import json
import uuid
from sandesh.viz.constants import *
from opserver_util import OpServerUtils
import copy

class PolicyRule(object):
    def __init__(self, match_tags, ep1, ep2, direction):
        self.match_tags = match_tags
        self.endpoint_1 = ep1
        self.endpoint_2 = ep2
        self.direction = direction
    def __eq__(self, another):
        return (self.match_tags['tag_list_list'] == another.match_tags['tag_list_list'] and
                self.endpoint_1['tags'] == another.endpoint_1['tags'] and
                self.endpoint_2['tags'] == another.endpoint_2['tags'] and
                self.direction == another.direction)
    def __hash__(self):
        return hash((', '.join(self.match_tags['tag_list_list']),
                     ', '.join(self.endpoint_1['tags']), 
                     ', '.join(self.endpoint_2['tags']),
                     self.direction))
    def __repr__(self):
        return str(self.__dict__)
    def __str__(self):
        return str(self.__dict__)


class PolicyGenerator(object):

    def __init__(self, analytics_api_ip,
                 analytics_api_port, user, password, vnc_api_client, logger):
        self._analytics_api_ip = analytics_api_ip
        self._analytics_api_port = analytics_api_port
        self._user = user
        self._password = password
        self._logger = logger
        self._vnc_api_client = vnc_api_client
        self._sessions = {}

    def _get_tags(self, token, detail=True):
        tag_objs = self._vnc_api_client.get_resource_list("tag", token, detail=True)
        tags = []
        for tag_obj in tag_objs:
            tags.append({'tag_type_name': tag_obj._tag_type_name,
                         'tag_id': tag_obj._tag_id,
                         'fq_name': tag_obj.fq_name,
                         'tag_name': ':'.join(tag_obj.fq_name)})
        return tags

    def process_request(self, request, token):
        self._tags = self._get_tags(token)
        self._logger.error('TAGS: {}'.format(self._tags))
        session_id = request.get('session_id')
        if not session_id:
            session_id = request['session_id'] = str(uuid.uuid4())
            self._logger.error('No session_id provided, new session id: {}'.format(session_id))
        consolidate = request['consolidate'] = request.get('consolidate', False)
        aps_req = {}
        if not session_id in self._sessions:
            self._sessions[session_id] = {}
            aps_req, self._sessions[session_id]['results'] = self._get_session_records(request)
        results = self._sessions[session_id]['results']
        if not results:
            return json.dumps({'QueryParams': request, 'application-policy-sets': []})
        aps_list = self._generate_aps_list(results)
        return self._send_response(request, aps_req, aps_list)

    def _get_session_records(self, query_params):
        project = query_params.get('project')
        start_time = query_params.get('start_time')
        end_time = query_params.get('end_time')
        aps_list = query_params.get('aps_list')
        security_policy_rule_list = []
        aps = {}
        if aps_list:
            for aps_info in aps_list:
                application = aps_info['application']
                aps[application] = {}
                if aps_info.get('name'): 
                    aps[application]['name'] = aps_info['name']
                if aps_info.get('policy_rule_uuid'):
                    security_policy_rule_list.append(aps_info['policy_rule_uuid'])
        select_list = ['application', 'site', 'deployment', 'tier',
                       'remote_application', 'remote_site', 'remote_deployment',
                       'remote_tier', 'server_port', 'protocol']
        where_list = []
        if project:
            where_list.append(OpServerUtils.Match(
                name='vmi', value=project,
                op=OpServerUtils.MatchOp.PREFIX).__dict__)
        if aps:
            for app in aps:
                where_list.append(OpServerUtils.Match(
                    name='application', value=app,
                    op=OpServerUtils.MatchOp.EQUAL).__dict__)
        if security_policy_rule_list:
            for security_policy_rule in security_policy_rule_list:
                where_list.append(OpServerUtils.Match(
                    name='security_policy_rule', value=security_policy_rule,
                    op=OpServerUtils.MatchOp.PREFIX).__dict__)

        if where_list:
            where_clause = [where_list]
        else:
            where_clause = None
        session_query = OpServerUtils.Query(table=SESSION_SERIES_TABLE,
                start_time=start_time, end_time=end_time,
                select_fields=select_list, where=where_clause, session_type='client',
                is_service_instance=0)
        return aps, self._send_query(json.dumps(session_query.__dict__))

    def _send_query(self, query):
        """Post the query to the analytics-api server and returns the
        response."""
        self._logger.error('Sending query: %s' % (query))
        opserver_url = OpServerUtils.opserver_query_url(self._analytics_api_ip,
                           str(self._analytics_api_port))
        resp = OpServerUtils.post_url_http(opserver_url, query, self._user,
            self._password, True)
        try:
            resp = json.loads(resp)
            value = resp['value']
        except (TypeError, ValueError, KeyError):
            raise _QueryError(query)
        return value

    def _translate_tag_names_to_name(self, app_name, site_name, dep_name, tier_name):
        app, site, dep, tier  = app_name, site_name, dep_name, tier_name
        for tag in self._tags:
            if tag['tag_type_name'] == 'application' and\
                    tag['tag_name'] == app_name:
                if len(tag['fq_name']) == 1:
                    app = 'global:' + tag['tag_name']
                else:   
                    app = tag['tag_name']
                continue
            if tag['tag_type_name'] == 'site' and\
                    tag['tag_name'] == site_name:
                if len(tag['fq_name']) == 1:
                    site = 'global:' + tag['tag_name']
                else:   
                    site = tag['tag_name']
                continue
            if tag['tag_type_name'] == 'deployment' and\
                    tag['tag_name'] == dep_name:
                if len(tag['fq_name']) == 1:
                    dep = 'global:' + tag['tag_name']
                else:   
                    dep = tag['tag_name']
                continue
            if tag['tag_type_name'] == 'tier' and\
                    tag['tag_name'] == tier_name:
                if len(tag['fq_name']) == 1:
                    tier = 'global:' + tag['tag_name']
                else:   
                    tier = tag['tag_name']
                continue
        return app, site, dep, tier

    def _translate_tag_ids_to_name(self, app_id, site_id, dep_id, tier_id):
        app, site, dep, tier  = app_id, site_id, dep_id, tier_id
        for tag in self._tags:
            if tag['tag_type_name'] == 'application' and\
                    tag['tag_id'] == app_id:
                if len(tag['fq_name']) == 1:
                    app = 'global:' + tag['tag_name']
                else:
                    app = tag['tag_name']
                continue
            if tag['tag_type_name'] == 'site' and\
                    tag['tag_id'] == site_id:
                if len(tag['fq_name']) == 1:
                    site = 'global:' + tag['tag_name']
                else:
                    site = tag['tag_name']
                continue
            if tag['tag_type_name'] == 'deployment' and\
                    tag['tag_id'] == dep_id:
                if len(tag['fq_name']) == 1:
                    dep = 'global:' + tag['tag_name']
                else:
                    dep = tag['tag_name']
                continue
            if tag['tag_type_name'] == 'tier' and\
                    tag['tag_id'] == tier_id:
                if len(tag['fq_name']) == 1:
                    tier = 'global:' + tag['tag_name']
                else:
                    tier = tag['ta_name']
                continue
        return app, site, dep, tier

    def _generate_aps_list(self, results):
        application_policy_list = {}
        for record in results:
            app, site, dep, tier, r_app, r_site, r_dep, r_tier =\
                record['application'], record['site'],\
                record['deployment'], record['tier'],\
                record['remote_application'], record['remote_site'],\
                record['remote_deployment'], record['remote_tier']
            app, site, dep, tier = self._translate_tag_names_to_name(
                record['application'], record['site'],
                record['deployment'], record['tier'])
            r_app, r_site, r_dep, r_tier = self._translate_tag_ids_to_name(
                record['remote_application'], record['remote_site'],
                record['remote_deployment'], record['remote_tier'])
            if '__UNKNOWN__' in [app, site, dep, tier, r_app, r_site, r_dep, r_tier]:
                continue
            service = '{}:any:{}'.format(OpServerUtils.ip_protocol_to_str(
                record['protocol']), record['server_port'])
            policy_rule = self._create_policy_rule(
                app, site, dep, tier, r_app, r_site, r_dep, r_tier)
            if not application_policy_list.get(app):
                application_policy_list[app] = [{'name': 'FW_Policy1',
                                                 'rules': {}}]
            #if not policy_rule in application_policy_list[app][0]['rules']:
            #    self._logger.error('found new rule: {}'.format(policy_rule))
            #    application_policy_list[app][0]['rules'][policy_rule] = set([service])
            #    self._logger.error('services: {}'.format(application_policy_list[app][0]['rules'][policy_rule]))
            #else:
            #    self._logger.error('found existing rule: {}'.format(policy_rule))
            #    application_policy_list[app][0]['rules'][policy_rule].add(service)
            #    self._logger.error('services: {}'.format(application_policy_list[app][0]['rules'][policy_rule]))
            application_policy_list[app][0]['rules'].setdefault(policy_rule, set([])).add(service)
        return application_policy_list

    def _create_policy_rule(self, app, site, dep, tier,
                            r_app, r_site, r_dep, r_tier):
        match_tags = ['', '', '', '']
        if app == r_app:
            match_tags[0] = 'application'
        if site == r_site:
            match_tags[1] = 'site'
        if dep == r_dep:
            match_tags[2] = 'deployment'
        if tier == r_tier:
            match_tags[3] = 'tier'

        local_ep = ['', '', '', '']
        remote_ep = ['', '', '', '']
        if not match_tags[0]:
            local_ep[0] = app; remote_ep[0] = r_app
        if not match_tags[1]:
            local_ep[1] = site; remote_ep[1] = r_site
        if not match_tags[2]:
            local_ep[2] = dep; remote_ep[2] = r_dep
        if not match_tags[3]:
            local_ep[3] = tier; remote_ep[3] = r_tier

        match_tags = {'tag_list_list': [attr for attr in match_tags if attr],
                      'tag_list': ','.join([attr for attr in match_tags if attr])}
        endpoint_1 = {'tags': [attr for attr in local_ep if attr]}
        endpoint_2 = {'tags': [attr for attr in remote_ep if attr]}
        direction = '>'

        return PolicyRule(match_tags, endpoint_1, endpoint_2, direction)

    def _send_response(self, query_params, aps_req, aps_list):
        session_id = query_params['session_id']
        consolidate = query_params['consolidate']
        policy_gen_response = {'QueryParams': query_params}
        aps_data = []
        idx = 1
        for app, policies in aps_list.iteritems():
            policies_resp = [{'firewall_policy': {'name': 'AUTO_FW_Policy1' + str(idx),
                                                  'firewall-rules': []}}]
            for rule, services in policies[0]['rules'].iteritems():
                policy = policies_resp[0]['firewall_policy']
                rule_resp = rule.__dict__
                if consolidate:
                    rule_resp['services'] = services
                    policy['firewall-rules'].append({'firewall-rule': rule_resp})
                else:
                    for service in services:
                        rule_resp_copy = copy.deepcopy(rule_resp)
                        rule_resp_copy['services'] = [service]
                        rule_resp_copy['service'] = service
                        policy['firewall-rules'].append({'firewall-rule': rule_resp_copy})
            aps_app = app if not app.startswith('global:') else app[7:]
            aps_resp = {'application': aps_app,
                        'firewall_policies': policies_resp}
            if aps_req and aps_req.get(app) and aps_req[app]['name']:
                aps_resp['name'] = aps_req[app]['name']
            else:
                try:
                    aps_resp['name'] = 'AUTO_' + app.split('=', 1)[1].upper() + '_Policy'
                    aps_resp['firewall_policies'][0]['firewall_policy']['name'] =\
                        'AUTO_' + app.split('=', 1)[1].upper() + '_FW_Policy'
                except:
                    aps_resp['name'] = 'AUTO_Policy_' + str(idx)
                    idx += 1
            aps_data.append({'application-policy-set':aps_resp})
        self._sessions[session_id]['aps_list'] = aps_data
        policy_gen_response['application-policy-sets'] = aps_data
        self._logger.error('aps_data: {}'.format(aps_req))
        return json.dumps(policy_gen_response)
