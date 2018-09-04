Optional installation of some contrail Analytics Components
===
# 1.      Introduction
Contrail ```analytics``` and ```analytics_database``` role contains multiple components. This document provides details about how to make some analytics components' installation optional.


# 2.      Problem Statement
Currently all the analytics components are grouped under role ```analytics``` or ```analytics_database```, so even if some components are not required, we will be ending up installing that component.

# 3.      Proposed Solution

Installation of below components in Contrail analytics should be optional.
```
alarm-gen
kafka
zookeeper
snmp-collector
topology
cassandra
query-engine
```

In Contrail, a role is tied with multiple components inside it.
For example:
Role ```analytics``` implies below components:
```
api
collector
query-engine
alarm-gen
snmp-collector
topology
redis
nodemgr
```

Role ```analytics_database``` implies below components:
```
kafka
cassandra
zookeeper
nodemgr
```

So, to make it sync with existing approach, we are creating five additional roles to make above six components' installation optional.
```
analytics_alarm
analytics_query_engine
analytics_snmp
analytics_database_kafka
analytics_database_cassandra
```

With the above roles, different roles with components in analytics are depicted as below:

```
+-------------+
|             |
| +---------+ |
| |nodemgr  | |
| +---------+ |
| +---------+ |
| |redis    | |                                      +-------------+
| +---------+ |                                      |             |
| +---------+ |                                      | +---------+ |
| |api      | | +-------------+ +------------------+ | | snmp    | |
| +---------+ | |             | |                  | | +---------+ |
| +---------+ | | +---------+ | | +--------------+ | | +---------+ |
| |collector| | | | alarm   | | | | query-engine | | | | topology| |
| +---------+ | | +---------+ | | +--------------+ | | +---------+ |
|             | |             | |                  | |             |
|  analytics  | |  analytics_ | | analytics_       | | analytics_  |
|             | |  alarm      | | query_engine     | | snmp        |
+-------------+ +-------------+ +------------------+ +-------------+
```

And different roles with components in analyticsdb are depicted as below:
```
                                  +---------------+
                                  |               |
                                  | +-----------+ |
+-------------+ +---------------+ | | kafka     | |
|             | |               | | +-----------+ |
| +---------+ | | +-----------+ | | +-----------+ |
| |nodemgr  | | | | cassandra | | | | zookeeper | |
| +---------+ | | +-----------+ | | +-----------+ |
|             | |               | |               |
| analyticsdb | | analyticsdb_  | | analyticsdb_  |
|             | | cassandra     | | kafka         |
+-------------+ +---------------+ +---------------+
```

```analytics_alarm``` role implies analytics ```alarm``` component
```analytics_snmp``` role implies analytics ```snmp-collector``` and ```topology```
components
```analytics_query_engine``` role implies analytics ```query-engine``` component
```analytics_database_kafka``` role implies analytics external ```kafka``` and ```zookeeper``` component
```analytics_database_cassandra``` role implies analytics external ```cassandra``` component

# 3.1    Alternatives considered
In stead of role, we could have used some boolean flag to enable/disable some components. But this will deviate from existing approach in ansible as well as other deployments (openshift, helm, openshift etc). So we did not consider that approach.

# 3.2    API schema changes
The below REST GET APIs should not be visible in ```api``` if ```analytics_alarm``` role is not provisioned.

