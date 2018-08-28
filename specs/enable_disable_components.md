Enable/disable Contrail Analytics Components
===
# 1.      Introduction
Contrail Analytics does have the below components:
```
api
collector
query-engine
alarm-gen
snmp-collector
topology
```
Above components are tightly coupled with the role ```analytics```

Contrail Analytics database have the below components:
```
kafka
cassandra
zookeeper
```
Above components are tightly coupled with the role ```analytics_database```


# 2.      Problem Statement
Currently all the analytics components are grouped under role ```analytics``` or ```analytics_database```, so even if some components are not required, we will be ending up installing that component.

# 3.      Proposed Solution

Installation of below components in Contrail analytics should be optional.
```
alarm-gen
kafka
snmp-collector
topology
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
```

Role ```analytics_database``` implies below components:
```
kafka
cassandra
zookeeper
```

So, to make it sync with existing approach, we are creating three additional roles to make above four components' installation optional.
```
analytics_alarm
analytics_database_kafka
analytics_snmp
```

```analytics_alarm``` role contains analytics ```alarm``` component
```analytics_database_kafka``` role contains analytics external ```kafka``` component
```analytics_snmp``` role contains analytics ```snmp-collector``` and ```topology``` components

# 3.1    Alternatives considered
None

# 3.2    API schema changes
The below APIs should not be visible in ```api``` if ```alarm-gen``` is not installed.
```
/analytics/alarms
/analytics/alarm-stream
````

# 3.3      User workflow impact
None

## 3.4      UI Changes
If ```analytics_alarm``` role is not provisioned, then Contrail UI should not show below references of alarm,
1. Global Alarm (Next to Logged in User)
2. Monitor -> Alarms
3. Configure -> Alarms

If ```contrail_snmp``` role is not provisioned, then Contrail UI should not show below reference of Physical Topology
1. Infrastructure -> Physical Topology

# 4 Implementation

## 4.1      Work items
### 4.1.1 Changes in contrail-ansible-deployer
Three new roles are added as discussed in [Proposed Solution](https://github.com/Juniper/contrail-analytics/blob/master/specs/enable_disable_components.md#3------proposed-solution) Section
```
analytics_alarm
analytics_database_kafka
analytics_snmp
```
As kafka can be installed irrespective of the node where analytics_database role is configured, so a new variable is added ```ANALYTICSDB_KAFKA_NODES``` which denote the kafka_nodes.

If any of the above role is not configured in a node, then we should not show the processes for that role in ```contrail-status```
To do that, we have added three new environment variables in ```/etc/contrail/common.env```.
```
ENABLE_ANALYTICS_ALARM
ENABLE_ANALYTICS_DATABASE_KAFKA
ENABLE_ANALYTICS_SNMP
```
which are used to to turn on/off the display of the contrail components status in ```contrail-status```.

### 4.1.1 Changes in contrail-container-builder
alarm-gen and collector use kafka. The kafka node details in configuration file ```contrail-collector.conf``` for collector and ```contrail-alarm-gen.conf``` for alarm-gen process are populated by ```ANALYTICSDB_KAFKA_NODES```.

This env-file ```/etc/contrail/common.env``` is passed along with contrail-status ```docker run``` arguments
```docker run --rm --name contrail-status -v $vol_opts --pid host --env-file /etc/contrail/common.env --net host --privileged ${CONTRAIL_STATUS_IMAGE}```
And internally these variables are used to show or not show the status of these analytics components.

# 5 Performance and Scaling Impact
None

## 5.1     API and control plane Performance Impact
None

## 5.2     Forwarding Plane Performance
None

# 6 Upgrade
None

# 7       Deprecations
None

# 8       Dependencies
None

# 9       Testing
## 9.1    Dev Tests
1. Do not assign the new roles, contrail-analytics should work fine and contrail-analytics should show all processes UP.
2. Assign ```analytics_alarm``` and ```analytics_snmp``` role in a node where role ```analytics``` is also assigned, contrail-analytics should work fine and contrail-status should show all processes UP.
3. Assign ```analytics_database_kafka``` role in a node where ```analytics_database``` role is also assigned, contrail-analytics should work fine and contrail-status should show all processes UP.

# 10      Documentation Impact
The new roles ```analytics_alarm``` and ```analytics_snmp``` must be added in the node where ```analytics``` role is also added.
Similarly ```analytics_database_kafka``` also must be added in the node where ```analytics_database``` role is also added.


# 11      References

