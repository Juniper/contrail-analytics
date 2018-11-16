Optional installation of some contrail Analytics Components
===
# 1.      Introduction
Contrail ```analytics``` and ```analytics_database``` role contains multiple components.
This document provides details about how to make below analytics components installation optional.
```
alarm-gen
kafka
snmp-collector
topology
cassandra
query-engine
```


# 2.      Problem Statement
Currently all the analytics components are grouped under role ```analytics``` or ```analytics_database```,
so even if some components are not required, we will be ending up installing that component.

# 3.      Proposed Solution

Installation of below components in Contrail analytics should be optional.
```
alarm-gen
kafka
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

So, to make it sync with existing approach, we are creating two additional roles to make above six components' installation optional.
```
analytics_alarm
analytics_snmp
```
along with ```analytics``` and ```analytics_database``` role.

With the above roles, different roles with components in analytics are depicted as below:

```
+-------------+
|             |
| +---------+ |
| |nodemgr  | | +-------------+ +-------------+ +---------------+
| +---------+ | |             | |             | |               |
| +---------+ | | +---------+ | | +---------+ | | +-----------+ |
| |redis    | | | |nodemgr  | | | |nodemgr  | | | |nodemgr    | |
| +---------+ | | +---------+ | | +---------+ | | +-----------+ |
| +---------+ | | +---------+ | | +---------+ | | +-----------+ |
| |api      | | | |alarm    | | | |snmp     | | | | query     | |
| +---------+ | | +---------+ | | +---------+ | | +-----------+ |
| +---------+ | | +---------+ | | +---------+ | | +-----------+ |
| |collector| | | |kafka    | | | |topology | | | | cassandra | |
| +---------+ | | +---------+ | | +---------+ | | +-----------+ |
|             | |             | |             | |               |
|  analytics  | |  analytics_ | | analytics_  | | analytics_    |
|             | |  alarm      | | snmp        | | database      |
+-------------+ +-------------+ +-------------+ +---------------+
```

```analytics_alarm``` role implies ```alarm```, ```kafka``` components
```analytics_snmp``` role implies analytics ```snmp-collector``` and ```topology``` components
```analytics_database``` role implies analytics ```query``` and ```cassandra``` components

```zookeeper``` component is removed from ```analytics_database``` role.

# 3.1    Alternatives considered
In stead of role, we could have used some boolean flag to enable/disable some components.
But this will deviate from existing approach in ansible as well as other deployments
(openshift, helm, openshift etc). So we did not consider that approach.

# 3.2    API changes
The below APIs should not be visible in ```api``` if ```alarm-gen``` is not installed.
```
/analytics/alarms
/analytics/alarm-stream
/analytics/uve-stream
````

If ```analytics_database``` is not provisioned, then the below REST APIs should not be visible in ```api```

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

If ```analytics_snmp``` role is not provisioned, then Contrail UI should not show below reference of Physical Topology
1. Infrastructure -> Physical Topology

If ```analytics_database``` is not provisioned, then Contrail UI should not show Query Page
# 4 Implementation

## 4.1      Work items
### 4.1.1 Changes in Config Schema
Two new node types will be defined in Config Schema.
```analytics-alarm-node```
```analytics-snmp-node```
with parent as ```global-system-config```

### 4.1.2 Changes in contrail-ansible-deployer
Two new roles are added as discussed in [Proposed Solution](https://github.com/Juniper/contrail-analytics/blob/master/specs/analytics_optional_components.md#3------proposed-solution) Section
```
analytics_alarm
analytics_snmp
```
If any of the above role is not configured in a node, then we should not show the processes for that role in ```contrail-status```

### 4.1.3 Changes in contrail-container-builder

```alarm-gen```, ```api```, ```collector```, ```snmp-collector```, ```topology``` and ```kafka``` use
```zookeeper``` from ```analytics_database```. With this change, all of them will use ```config_database```
zookeeper nodes (```ZOOKEEPER_SERVERS```). ```zookeeper``` component is removed from ```analytics_database``` role.

If any of the above optional role is not provisioned, then corresponding analytics component related configuration
should not be available in other component's individual configuration file.
For example:
If ```analytics_database``` is not provisioned, then contrail-collector.conf file should not have ```DATABASE``` section.

### 4.1.4 Changes in nodemgr
If any of the optional role is not provisioned, then nodemgr should not send NodeStatus UVE for the corresponding components.

We will be adding two module types (module identifier to event manager):
```
ANALYTICS_ALARM_NODE_MGR
ANALYTICS_SNMP_NODE_MGR
```

### 4.1.5 Changes in Sandesh
In viz.sandesh, two Object tables are created, ```ObjectAnalyticsAlarmInfo``` and ```ObjectAnalyticsSNMPInfo```
In vns.sandesh, the Sandesh port for ```analytics-alarm-nodemgr``` and ```analytics-snmp-nodemgr``` are defined as below:
```
const u16 HttpPortAnalyticsAlarmNodemgr = 8113
const u16 HttpPortAnalyticsSNMPNodemgr = 8114
```

### 4.1.6 Changes in Other Deployers
Other deployers like contrail-helm-deployer, openshift-ansible, tripleo, also need to have similar changes.

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
1. Do not assign the new roles, contrail-analytics should work fine and contrail-analytics should show
   all expected processes (api, collector, redis) active.
2. Assign ```analytics_alarm``` and ```analytics_snmp``` role in a node where role ```analytics``` is not assigned,
   contrail-analytics should work fine and contrail-status should show all expected processes (api, collector,
   redis, alarm-gen, kafka, snmp, topology) active.
3. In a multi-node setup, configure ```config_database``` role in a seperate node than a node where```analytics```,
   ```analytics_alarm```, ```analytics_snmp``` roles are configued. Verify that all the components use
   ```zookeeper``` from ```config_database```.

# 10      Documentation Impact

# 11      References

