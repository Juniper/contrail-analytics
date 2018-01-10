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
        self._analytics_api_config_change_callback\
                                   = analytics_api_config_change_callback
        self._rfc5424_tbl = {}
        self._paser_to_rfc5424_map = {}
        self._tag_tbl = {}
        self._metric_tbl = {}
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

    def _create_inbuilt_analytics_api_config(self):
        if self._analytics_api_plugins == None:
            return 
    # end _create_inbuilt_alarms_config

    def _handle_config_update(self, config_type, fq_name, operation,
                              config_obj=None):
        '''
        stat_tables should be the list like:
        {
             'display_name' : 'Values Table - string',
             'stat_type' : 'FieldNames'
             'stat_attr' : 'fields'
             'obj_table' : 'NONE',
             'attributes': [
                  { 'name' : 'fields.value',  'datatype' : 'string',    'index' : false},
             ]
        }
        '''
        # Log config update
        config_dict = None
        if config_obj is not None:
            config_dict = self.obj_to_dict(config_obj)
        if operation == 'CREATE' or operation == 'UPDATE':
            name = None
            if config_type == 'rfc5424':
                fq_name = fq_name.split(":")
                name = fq_name[-1]
                if 'rfc5424_config' in config_dict.keys():
                    self._rfc5424_tbl[name] = config_dict['rfc5424_config']
            if config_type == 'syslog_parser':
                fq_name = fq_name.split(":")
                name = fq_name[-1]
                parent_name = fq_name[-2]
                self._paser_to_rfc5424_map[name] = parent_name
                # first step: delete all old schema
                if name in self._metric_tbl.keys():
                    for metric in self._metric_tbl[name]:
                        stat_table['stat_type'] = name
                        stat_table['stat_attr'] = metric['name']
                        analytics_api_config_change_callback(stat_table, False)

                if 'query_tags' in config_dict.keys():
                    if 'tag_list' in config_dict['query_tags'].keys():
                        self._tag_tbl[name] = config_dict['query_tags']['tag_list']
                if 'metrics' in config_dict.keys():
                    if 'metric_list' in config_dict['metrics'].keys():
                        self._metric_tbl[name] = config_dict['metrics']['metric_list']
                if name in self._metric_tbl.keys():
                    for metric in self._metric_tbl[name]:
                        stat_tables = []
                        stat_table = {}
                        stat_table['attributes'] = []
                        stat_table['display_name'] = parent_name + " " + name
                        stat_table['stat_type'] = name
                        stat_table['stat_attr'] = metric['name']
                        stat_table['obj_table'] = 'NONE'
                        if name in self._tag_tbl.keys():
                            for tag in self._tag_tbl[name]:
                                attribute = {}
                                attribute['name'] = tag
                                attribute['datatype'] = 'string'
                                attribute['index'] = True
                                stat_table['attributes'].append(attribute)
                        attribute = {}
                        attribute['name'] = metric['name']
                        attribute['datatype'] = metric['data_type']
                        attribute['index'] = False
                        stat_table['attributes'].append(attribute)
                        stat_tables.append(stat_table)
                        self._analytics_api_config_change_callback(stat_tables, True)
        elif operation == 'DELETE':
            if config_type == 'rfc5424':
                fq_name = fq_name.split(":")
                name = fq_name[-1]
                if 'rfc5424_config' in config_dict.keys():
                    for m in config_dict['rfc5424_config']:
                        self._rfc5424_tbl[name].remove(m)
                        if len(self._rfc5424_tbl[name]) == 0:
                            self._rfc5424_tbl.remove(name)
            if config_type == 'syslog_parser':
                name = fq_name[-1]
                # first step: delete all old schema
                if name in self._metric_tbl.keys():
                    for metric in self._metric_tbl[name]:
                        stat_table['stat_type'] = name
                        stat_table['stat_attr'] = metric['name']
                        analytics_api_config_change_callback(stat_table, False)
                if 'query_tags' in config_dict.keys():
                    if 'tag_list' in config_dict['query_tags'].keys():
                        for tag in config_dict['query_tags']['tag_list']:
                            if tag in self._tag_tbl:
                                self._tag_tbl.remove(tag)
                if 'metrics' in config_dict.keys():
                    if 'metric_list' in config_dict['metrics'].keys():
                        for metric in config_dict['metrics']['metric_list']:
                            if metric in self._metric_tbl:
                                self._metric_tbl.remove(metric)
                if name in self._metric_tbl.keys():
                    for metric in self._metric_tbl[name]:
                        stat_tables = []
                        stat_table = {}
                        stat_table['attributes'] = []
                        stat_table['display_name'] = parent_name + " " + name
                        stat_table['stat_type'] = name
                        stat_table['stat_attr'] = metric['name']
                        stat_table['obj_table'] = 'NONE'
                        for tag in self._tag_tbl[name]:
                            attribute = {}
                            attribute['name'] = tag
                            attribute['datatype'] = 'string'
                            attribute['index'] = true
                            stat_table['attributes'].append(attribute)
                    attribute = {}
                    attribute['name'] = metric['name']
                    attribute['datatype'] = metric['data_type']
                    attribute['index'] = false
                    stat_table['attributes'].append(attribute)
                    stat_tables.append(stat_table)
                    analytics_api_config_change_callback(stat_tables, True)
        else:
            # Invalid operation
            assert(0)
    # end _handle_config_update

    def _handle_config_sync(self):
        db_cls_list = [GlobalSystemConfigAG, RFC5424AG, SyslogParserAG]
        for cls in db_cls_list:
            for fq_name, alarmgen_db_obj in cls.items():
                self._handle_config_update(cls.obj_type, fq_name, 'UPDATE',
                    alarmgen_db_obj.obj)
    # end _handle_config_sync


# end class AlarmGenConfigHandler
