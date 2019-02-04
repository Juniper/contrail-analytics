#
# Copyright (c) 2016 Juniper Networks, Inc. All rights reserved.
#

from gevent import monkey
monkey.patch_all()

import gevent

import json
import traceback

from cfgm_common.vnc_amqp import VncAmqpHandle
from cfgm_common.vnc_etcd import VncEtcdWatchHandle
from cfgm_common.vnc_object_db import VncObjectDBClient, VncObjectEtcdClient
from analytics_logger import AnalyticsLogger


class ConfigHandler(object):

    def __init__(self, sandesh, service_id, rabbitmq_cfg, cassandra_cfg,
                 etcd_cfg, db_cls, reaction_map, host_ip):
        self._sandesh = sandesh
        self._logger = AnalyticsLogger(self._sandesh)
        self._service_id = service_id
        self._rabbitmq_cfg = rabbitmq_cfg
        self._cassandra_cfg = cassandra_cfg
        self._etcd_cfg = etcd_cfg
        self._db_cls = db_cls
        self._reaction_map = reaction_map
        self._vnc_amqp = None
        self._vnc_db = None
        self.host_ip = host_ip
    # end __init__

    # Public methods

    def start(self):
        #use_etcd = self._etcd_cfg and self._etcd_cfg.host
        use_etcd = True
        # Connect to rabbitmq for config update notifications
        self._logger.info("!!!!!!!!!!!!Connecting to ETCD (subscription): %s" % str(self._etcd_cfg))
        while True:
            try:
                if use_etcd:
                    self._vnc_amqp = VncAmqpHandle(self._sandesh, self._logger,
                        self._db_cls, self._reaction_map, self._service_id,
                        self._rabbitmq_cfg, self.host_ip)
                else:
                    self._vnc_amqp = VncEtcdWatchHandle(logger=self._logger,
                        **self._etcd_cfg)
                self._logger.info("!!!!!!!!!!Esteblishing connection to ETCD (subscription)")
                self._vnc_amqp.establish()
            except Exception as e:
                template = '!!!!!!!!!!!!!!Exception {0} connecting to ETCD. Arguments:\n{1!r}'
                msg = template.format(type(e).__name__, e.args)
                self._logger.error('%s: %s' % (msg, traceback.format_exc()))
                gevent.sleep(2)
            else:
                break

        self._logger.info("!!!!!!!!!!Connected to ETCD (subscription)")

        # Connect to config Cassandra DB
        self._logger.info("!!!!!!!!!!!Connecting to ETCD")
        try:
            if use_etcd:
                cassandra_credential = {
                    'username': self._cassandra_cfg['user'],
                    'password': self._cassandra_cfg['password']
                }
                if not all(cassandra_credential.values()):
                    cassandra_credential = None

                self._vnc_db = VncObjectDBClient(self._cassandra_cfg['servers'],
                self._cassandra_cfg['cluster_id'], logger=self._logger.log,
                credential=cassandra_credential,
                ssl_enabled=self._cassandra_cfg['use_ssl'],
                ca_certs=self._cassandra_cfg['ca_certs'])
            else:
                self._vnc_db = VncObjectEtcdClient(logger=self._logger.log,
                    **self._etcd_cfg)
        except Exception as e:
            template = 'Exception {0} connecting to Config DB. Arguments:\n{1!r}'
            msg = template.format(type(e).__name__, e.args)
            self._logger.error('%s: %s' % (msg, traceback.format_exc()))
            exit(2)
        self._logger.info("!!!!!!!!!!!!!!!!!!Connected to ETCD")
        self._db_cls.init(self, self._logger, self._vnc_db)
        self._sync_config_db()
        self._logger.info("!!!!!!!!!!!!!!!!ETCD is syncronized")
    # end start

    def stop(self):
        self._vnc_amqp.close()
        self._vnc_db = None
        self._db_cls.clear()
    # end stop

    def obj_to_dict(self, obj):
        def to_json(obj):
            if hasattr(obj, 'serialize_to_json'):
                return obj.serialize_to_json()
            else:
                return dict((k, v) for k, v in obj.__dict__.iteritems())

        return json.loads(json.dumps(obj, default=to_json))
    # end obj_to_dict

    # Private methods

    def _fqname_to_str(self, fq_name):
        return ':'.join(fq_name)
    # end _fqname_to_str

    def _sync_config_db(self):
        for cls in self._db_cls.get_obj_type_map().values():
            cls.reinit()
        self._handle_config_sync()
        self._vnc_amqp._db_resync_done.set()
    # end _sync_config_db

    # Should be overridden by the derived class
    def _handle_config_sync(self):
        pass
    # end _handle_config_sync


# end class ConfigHandler
