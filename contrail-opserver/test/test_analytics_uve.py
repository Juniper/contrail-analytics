#!/usr/bin/env python

#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

#
# analytics_uvetest.py
#
# UVE and Alarm tests
#

import os
import sys
import threading
threading._DummyThread._Thread__stop = lambda x: 42
import signal
import gevent
from gevent import monkey
monkey.patch_all()
import unittest
import testtools
import fixtures
import mock
import socket
from utils.util import obj_to_dict, find_buildroot
from utils.analytics_fixture import AnalyticsFixture
from utils.generator_fixture import GeneratorFixture
from mockzoo import mockzoo
import logging
import time
from opserver.sandesh.viz.constants import *
from opserver.sandesh.viz.constants import _OBJECT_TABLES
from opserver.vnc_cfg_api_client import VncCfgApiClient
from sandesh_common.vns.ttypes import Module
from sandesh_common.vns.constants import ModuleNames
import platform

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')
builddir = find_buildroot(os.getcwd())


class AnalyticsUveTest(testtools.TestCase, fixtures.TestWithFixtures):

    @classmethod
    def setUpClass(cls):

        if (os.getenv('LD_LIBRARY_PATH', '').find('build/lib') < 0):
            if (os.getenv('DYLD_LIBRARY_PATH', '').find('build/lib') < 0):
                assert(False)

    @classmethod
    def tearDownClass(cls):
        pass
    
    def setUp(self):
        super(AnalyticsUveTest, self).setUp()
        mock_is_role_cloud_admin = mock.patch.object(VncCfgApiClient,
            'is_role_cloud_admin')
        mock_is_role_cloud_admin.return_value = True
        mock_is_role_cloud_admin.start()
        self.addCleanup(mock_is_role_cloud_admin.stop)
        mock_get_obj_perms_by_name = mock.patch.object(VncCfgApiClient,
            'get_obj_perms_by_name')
        rv_uve_perms = {'permissions': 'RWX'}
        mock_get_obj_perms_by_name.return_value = rv_uve_perms
        mock_get_obj_perms_by_name.start()
        self.addCleanup(mock_get_obj_perms_by_name.stop)

    #@unittest.skip('Skipping non-cassandra test with vizd')
    def test_00_nocassandra(self):
        '''
        This test starts redis,vizd,opserver and qed
        Then it checks that the collector UVE (via redis)
        can be accessed from opserver.
        '''
        logging.info("%%% test_00_nocassandra %%%")

        vizd_obj = self.useFixture(
            AnalyticsFixture(logging, builddir, 0)) 
        assert vizd_obj.verify_on_setup()

        return True
    # end test_00_nocassandra

    #@unittest.skip('Skipping VM UVE test')
    def test_01_vm_uve(self):
        '''
        This test starts redis, vizd, opserver, qed, and a python generator
        that simulates vrouter and sends UveVirtualMachineAgentTrace messages.
        Then it checks that the VM UVE (via redis) can be accessed from
        opserver.
        '''
        logging.info("%%% test_01_vm_uve %%%")

        vizd_obj = self.useFixture(
            AnalyticsFixture(logging, builddir, 0))
        assert vizd_obj.verify_on_setup()
        collectors = [vizd_obj.get_collector()]
        generator_obj = self.useFixture(
            GeneratorFixture("contrail-vrouter-agent", collectors,
                             logging, vizd_obj.get_opserver_port()))
        assert generator_obj.verify_on_setup()
        generator_obj.send_vm_uve(vm_id='abcd',
                                  num_vm_ifs=5,
                                  msg_count=5)
        assert generator_obj.verify_vm_uve(vm_id='abcd',
                                           num_vm_ifs=5,
                                           msg_count=5)
        # Delete the VM UVE and verify that the deleted flag is set
        # in the UVE cache
        generator_obj.delete_vm_uve('abcd')
        assert generator_obj.verify_vm_uve_cache(vm_id='abcd', delete=True)
        # Add the VM UVE with the same vm_id and verify that the deleted flag
        # is cleared in the UVE cache
        generator_obj.send_vm_uve(vm_id='abcd',
                                  num_vm_ifs=5,
                                  msg_count=5)
        assert generator_obj.verify_vm_uve_cache(vm_id='abcd')
        assert generator_obj.verify_vm_uve(vm_id='abcd',
                                           num_vm_ifs=5,
                                           msg_count=5)
        # Generate VM with vm_id containing XML control character
        generator_obj.send_vm_uve(vm_id='<abcd&>', num_vm_ifs=2, msg_count=2)
        assert generator_obj.verify_vm_uve(vm_id='<abcd&>', num_vm_ifs=2,
                                           msg_count=2)
        return True
    # end test_01_vm_uve

    #@unittest.skip('Skipping VM UVE test')
    def test_02_vm_uve_with_password(self):
        '''
        This test starts redis, vizd, opserver, qed, and a python generator
        that simulates vrouter and sends UveVirtualMachineAgentTrace messages.
        Then it checks that the VM UVE (via redis) can be accessed from
        opserver.
        '''
        logging.info("%%% test_02_vm_uve_with_password %%%")

        vizd_obj = self.useFixture(
            AnalyticsFixture(logging, builddir, 0,
                             redis_password='contrail'))
        assert vizd_obj.verify_on_setup()
        collectors = [vizd_obj.get_collector()]
        generator_obj = self.useFixture(
            GeneratorFixture("contrail-vrouter-agent", collectors,
                             logging, vizd_obj.get_opserver_port()))
        assert generator_obj.verify_on_setup()
        generator_obj.send_vm_uve(vm_id='abcd',
                                  num_vm_ifs=5,
                                  msg_count=5)
        assert generator_obj.verify_vm_uve(vm_id='abcd',
                                           num_vm_ifs=5,
                                           msg_count=5)
        return True
    # end test_02_vm_uve_with_password

    #@unittest.skip('skipping verify redis-uve restart')
    def test_03_redis_uve_restart(self):
        logging.info('%%% test_03_redis_uve_restart %%%')

        vizd_obj = self.useFixture(
            AnalyticsFixture(logging, builddir, 0,
            start_kafka = True))
        assert vizd_obj.verify_on_setup()

        collectors = [vizd_obj.get_collector()]
        alarm_gen1 = self.useFixture(
            GeneratorFixture('vrouter-agent', collectors, logging,
                             None, hostname=socket.gethostname()))
        alarm_gen1.verify_on_setup()

        # send vrouter UVE without build_info !!!
        # check for PartialSysinfo alarm
        alarm_gen1.send_vrouterinfo("myvrouter1")
        assert(vizd_obj.verify_uvetable_alarm("ObjectVRouter",
            "ObjectVRouter:myvrouter1",
            "default-global-system-config:partial-sysinfo-compute"))

        self.verify_uve_resync(vizd_obj)
 
        # Alarm should return after redis restart
        assert(vizd_obj.verify_uvetable_alarm("ObjectVRouter",
            "ObjectVRouter:myvrouter1",
            "default-global-system-config:partial-sysinfo-compute"))
    # end test_03_redis_uve_restart

    #@unittest.skip('verify redis-uve restart')
    def test_04_redis_uve_restart_with_password(self):
        logging.info('%%% test_04_redis_uve_restart_with_password %%%')

        vizd_obj = self.useFixture(
            AnalyticsFixture(logging,
                             builddir, 0,
                             redis_password='contrail'))
        self.verify_uve_resync(vizd_obj)
        return True
    # end test_04_redis_uve_restart

    def verify_uve_resync(self, vizd_obj):
        assert vizd_obj.verify_on_setup()
        assert vizd_obj.verify_collector_redis_uve_connection(
                            vizd_obj.collectors[0])
        assert vizd_obj.verify_opserver_redis_uve_connection(
                            vizd_obj.opserver)
        # verify redis-uve list
        host = socket.gethostname()
        gen_list = [host+':Analytics:contrail-collector:0',
                    host+':Analytics:contrail-query-engine:0',
                    host+':Analytics:contrail-analytics-api:0']
        assert vizd_obj.verify_generator_uve_list(gen_list)

        # stop redis-uve
        vizd_obj.redis_uves[0].stop()
        assert vizd_obj.verify_collector_redis_uve_connection(
                            vizd_obj.collectors[0], False)
        assert vizd_obj.verify_opserver_redis_uve_connection(
                            vizd_obj.opserver, False)
        # start redis-uve and verify that contrail-collector and Opserver are
        # connected to the redis-uve
        vizd_obj.redis_uves[0].start()
        assert vizd_obj.verify_collector_redis_uve_connection(
                            vizd_obj.collectors[0])
        assert vizd_obj.verify_opserver_redis_uve_connection(
                            vizd_obj.opserver)
        # verify that UVEs are resynced with redis-uve
        assert vizd_obj.verify_generator_uve_list(gen_list)

    @unittest.skip('Skipping contrail-collector HA test')
    def test_05_collector_ha(self):
        logging.info('%%% test_05_collector_ha %%%')
        
        vizd_obj = self.useFixture(
            AnalyticsFixture(logging, builddir, 0,
                             collector_ha_test=True))
        assert vizd_obj.verify_on_setup()
        collectors = [vizd_obj.collectors[1].get_addr(), 
                      vizd_obj.collectors[0].get_addr()]
        vr_agent = self.useFixture(
            GeneratorFixture("contrail-vrouter-agent", collectors,
                             logging, vizd_obj.get_opserver_port()))
        assert vr_agent.verify_on_setup()
        source = socket.gethostname()
        exp_genlist = [
            source+':Analytics:contrail-collector:0',
            source+':Analytics:contrail-analytics-api:0',
            source+':Analytics:contrail-query-engine:0',
            source+':Test:contrail-vrouter-agent:0',
            source+'dup:Analytics:contrail-collector:0'
        ]
        assert vizd_obj.verify_generator_list(vizd_obj.collectors,
                                              exp_genlist)
        # stop collectors[0] and verify that all the generators are connected
        # to collectors[1]
        vizd_obj.collectors[0].stop()
        exp_genlist = [
            source+'dup:Analytics:contrail-collector:0',
            source+':Analytics:contrail-analytics-api:0',
            source+':Analytics:contrail-query-engine:0',
            source+':Test:contrail-vrouter-agent:0'
        ]
        assert vizd_obj.verify_generator_list([vizd_obj.collectors[1]],
                                              exp_genlist)
        # start collectors[0]
        vizd_obj.collectors[0].start()
        exp_genlist = [source+':Analytics:contrail-collector:0']
        assert vizd_obj.verify_generator_list([vizd_obj.collectors[0]],
                                              exp_genlist)
        # verify that the old UVEs are flushed from redis when collector restarts
        exp_genlist = [vizd_obj.collectors[0].get_generator_id()]
        assert vizd_obj.verify_generator_list_in_redis(\
                                vizd_obj.collectors[0].get_redis_uve(),
                                exp_genlist)

        # stop collectors[1] and verify that all the generators are connected
        # to collectors[0]
        vizd_obj.collectors[1].stop()
        exp_genlist = [
            source+':Analytics:contrail-collector:0',
            source+':Analytics:contrail-analytics-api:0',
            source+':Analytics:contrail-query-engine:0',
            source+':Test:contrail-vrouter-agent:0'
        ]
        assert vizd_obj.verify_generator_list([vizd_obj.collectors[0]],
                                              exp_genlist)
        # verify the generator list in redis
        exp_genlist = [vizd_obj.collectors[0].get_generator_id(),
                       vr_agent.get_generator_id(),
                       vizd_obj.opserver.get_generator_id(),
                       vizd_obj.query_engine.get_generator_id()]
        assert vizd_obj.verify_generator_list_in_redis(\
                                vizd_obj.collectors[0].get_redis_uve(),
                                exp_genlist)

        # stop QE 
        vizd_obj.query_engine.stop()
        exp_genlist = [
            source+':Analytics:contrail-collector:0',
            source+':Analytics:contrail-analytics-api:0',
            source+':Test:contrail-vrouter-agent:0'
        ]
        assert vizd_obj.verify_generator_list([vizd_obj.collectors[0]],
                                              exp_genlist)

        # verify the generator list in redis
        exp_genlist = [vizd_obj.collectors[0].get_generator_id(),
                       vizd_obj.opserver.get_generator_id(),
                       vr_agent.get_generator_id()]
        assert vizd_obj.verify_generator_list_in_redis(\
                                vizd_obj.collectors[0].get_redis_uve(),
                                exp_genlist)

        # start a python generator and QE and verify that they are connected
        # to collectors[0]
        vr2_collectors = [vizd_obj.collectors[1].get_addr(), 
                          vizd_obj.collectors[0].get_addr()]
        vr2_agent = self.useFixture(
            GeneratorFixture("contrail-snmp-collector", collectors,
                             logging, vizd_obj.get_opserver_port()))
        assert vr2_agent.verify_on_setup()
        vizd_obj.query_engine.start()
        exp_genlist = [
            source+':Analytics:contrail-collector:0',
            source+':Analytics:contrail-analytics-api:0',
            source+':Test:contrail-vrouter-agent:0',
            source+':Analytics:contrail-query-engine:0',
            source+':Test:contrail-snmp-collector:0'
        ]
        assert vizd_obj.verify_generator_list([vizd_obj.collectors[0]],
                                              exp_genlist)
        # stop the collectors[0] - both collectors[0] and collectors[1] are down
        # send the VM UVE and verify that the VM UVE is synced after connection
        # to the collector
        vizd_obj.collectors[0].stop()
        # Make sure the connection to the collector is teared down before 
        # sending the VM UVE
        while True:
            if vr_agent.verify_on_setup() is False:
                break
        vr_agent.send_vm_uve(vm_id='abcd-1234-efgh-5678',
                             num_vm_ifs=5, msg_count=5) 
        vizd_obj.collectors[1].start()
        exp_genlist = [
            source+'dup:Analytics:contrail-collector:0',
            source+':Analytics:contrail-analytics-api:0',
            source+':Test:contrail-vrouter-agent:0',
            source+':Analytics:contrail-query-engine:0',
            source+':Test:contrail-snmp-collector:0'
        ]
        assert vizd_obj.verify_generator_list([vizd_obj.collectors[1]],
                                              exp_genlist)
        assert vr_agent.verify_vm_uve(vm_id='abcd-1234-efgh-5678',
                                      num_vm_ifs=5, msg_count=5)
    # end test_05_collector_ha

    #@unittest.skip('Skipping UVE/Alarm Filter test')
    def test_06_uve_filter(self):
        '''
        This test verifies the filter options kfilt, sfilt, mfilt and cfilt
        in the UVE/Alarm GET and POST methods.
        '''
        logging.info('%%% test_06_uve_filter %%%')

        if AnalyticsUveTest._check_skip_kafka() is True:
            return True

        vizd_obj = self.useFixture(
            AnalyticsFixture(logging, builddir, 0,
                collector_ha_test=True, start_kafka = True))
        assert vizd_obj.verify_on_setup()

        collectors = [vizd_obj.collectors[0].get_addr(),
                      vizd_obj.collectors[1].get_addr()]
        api_server_name = socket.gethostname()+'_1'
        api_server = self.useFixture(
            GeneratorFixture('contrail-api', [collectors[0]], logging,
                             None, node_type='Config',
                             hostname=api_server_name))
        vr_agent_name = socket.gethostname()+'_2'
        vr_agent = self.useFixture(
            GeneratorFixture('contrail-vrouter-agent', [collectors[1]],
                             logging, None, node_type='Compute',
                             hostname=vr_agent_name))
        api_server.verify_on_setup()
        vr_agent.verify_on_setup()

        vn_list = ['default-domain:project1:vn1',
                   'default-domain:project1:vn2',
                   'default-domain:project2:vn1',
                   'default-domain:project2:vn1&']
        # generate UVEs for the filter test
        api_server.send_vn_config_uve(name=vn_list[0],
                                      partial_conn_nw=[vn_list[1]],
                                      num_acl_rules=2)
        api_server.send_vn_config_uve(name=vn_list[1],
                                      num_acl_rules=3)
        vr_agent.send_vn_agent_uve(name=vn_list[1], num_acl_rules=3,
                                   ipkts=2, ibytes=1024)
        vr_agent.send_vn_agent_uve(name=vn_list[2], ipkts=4, ibytes=128)
        vr_agent.send_vn_agent_uve(name=vn_list[3], ipkts=8, ibytes=256)

        filt_test = [
            # no filter
            {
                'uve_list_get': [
                    'default-domain:project1:vn1',
                    'default-domain:project1:vn2',
                    'default-domain:project2:vn1',
                    'default-domain:project2:vn1&'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn1',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'partially_connected_networks': [
                                        'default-domain:project1:vn2'
                                    ],
                                    'total_acl_rules': 2
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project1:vn2',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 2,
                                    'in_bytes': 1024,
                                    'total_acl_rules': 3
                                },
                                'UveVirtualNetworkConfig': {
                                    'total_acl_rules': 3
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 4,
                                    'in_bytes': 128
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1&',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 8,
                                    'in_bytes': 256
                                }
                            }
                        }
                    ]
                },
            },

            # kfilt
            {
                'kfilt': ['*'],
                'uve_list_get': [
                    'default-domain:project1:vn1',
                    'default-domain:project1:vn2',
                    'default-domain:project2:vn1',
                    'default-domain:project2:vn1&'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn1',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'partially_connected_networks': [
                                        'default-domain:project1:vn2'
                                    ],
                                    'total_acl_rules': 2
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project1:vn2',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 2,
                                    'in_bytes': 1024,
                                    'total_acl_rules': 3
                                },
                                'UveVirtualNetworkConfig': {
                                    'total_acl_rules': 3
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 4,
                                    'in_bytes': 128
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1&',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 8,
                                    'in_bytes': 256
                                }
                            }
                        }
                    ]
                },
            },
            {
                'kfilt': ['default-domain:project1:*',
                          'default-domain:project2:*'],
                'uve_list_get': [
                    'default-domain:project1:vn1',
                    'default-domain:project1:vn2',
                    'default-domain:project2:vn1',
                    'default-domain:project2:vn1&'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn1',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'partially_connected_networks': [
                                        'default-domain:project1:vn2'
                                    ],
                                    'total_acl_rules': 2
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project1:vn2',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 2,
                                    'in_bytes': 1024,
                                    'total_acl_rules': 3
                                },
                                'UveVirtualNetworkConfig': {
                                    'total_acl_rules': 3
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 4,
                                    'in_bytes': 128
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1&',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 8,
                                    'in_bytes': 256
                                }
                            }
                        }
                    ]
                },
            },
            {
                'kfilt': ['default-domain:project1:vn1',
                          'default-domain:project2:*'],
                'uve_list_get': [
                    'default-domain:project1:vn1',
                    'default-domain:project2:vn1',
                    'default-domain:project2:vn1&'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn1',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'partially_connected_networks': [
                                        'default-domain:project1:vn2'
                                    ],
                                    'total_acl_rules': 2
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 4,
                                    'in_bytes': 128
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1&',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 8,
                                    'in_bytes': 256
                                }
                            }
                        }
                    ]
                },
            },
            {
                'kfilt': [
                    'default-domain:project2:*',
                    'invalid-vn:*'
                ],
                'uve_list_get': [
                    'default-domain:project2:vn1',
                    'default-domain:project2:vn1&'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project2:vn1',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 4,
                                    'in_bytes': 128
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1&',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 8,
                                    'in_bytes': 256
                                }
                            }
                        }
                    ]
                },
            },
            {
                'kfilt': [
                    'default-domain:project1:vn2',
                    'default-domain:project2:vn1&',
                    'invalid-vn'
                ],
                'uve_list_get': [
                    'default-domain:project1:vn2',
                    'default-domain:project2:vn1&'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn2',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 2,
                                    'in_bytes': 1024,
                                    'total_acl_rules': 3
                                },
                                'UveVirtualNetworkConfig': {
                                    'total_acl_rules': 3
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1&',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 8,
                                    'in_bytes': 256
                                }
                            }
                        }
                    ]
                },
            },
            {
                'kfilt': ['invalid-vn'],
                'uve_list_get': [],
                'uve_get_post': {'value': []},
            },

            # sfilt
            {
                'sfilt': socket.gethostname()+'_1',
                'uve_list_get': [
                    'default-domain:project1:vn1',
                    'default-domain:project1:vn2'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn1',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'partially_connected_networks': [
                                        'default-domain:project1:vn2'
                                    ],
                                    'total_acl_rules': 2
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project1:vn2',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'total_acl_rules': 3
                                }
                            }
                        }
                    ]
                },
            },
            {
                'sfilt': 'invalid_source',
                'uve_list_get': [],
                'uve_get_post': {'value': []},
            },

            # mfilt
            {
                'mfilt': 'Config:contrail-api:0',
                'uve_list_get': [
                    'default-domain:project1:vn1',
                    'default-domain:project1:vn2'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn1',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'partially_connected_networks': [
                                        'default-domain:project1:vn2'
                                    ],
                                    'total_acl_rules': 2
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project1:vn2',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'total_acl_rules': 3
                                }
                            }
                        }
                    ]
                },
            },
            {
                'mfilt': 'Analytics:contrail-invalid:0',
                'uve_list_get': [],
                'uve_get_post': {'value': []},
            },

            # cfilt
            {
                'cfilt': ['UveVirtualNetworkAgent'],
                'uve_list_get': [
                    'default-domain:project1:vn2',
                    'default-domain:project2:vn1',
                    'default-domain:project2:vn1&'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn2',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 2,
                                    'in_bytes': 1024,
                                    'total_acl_rules': 3
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 4,
                                    'in_bytes': 128
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1&',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 8,
                                    'in_bytes': 256
                                }
                            }
                        }
                    ]
                },
            },
            {
                'cfilt': [
                    'UveVirtualNetworkAgent:total_acl_rules',
                    'UveVirtualNetworkConfig:partially_connected_networks'
                ],
                'uve_list_get': [
                    'default-domain:project1:vn1',
                    'default-domain:project1:vn2'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn1',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'partially_connected_networks': [
                                        'default-domain:project1:vn2'
                                    ]
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project1:vn2',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'total_acl_rules': 3
                                }
                            }
                        }
                    ]
                },
            },
            {
                'cfilt': [
                    'UveVirtualNetworkConfig:invalid',
                    'UveVirtualNetworkAgent:in_tpkts',
                ],
                'uve_list_get': [
                    'default-domain:project1:vn2',
                    'default-domain:project2:vn1',
                    'default-domain:project2:vn1&'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn2',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 2,
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 4,
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1&',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 8,
                                }
                            }
                        }
                    ]
                },
            },
            {
                'cfilt': [
                    'UveVirtualNetworkAgent:invalid',
                    'invalid'
                ],
                'uve_list_get': [],
                'uve_get_post': {'value': []},
            },

            # ackfilt
            {
                'ackfilt': True,
                'uve_list_get': [
                    'default-domain:project1:vn1',
                    'default-domain:project1:vn2',
                    'default-domain:project2:vn1',
                    'default-domain:project2:vn1&'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn1',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'partially_connected_networks': [
                                        'default-domain:project1:vn2'
                                    ],
                                    'total_acl_rules': 2
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project1:vn2',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 2,
                                    'in_bytes': 1024,
                                    'total_acl_rules': 3
                                },
                                'UveVirtualNetworkConfig': {
                                    'total_acl_rules': 3
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 4,
                                    'in_bytes': 128
                                },
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1&',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 8,
                                    'in_bytes': 256
                                },
                            }
                        }
                    ]
                },
            },
            {
                'ackfilt': False,
                'uve_list_get': [
                    'default-domain:project1:vn1',
                    'default-domain:project1:vn2',
                    'default-domain:project2:vn1',
                    'default-domain:project2:vn1&'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn1',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'partially_connected_networks': [
                                        'default-domain:project1:vn2'
                                    ],
                                    'total_acl_rules': 2
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project1:vn2',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 2,
                                    'in_bytes': 1024,
                                    'total_acl_rules': 3
                                },
                                'UveVirtualNetworkConfig': {
                                    'total_acl_rules': 3
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 4,
                                    'in_bytes': 128
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1&',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 8,
                                    'in_bytes': 256
                                }
                            }
                        }
                    ]
                },
            },

            # kfilt + sfilt
            {
                'kfilt': [
                    'default-domain:project1:*',
                    'default-domain:project2:vn1',
                    'default-domain:invalid'
                ],
                'sfilt': socket.gethostname()+'_2',
                'uve_list_get': [
                    'default-domain:project1:vn2',
                    'default-domain:project2:vn1'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn2',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 2,
                                    'in_bytes': 1024,
                                    'total_acl_rules': 3
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 4,
                                    'in_bytes': 128
                                }
                            }
                        }
                    ]
                },
            },

            # kfilt + sfilt + ackfilt
            {
                'kfilt': [
                    'default-domain:project1:vn1',
                    'default-domain:project2:*',
                    'default-domain:invalid'
                ],
                'sfilt': socket.gethostname()+'_2',
                'ackfilt': True,
                'uve_list_get': [
                    'default-domain:project2:vn1',
                    'default-domain:project2:vn1&'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project2:vn1',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 4,
                                    'in_bytes': 128
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project2:vn1&',
                            'value': {
                                'UveVirtualNetworkAgent': {
                                    'in_tpkts': 8,
                                    'in_bytes': 256
                                }
                            }
                        }
                    ]
                },
            },

            # kfilt + sfilt + cfilt
            {
                'kfilt': [
                    'default-domain:project1:vn2',
                    'default-domain:project2:vn1'
                ],
                'sfilt': socket.gethostname()+'_1',
                'cfilt': [
                    'UveVirtualNetworkConfig',
                ],
                'uve_list_get': [
                    'default-domain:project1:vn2'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn2',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'total_acl_rules': 3
                                },
                            }
                        }
                    ]
                },
            },

            # kfilt + mfilt + cfilt
            {
                'kfilt': ['*'],
                'mfilt': 'Config:contrail-api:0',
                'cfilt': [
                    'UveVirtualNetworkAgent',
                ],
                'uve_list_get': [],
                'uve_get_post': {'value': []},
            },

            # kfilt + sfilt + mfilt + cfilt
            {
                'kfilt': [
                    'default-domain:project1:vn1',
                    'default-domain:project1:vn2',
                    'default-domain:project2:*'
                ],
                'sfilt': socket.gethostname()+'_1',
                'mfilt': 'Config:contrail-api:0',
                'cfilt': [
                    'UveVirtualNetworkConfig:partially_connected_networks',
                    'UveVirtualNetworkConfig:total_acl_rules',
                ],
                'uve_list_get': [
                    'default-domain:project1:vn1',
                    'default-domain:project1:vn2'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn1',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'partially_connected_networks': [
                                        'default-domain:project1:vn2'
                                    ],
                                    'total_acl_rules': 2
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project1:vn2',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'total_acl_rules': 3
                                },
                            }
                        }
                    ]
                },
            },

            # kfilt + sfilt + mfilt + cfilt + ackfilt
            {
                'kfilt': [
                    'default-domain:project1:*',
                    'default-domain:project2:vn1&',
                    'default-domain:project2:invalid'
                ],
                'sfilt': socket.gethostname()+'_1',
                'mfilt': 'Config:contrail-api:0',
                'cfilt': [
                    'UveVirtualNetworkConfig',
                    'UveVirtualNetworkAgent'
                ],
                'ackfilt': True,
                'uve_list_get': [
                    'default-domain:project1:vn1',
                    'default-domain:project1:vn2'
                ],
                'uve_get_post': {
                    'value': [
                        {
                            'name': 'default-domain:project1:vn1',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'partially_connected_networks': [
                                        'default-domain:project1:vn2'
                                    ],
                                    'total_acl_rules': 2
                                }
                            }
                        },
                        {
                            'name': 'default-domain:project1:vn2',
                            'value': {
                                'UveVirtualNetworkConfig': {
                                    'total_acl_rules': 3
                                },
                            }
                        }
                    ]
                },
            }
        ]

        vn_table = _OBJECT_TABLES[VN_TABLE].log_query_name

        for i in range(len(filt_test)):
            filters = dict(kfilt=filt_test[i].get('kfilt'),
                           sfilt=filt_test[i].get('sfilt'),
                           mfilt=filt_test[i].get('mfilt'),
                           cfilt=filt_test[i].get('cfilt'),
                           ackfilt=filt_test[i].get('ackfilt'))
            assert(vizd_obj.verify_uve_list(vn_table,
                filts=filters, exp_uve_list=filt_test[i]['uve_list_get']))
            assert(vizd_obj.verify_multi_uve_get(vn_table,
                filts=filters, exp_uves=filt_test[i]['uve_get_post']))
            assert(vizd_obj.verify_uve_post(vn_table,
                filts=filters, exp_uves=filt_test[i]['uve_get_post']))
    # end test_06_uve_filter

    #
    #               disk                compaction
    #              usage                tasks
    #                       |
    #                       |
    #              90   (severity=0)    400
    #                     LEVEL 0
    #              85   (severity=1)    300
    #                       |
    #                       |
    #                       |
    #                       |
    #              80   (severity=3)    200
    #                     LEVEL 1
    #              75   (severity=4)    150
    #                       |
    #                       |
    #                       |
    #                       |
    #             70    (severity 7)    100
    #                     LEVEL 2
    #             60    (severity x)     80
    #                       |
    #                       |
    def test_09_verify_db_info(self):
        logging.info('%%% test_09_verify_db_info %%%')

        vizd_obj = self.useFixture(
            AnalyticsFixture(logging,
                             builddir, 0,
                             redis_password='contrail'))
        assert vizd_obj.verify_on_setup()
        assert vizd_obj.set_opserver_db_info(vizd_obj.opserver,
                                             50, 90, 50, 90)
        assert vizd_obj.verify_collector_db_info(vizd_obj.collectors[0],
                                                 50, 90,
                                                 2147483647, 2147483647)

        logging.info('%%% test_09_verify_db_info - test#1 %%%')
        assert vizd_obj.set_opserver_db_info(vizd_obj.opserver,
                                             40, 50, 40, 50)
        assert vizd_obj.verify_collector_db_info(vizd_obj.collectors[0],
                                                 40, 50,
                                                 2147483647, 2147483647)

        logging.info('%%% test_09_verify_db_info - test#2 %%%')
        assert vizd_obj.set_opserver_db_info(vizd_obj.opserver,
                                             65, 120, 65, 120)
        assert vizd_obj.verify_collector_db_info(vizd_obj.collectors[0],
                                                 65, 120,
                                                 2147483647, 7)

        logging.info('%%% test_09_verify_db_info - test#3 %%%')
        assert vizd_obj.set_opserver_db_info(vizd_obj.opserver,
                                             72, 120, 72, 120)
        assert vizd_obj.verify_collector_db_info(vizd_obj.collectors[0],
                                                 72, 120,
                                                 7, 7)

        logging.info('%%% test_09_verify_db_info - test#4 %%%')
        assert vizd_obj.set_opserver_db_info(vizd_obj.opserver,
                                             87, 85, 87, 85)
        assert vizd_obj.verify_collector_db_info(vizd_obj.collectors[0],
                                                 87, 85,
                                                 3, 7)

        logging.info('%%% test_09_verify_db_info - test#5 %%%')
        assert vizd_obj.set_opserver_db_info(vizd_obj.opserver,
                                             45, 65, 45, 65)
        assert vizd_obj.verify_collector_db_info(vizd_obj.collectors[0],
                                                 45, 65,
                                                 2147483647, 2147483647)

        logging.info('%%% test_09_verify_db_info - test#6 %%%')
        assert vizd_obj.set_opserver_db_info(vizd_obj.opserver,
                                             pending_compaction_tasks_in = 250,
                                             disk_usage_percentage_out = 45,
                                             pending_compaction_tasks_out = 250)
        assert vizd_obj.verify_collector_db_info(vizd_obj.collectors[0],
                                                 45, 250,
                                                 2147483647, 3)

        return True
    # end test_09_verify_db_info

    #@unittest.skip('Skipping AnalyticsApiInfo UVE test')
    def test_10_analytics_api_info_uve(self):

        '''
        This test starts redis, vizd, opserver, qed, and a python generator
        that simulates analytics API

        Reads rest_api_ip and host_ip of OpServer as AnalyticsApiInfoUVE
        Test case doesn't invoke AnalyticsAPiInfo UVE add
        and UVE delete.

        '''
        logging.info("%%% test_10_analytics_api_info_uve %%%")

        vizd_obj = self.useFixture(
                AnalyticsFixture(logging, builddir, 0))
        table = _OBJECT_TABLES[COLLECTOR_INFO_TABLE].log_query_name
        assert vizd_obj.verify_on_setup()
        assert vizd_obj.verify_analytics_api_info_uve(
                    hostname = socket.gethostname(),
                    analytics_table = table,
                    rest_api_ip = '0.0.0.0',
                    host_ip = '127.0.0.1')
        return True

    #@unittest.skip('Skipping test_11_analytics_generator_timeout')
    def test_11_analytics_generator_timeout(self):

        '''
        This test starts redis, vizd, opserver, qed, and a python generator
        that simulates simulates vrouter.
        1. check vrouter generator in collector
        2. check generator successful connection
        2. delete vrouter generator in redis NGENERATORS
        3. send uve
        4. check generator successful connection again
        '''
        logging.info('%%% test_11_analytics_generator_timeout %%%')

        vizd_obj = self.useFixture(
            AnalyticsFixture(logging, builddir, 0))
        assert vizd_obj.verify_on_setup()
        collectors = [vizd_obj.get_collector()]
        generator_obj = self.useFixture(
            GeneratorFixture("contrail-vrouter-agent", collectors,
                             logging, vizd_obj.get_opserver_port()))
        assert generator_obj.verify_on_setup()

        source = socket.gethostname()
        exp_genlist = [
            source+':Analytics:contrail-collector:0',
            source+':Analytics:contrail-analytics-api:0',
            source+':Analytics:contrail-query-engine:0',
            source+':Test:contrail-vrouter-agent:0',
        ]
        assert vizd_obj.verify_generator_list(vizd_obj.collectors,
                                              exp_genlist)

        assert vizd_obj.verify_generator_connected_times(
                                            source+':Test:contrail-vrouter-agent:0', 1)
        assert vizd_obj.delete_generator_from_ngenerator(vizd_obj.collectors[0].get_redis_uve(),
                                                  source+':Test:contrail-vrouter-agent:0')
        generator_obj.send_vm_uve(vm_id='abcd',
                                  num_vm_ifs=1,
                                  msg_count=1)
        time.sleep(1)
        assert vizd_obj.verify_generator_connected_times(
                                            source+':Test:contrail-vrouter-agent:0', 2)
    # end test_11_verify_generator_timeout

    @staticmethod
    def get_free_port():
        cs = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cs.bind(("", 0))
        cport = cs.getsockname()[1]
        cs.close()
        return cport

    @staticmethod
    def _check_skip_kafka():
      
        (PLATFORM, VERSION, EXTRA) = platform.linux_distribution()
        if PLATFORM.lower() == 'ubuntu':
            if VERSION.find('12.') == 0:
                return True
        if PLATFORM.lower() == 'centos':
            if VERSION.find('6.') == 0:
                return True
        return False

def _term_handler(*_):
    raise IntSignal()

if __name__ == '__main__':
    gevent.signal(signal.SIGINT,_term_handler)
    unittest.main(catchbreak=True)
