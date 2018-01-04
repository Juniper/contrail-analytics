# 1. Introduction
Currently all the stats collected by collector consists of a number of tags against which the stat is to be indexed. With the current schema, we need to do as many writes as the number of tags for the stat.

# 2. Problem statement
Currently all the stats collected by collector consists of a number of tags against which the stat is to be indexed. With the current schema, we need to do as many writes as the number of tags for the stat. If high number of stats are sent to collector, it will scheme will not scale. Hence, the number of writes per stat should be reduced.

# 3. Proposed solution
Currently we do one write in database per tag. Instead, we can create an encoded string in **tag1=value1;tag2=value2;tag3=value3...** format. We will have 4 such fields and each tag will go into 1 of the four buckets depending on the hashing of the tag name. Apart from that we will have separate columns for well-known tags like name, source, key and proxy. we will index the encoded tags string, name, source and key fields with SASI index, which will allow these fields to be queried. The new schema will look like below -  

```
CREATE TABLE "ContrailAnalyticsCql".stattablev4 (
    key int,              \\ T2
    key2 int,             \\ partition_number
    key3 text,            \\ StatName
    key4 text,            \\ StatAttr
    column1 int,          \\ T1
    column2 uuid,         \\ UUID
    column3 text,         \\ T2:name
    column4 text,         \\ T2:source
    column5 text,         \\ T2:key
    column6 text,         \\ T2:proxy
    column7 text,         \\ T2:tag1=value1;tag2=value2;..
    column8 text,         \\ T2:tag1=value1;tag2=value2;..
    column9 text,         \\ T2:tag1=value1;tag2=value2;..
    column10 text,        \\ T2:tag1=value1;tag2=value2;..
    value text,           \\ value
    PRIMARY KEY ((key, key2, key3, key4), column1, column2)
) WITH CLUSTERING ORDER BY (column1 ASC, column2 ASC)

CREATE CUSTOM INDEX stattablev4_column3_idx ON "ContrailAnalyticsCql".stattablev4 (column3) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode': 'PREFIX'};
CREATE CUSTOM INDEX stattablev4_column4_idx ON "ContrailAronalyticsCql".stattablev4 (column4) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode': 'PREFIX'};
CREATE CUSTOM INDEX stattablev4_column5_idx ON "ContrailAnalyticsCql".stattablev4 (column5) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode': 'PREFIX'};
CREATE CUSTOM INDEX stattablev4_column6_idx ON "ContrailAnalyticsCql".stattablev4 (column6) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode': 'PREFIX'};
CREATE CUSTOM INDEX stattablev4_column7_idx ON "ContrailAnalyticsCql".stattablev4 (column7) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode': 'CONTAINS'};
CREATE CUSTOM INDEX stattablev4_column8_idx ON "ContrailAnalyticsCql".stattablev4 (column8) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode': 'CONTAINS'};
CREATE CUSTOM INDEX stattablev4_column9_idx ON "ContrailAnalyticsCql".stattablev4 (column9) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode': 'CONTAINS'};
CREATE CUSTOM INDEX stattablev4_column10_idx ON "ContrailAnalyticsCql".stattablev4 (column10) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode': 'CONTAINS'};
```

In Query-Engine, currently we do as many queries as number of where clauses for tags. Now
In each query, we will have where clause like - **column7 LIKE %tag_name=value%**. Each query may have one or more such LIKE clauses depending on the number if tags queried and in which of the 4 tags fields these tags reside. So for example, if the query has 4 tags and all of them hash into different tag fields, cassandra query will have 4 such LIKE clauses. This way number of queries would be reduced to 1/4. If there are more than one tags that are in same tag_field are queried, this will result into multiple cassandra queries, each one of them will have a LIKE CLAUSE for one tag.

## 3.1 Alternatives considered
None
## 3.2 API schema changes
None
## 3.3 User workflow impact
None
## 3.4 UI changes
None
## 3.5 Notification impact
None
# 4. Implementation
# 5. Performance and scaling impact
## 5.1 API and control plane
None
## 5.2 Forwarding performance
None
# 6. Upgrade
None
# 7. Deprecations
Range queries on U64 and Double tags will no longer be supported
# 8. Dependencies
None
# 9. Testing
## 9.1 Unit tests
All the existing Unit tests and systemless tests should be working.
## 9.2 Dev tests
## 9.3 System tests

# 10. Documentation Impact

# 11. Reference