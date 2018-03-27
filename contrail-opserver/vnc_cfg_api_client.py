#
# Copyright (c) 2016 Juniper Networks, Inc. All rights reserved.
#

import time
import requests
import bottle
from pysandesh.connection_info import ConnectionState
from pysandesh.gen_py.process_info.ttypes import ConnectionType,\
    ConnectionStatus
from vnc_api import vnc_api
from functools import wraps

class VncCfgApiClient(object):

    config_obj_to_fq_name_prefix_map = {
        'alarm': 'default-global-system-config',
        'analytics_node': 'default-global-system-config',
        'api_access_list': 'default-global-system-config',
        'application_policy_set': 'default-policy-management',
        'bgp_router': 'default-domain:default-project:ip-fabric:__default__',
        'config_node': 'default-global-system-config',
        'database_node': 'default-global-system-config',
        'discovery_service_assignment': 'default-discovery-service-assignment',
        'firewall_policy': 'default-policy-management',
        'global_qos_config': 'default-global-system-config',
        'global_system_config': 'default-global-system-config',
        'global_vrouter_config': 'default-global-system-config',
        'policy_management': 'default-policy-management',
        'route_target': 'target',
        'service_appliance_set': 'default-global-system-config',
        'service_templete': 'default-domain',
        'tag_type': '',
        'virtual_machine_interfcae': 'default-global-system-config',
        'virtual_router': 'default-global-system-config'
    }

    def __init__(self, conf_info, sandesh_instance, logger):
        self._conf_info = conf_info
        self._sandesh_instance = sandesh_instance
        self._logger = logger
        self._vnc_api_client = None
    # end __init__

    def _update_connection_state(self, status, message = ''):
        ConnectionState.update(conn_type=ConnectionType.APISERVER, name='',
            status=status, message=message,
            server_addrs=self._conf_info['api_servers'])
    # end _update_connection_state

    def check_client_presence(func):
        @wraps(func)
        def impl(self, *f_args, **f_kwargs):
            if not self._vnc_api_client:
                content = 'Not able to connect to VNC API: %s' % \
                    (' '.join(self._conf_info['api_servers']))
                raise bottle.HTTPResponse(status = 503, body = content)
            return func(self, *f_args, **f_kwargs)
        return impl
    # end check_client_presence

    @check_client_presence
    def _get_user_token_info(self, user_token, uuid=None):
        return self._vnc_api_client.obj_perms(user_token, uuid)
    # end _get_user_token_info

    @check_client_presence
    def _get_resource_list(self, obj_type, token):
        return self._vnc_api_client.resource_list(obj_type, token=token)
    # end _get_resource_list

    def update_api_servers(self, api_servers):
        self._conf_info['api_servers'] = api_servers
        self._vnc_api_client = None
        self.connect()
    # end update_api_servers

    def connect(self):
        # Retry till API server is up
        connected = False
        api_server_list = [s.split(':')[0] for s in self._conf_info['api_servers']]
        api_server_port = self._conf_info['api_servers'][0].split(':')[1] \
            if self._conf_info['api_servers'] else None
        self._update_connection_state(ConnectionStatus.INIT)
        while not connected:
            try:
                self._vnc_api_client = vnc_api.VncApi(
                    self._conf_info['admin_user'],
                    self._conf_info['admin_password'],
                    self._conf_info['admin_tenant_name'],
                    api_server_list, api_server_port,
                    api_server_use_ssl=self._conf_info['api_server_use_ssl'],
                    auth_host=self._conf_info['auth_host'],
                    auth_port=self._conf_info['auth_port'],
                    auth_protocol=self._conf_info['auth_protocol'])
                connected = True
                self._update_connection_state(ConnectionStatus.UP)
            except Exception as e:
                # Update connection info
                self._update_connection_state(ConnectionStatus.DOWN, str(e))
                time.sleep(3)
    # end connect

    def get_obj_perms_from_name(self, name, cfg_type, token):
        try:
            uuid = None
            rv_obj_perms = None
            if name.count(":") == 0:
                fq_name = [self.config_obj_to_fq_name_prefix_map[cfg_type], name]
            else:
                fq_name = name.split(":")
            uuid = self._vnc_api_client.fq_name_to_id(cfg_type, fq_name)
            self._logger.info("name:%s fq_name:%s uuid:%s" % (name, fq_name, uuid))
        except Exception as e:
            self._logger.error("fq_name_to_id: Exception: %s", str(e))
        else:
            rv_obj_perms = self._vnc_api_client.obj_perms(token, uuid)
        return rv_obj_perms
    # end get_obj_perms_from_name

    def get_resource_list(self, obj_type, token):
        try:
            res_list = self._get_resource_list(obj_type, token)
        except Exception as e:
            self._logger.error('VNC Config API Client NOT FOUND: %s' % str(e))
            return dict()
        else:
            return res_list
    # end get_resource_list

    def is_role_cloud_admin(self, user_token, user_token_info=None):
        result = self._get_user_token_info(user_token)
        if not result or not result['token_info']:
            self._logger.error(
                    'Token info for %s NOT FOUND' % str(user_token))
            return False
        # Handle v2 and v3 responses
        token_info = result['token_info']
        if user_token_info is not None:
            user_token_info.update(result)
        if 'access' in token_info:
            roles_list = [roles['name'] for roles in \
                    token_info['access']['user']['roles']]
        elif 'token' in token_info:
            roles_list = [roles['name'] for roles in \
                    token_info['token']['roles']]
        else:
            self._logger.error('Role info for %s NOT FOUND: %s' % \
                    (str(user_token), str(token_info)))
            return False
        return self._conf_info['cloud_admin_role'] in roles_list
    # end is_role_cloud_admin

# end class VncCfgApiServer
