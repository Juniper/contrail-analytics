#
# Copyright (c) 2016 Juniper Networks, Inc. All rights reserved.
#


import socket
import json

#from vnc_api.gen.resource_client import Alarm
from vnc_api.gen.resource_xsd import IdPermsType
from pysandesh.gen_py.sandesh.ttypes import SandeshLevel
#from sandesh.alarmgen_ctrl.ttypes import AlarmgenConfigLog
from config_handler import ConfigHandler
from analytics_api_config_db import DBBaseAG, GlobalSystemConfigAG, RFC5424AG, SyslogParserAG
from opserver_util import camel_case_to_hyphen, inverse_dict
from plugins.alarm_base import AlarmBase 
#from sandesh.viz.constants import UVE_MAP


#_INVERSE_UVE_MAP = inverse_dict(UVE_MAP)


class AnalyticsApiConfigHandler(ConfigHandler):

    REACTION_MAP = {
        'global_system_config': {
            'self': []
        },
        'rfc5424': {
            'self': []
        },
        'syslog_parser': {
            'self': []
        }
    }

    def __init__(self, sandesh, module_id, instance_id, rabbitmq_cfg,
                               cassandra_cfg, analytics_api_plugins,
                               analytics_api_config_change_callback):
        service_id = socket.gethostname()+':'+module_id+':'+instance_id
        super(AnalyticsApiConfigHandler, self).__init__(sandesh, service_id,
              rabbitmq_cfg, cassandra_cfg, DBBaseAG, self.REACTION_MAP)
        self._analytics_api_plugins = analytics_api_plugins
        self._analytics_api_config_change_callback 
                                   = analytics_api_config_change_callback
        self._anlytics_api_config_db = {}
        self._create_inbuilt_analytics_api_config()
    # end __init__

    #def config_db(self):
    #    return self._config_db
    # end config_db

    #def alarm_config_db(self):
    #    return self._alarm_config_db
    # end alarm_config_db

    def config_update(self, config_type, fq_name, config_obj):
        self._handle_config_update(config_type, fq_name, 'UPDATE', config_obj)
    # end config_update

    def config_delete(self, config_type, fq_name):
        self._handle_config_update(config_type, fq_name, 'DELETE')
    # end config_delete

    #def _update_alarm_config_table(self, alarm_fqname, alarm_obj, uve_keys,
    #                               operation):
    #    alarm_config_change_map = {}
    #    for key in uve_keys:
    #        uve_type_name = key.split(':', 1)
    #        try:
    #            table = UVE_MAP[uve_type_name[0]]
    #        except KeyError:
    #            self._logger.error('Invalid uve_key "%s" specified in '
    #                'alarm config "%s"' % (key, alarm_fqname))
    #        else:
    #            if len(uve_type_name) == 2:
    #                uve_key = table+':'+uve_type_name[1]
    #            else:
    #                uve_key = table
    #            try:
    #                alarm_table = self._alarm_config_db[uve_key]
    #            except KeyError:
    #                self._alarm_config_db[uve_key] = {}
    #                alarm_table = self._alarm_config_db[uve_key]
    #            finally:
    #                if operation == 'CREATE' or operation == 'UPDATE':
    #                    if not isinstance(alarm_obj, AlarmBase):
    #                        if alarm_table.has_key(alarm_fqname):
    #                            alarm_table[alarm_fqname].set_config(alarm_obj)
    #                        else:
    #                            alarm_base_obj = AlarmBase(config=alarm_obj)
    #                            alarm_table[alarm_fqname] = alarm_base_obj
    #                    else:
    #                        alarm_table[alarm_fqname] = alarm_obj
    #                elif operation == 'DELETE':
    #                    if alarm_table.has_key(alarm_fqname):
    #                        del alarm_table[alarm_fqname]
    #                    if not len(alarm_table):
    #                        del self._alarm_config_db[uve_key]
    #                else:
    #                    assert(0)
    #                alarm_config_change_map[uve_key] = {alarm_fqname:operation}
    #    return alarm_config_change_map
    # end _update_alarm_config_table

    def _create_inbuilt_analytics_api_config(self):
        if self._analytics_api_plugins == None:
            return 
    # end _create_inbuilt_alarms_config

    def _handle_config_update(self, config_type, fq_name, operation,
                              config_obj=None):
        # Log config update
        config_dict = None
        if config_obj is not None:
            config_dict = {k: json.dumps(v) for k, v in \
                self.obj_to_dict(config_obj).iteritems()}
        alarmgen_config_log = AlarmgenConfigLog(fq_name, config_type,
            operation, config_dict, sandesh=self._sandesh)
        alarmgen_config_log.send(sandesh=self._sandesh)
        if not self._config_db.get(config_type):
            self._config_db[config_type] = {}
        alarm_config_change_map = {}
        if operation == 'CREATE' or operation == 'UPDATE':
            if config_type == 'alarm':
                if '_alarm_rules' not in config_obj.__dict__:
                    self._logger.info('Ignoring conf for inbuilt alarm %s' % \
                            fq_name)
                    return
                alarm_config = self._config_db[config_type].get(fq_name)
                if alarm_config is None:
                    alarm_config_change_map = self._update_alarm_config_table(
                        fq_name, config_obj, config_obj.uve_keys.uve_key,
                        'CREATE')
                else:
                    # If the alarm config already exists, then check for
                    # addition/deletion of elements from uve_keys and
                    # update the alarm_config_db appropriately.
                    add_uve_keys = set(config_obj.uve_keys.uve_key) - \
                        set(alarm_config.uve_keys.uve_key)
                    if add_uve_keys:
                        alarm_config_change_map.update(
                            self._update_alarm_config_table(
                                fq_name, config_obj, add_uve_keys, 'CREATE'))
                    del_uve_keys = set(alarm_config.uve_keys.uve_key) - \
                        set(config_obj.uve_keys.uve_key)
                    if del_uve_keys:
                        alarm_config_change_map.update(
                            self._update_alarm_config_table(
                                fq_name, None, del_uve_keys, 'DELETE'))
                    upd_uve_keys = \
                        set(config_obj.uve_keys.uve_key).intersection(
                            set(alarm_config.uve_keys.uve_key))
                    if upd_uve_keys:
                        alarm_config_change_map.update(
                            self._update_alarm_config_table(
                                fq_name, config_obj, upd_uve_keys, 'UPDATE'))
            self._config_db[config_type][fq_name] = config_obj
        elif operation == 'DELETE':
            config_obj = self._config_db[config_type].get(fq_name)
            if config_obj is not None:
                if config_type == 'alarm':
                    alarm_config_change_map = self._update_alarm_config_table(
                        fq_name, None, config_obj.uve_keys.uve_key, 'DELETE')
                del self._config_db[config_type][fq_name]
            if not len(self._config_db[config_type]):
                del self._config_db[config_type]
        else:
            # Invalid operation
            assert(0)
        if alarm_config_change_map:
            self._alarm_config_change_callback(alarm_config_change_map)
    # end _handle_config_update

    def _handle_config_sync(self):
        db_cls_list = [GlobalSystemConfigAG, AlarmAG]
        for cls in db_cls_list:
            for fq_name, alarmgen_db_obj in cls.items():
                self._handle_config_update(cls.obj_type, fq_name, 'UPDATE',
                    alarmgen_db_obj.obj)
    # end _handle_config_sync


# end class AlarmGenConfigHandler
