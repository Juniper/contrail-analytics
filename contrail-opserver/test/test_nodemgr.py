#!/usr/bin/env python
#
#
# Copyright (c) 2018 Juniper Networks, Inc. All rights reserved.
#

#
# NodemgrTest
#
# Unit Tests for testing nodemgr
#

from builtins import object
import logging
import os
import sys
import copy
import mock
import unittest
from gevent.subprocess import Popen, PIPE
#from supervisor import xmlrpc
import nodemgr
import nodemgr.common.event_manager
import nodemgr.control_nodemgr.event_manager
from pysandesh.connection_info import ConnectionState
import nodemgr.common.utils
from nodemgr.common.docker_process_manager import DockerProcessInfoManager

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')
class config(object):
    def __init__(self):
        self.collectors = ['0.0.0.0']
        self.sandesh_keyfile = ''
        self.sandesh_certfile = ''
        self.sandesh_ca_cert = ''
        self.sandesh_ssl_enable = False
        self.introspect_ssl_enable = None
        self.introspect_ssl_insecure = None
        self.sandesh_dscp_value = None
        self.disable_object_logs = None
        self.sandesh_send_rate_limit = None
        self.log_local = False
        self.log_category = '*'
        self.log_level = 4
        self.log_file = None
        self.use_syslog = False
        self.syslog_facility = None
        self.hostip = '0.0.0.0'
        self.http_server_ip = '0.0.0.0'
        self.corefile_path = '/var/crashes/'
        self.tcp_keepalive_enable = None
        self.tcp_keepalive_idle_time = None
        self.tcp_keepalive_interval = None
        self.tcp_keepalive_probes = None
        self.hostname = None

class NodemgrTest(unittest.TestCase):

    @mock.patch('os.path.getmtime')
    @mock.patch('glob.glob')
    @mock.patch('os.remove')
    @mock.patch('__builtin__.open')
    @mock.patch('nodemgr.control_nodemgr.event_manager.ControlEventManager.send_process_state_db')
    @mock.patch('pysandesh.connection_info.ConnectionState.get_conn_state_cb')
    @mock.patch('nodemgr.common.utils.is_running_in_kubepod')
    @mock.patch('nodemgr.common.docker_process_manager.DockerProcessInfoManager')
    @mock.patch('nodemgr.common.docker_process_manager.DockerProcessInfoManager.get_all_processes')
    @mock.patch('nodemgr.common.linux_sys_data.LinuxSysData.get_corefiles')
    def test_nodemgr(self, mock_get_core_files, mock_get_all_process, mock_docker_process_info_mgr, mock_is_running_in_kubepod, mock_get_conn_state_cb,
        mock_send_process_state_db, mock_open, mock_remove, mock_glob, mock_tm_time):
        headers = {}
        headers['expected']='0'
        headers['pid']='123'
        config_obj = config()
        mock_is_running_in_kubepod.return_value = True
        mock_docker_process_info_mgr.return_value = DockerProcessInfoManager('','','','')
        list_of_process = []
        process_info = {}
        process_info['pid'] = '123'
        process_info['statename'] = 'expected'
        process_info['start'] = '12:00:00'
        process_info['name'] = 'proc1'
        process_info['group'] = 'default'
        list_of_process.append(process_info)
        mock_get_all_process.return_value = list_of_process
        cm = nodemgr.control_nodemgr.event_manager.\
            ControlEventManager(config_obj,'')
        proc_stat = nodemgr.common.process_stat.ProcessStat('proc1', '0.0.0.0')
        # create 4 core files
        cm.process_state_db['default']['proc1'] = proc_stat
        # IF core file list < 5 entries , no core files should be deleted
        mock_get_core_files.return_value = ['core.proc1.1', 'core.proc1.2', 'core.proc1.3', 'core.proc1.4']
        status = cm._update_process_core_file_list()
        exp_core_list = ['core.proc1.1', 'core.proc1.2', 'core.proc1.3', 'core.proc1.4']
        # there should be no core files
        self.assertEqual(len(cm.process_state_db['default']['proc1'].core_file_list), 4)
        self.assertEqual(cm.process_state_db['default']['proc1'].core_file_list, exp_core_list)
        # Calls with more core files should change the list of core files
        mock_get_core_files.return_value = ['core.proc1.1', 'core.proc1.2', 'core.proc1.3', 'core.proc1.4', 'core.proc1.5']
        exp_core_list = ['core.proc1.2', 'core.proc1.3', 'core.proc1.4', 'core.proc1.5']
        status = cm._update_process_core_file_list()
        self.assertEqual(len(cm.process_state_db['default']['proc1'].core_file_list), 4)

if __name__ == '__main__':
    unittest.main()