```
/analytics/alarms
/analytics/alarm-stream
/analytics/uve-stream
````

If ```analytics_query_engine``` is not provisioned, then the below REST APIs should not be visible in ```api```

GET API
```
/analytics/tables
/analytics/queries
```
POST API
```
/analytics/query
```
# 3.3      User workflow impact
None

## 3.4      UI Changes
If ```analytics_alarm``` role is not provisioned, then Contrail UI should not show below references of alarm,
1. Global Alarm (Next to Logged in User)
2. Monitor -> Alarms
3. Configure -> Alarms

If ```contrail_snmp``` role is not provisioned, then Contrail UI should not show below reference of Physical Topology
1. Infrastructure -> Physical Topology

If ```contrail_query_engine``` is not provisioned, then Contrail UI should not show Query Page
# 4 Implementation

## 4.1      Work items
### 4.1.1 Changes in contrail-ansible-deployer
Five new roles are added as discussed in [Proposed Solution](https://github.com/biswajit-mandal/contrail-web-controller/blob/master/specs/introspect_proxy_without_login.md#33------user-workflow-impact) Section
```
analytics_alarm
analytics_snmp
analytics_query_engine
analytics_database_kafka
analytics_database_cassandra
```
If any of the above role is not configured in a node, then we should not show the processes for that role in ```contrail-status```
To do that, we have added five new environment variables in ```/etc/contrail/common.env```.
```
ENABLE_ANALYTICS_ALARM
ENABLE_ANALYTICS_SNMP
ENABLE_ANALYTICS_QUERY_ENGINE
ENABLE_ANALYTICS_DATABASE_KAFKA
ENABLE_ANALYTICS_DATABASE_CASSANDRA
```
which are used to to turn on/off the display of the contrail components status in ```contrail-status```.

### 4.1.1 Changes in contrail-container-builder
```alarm-gen```, ```api```, ```collector```, ```snmp-collector``` and ```topology``` use ```zookeeper``` from ```analytics_database```. With this change, all of them use ```config_database``` zookeeper nodes (```ZOOKEEPER_SERVERS```)

The env-file ```/etc/contrail/common.env``` is passed along with contrail-status ```docker run``` arguments
```docker run --rm --name contrail-status -v $vol_opts --pid host --env-file /etc/contrail/common.env --net host --privileged ${CONTRAIL_STATUS_IMAGE}```
And internally above environment variables are used to show or not show the status of these analytics components.

If any of the above optional role is not provisioned, then corresponding analytics component related configuration should not be available in other component's individual
configuration file.
For ex:
If ```analytics_database_cassandra``` is not provisioned, then contrail-collector.conf file should not have ```DATABASE``` section.
That is taken care by using below five environment variables:
```
ENABLE_GLOBAL_ANALYTICS_ALARM
ENABLE_GLOBAL_ANALYTICS_SNMP
ENABLE_GLOBAL_ANALYTICS_QUERY_ENGINE
ENABLE_GLOBAL_ANALYTICS_DATABASE_KAFKA
ENABLE_GLOBAL_ANALYTICS_DATABASE_CASSANDRA
```


### 4.1.1 Changes in nodemgr
If any of the optional role is not provisioned, then nodemgr should not send NodeStatus UVE for the corresponding components.
That is achieved by using the above five flags.

# 5 Performance and Scaling Impact
None

## 5.1     API and control plane Performance Impact
None

## 5.2     Forwarding Plane Performance
None

# 6 Upgrade
During upgrade, we need to make sure that if some optional role is not provisioned which was provisioned earlier, should get removed.

# 7       Deprecations
None

# 8       Dependencies
None

# 9       Testing
## 9.1    Dev Tests
1. Do not assign the new roles, contrail-analytics should work fine and contrail-analytics should show all expected processes (api, collector, redis) active.
2. Assign ```analytics_alarm``` and ```analytics_snmp``` role in a node where role ```analytics``` is also assigned, contrail-analytics should work fine and contrail-status should show all expected processes (api, collector, redis, alarm-gen, kafka, snmp, topology) active.
3. Assign ```analytics_database_kafka``` role in a node where ```analytics_database``` role is also assigned, contrail-analytics should work fine and contrail-status should show all expected processes (kafka, zookeeper) active.
4. Do not assign ```analytics_database_cassandra``` and ```analytics_database_kafka```, then ```zookeeper``` from analytics_database should not get installed.
5. Assign ```analytics_database_kafka``` role, then only ```zookeeper``` from analytics_database should get installed.
6. In a multi-node setup, configure ```config_database``` role in a seperate node than a node where```analytics```, ```analytics_alarm```, ```analytics_snmp``` roles are configued. Verify that all the components use ```zookeeper``` from ```config_database```.

# 10      Documentation Impact
The optional roles ```analytics_alarm```, ```analytics_snmp```, ```analytics_query_engine```  must be added in the node where ```analytics``` role is also added.
Similarly ```analytics_database_kafka``` and ```analytics_database_cassandra``` also must be added in the node where ```analytics_database``` role is also added.


# 11      References

