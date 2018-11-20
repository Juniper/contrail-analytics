# 1. Introduction
Currently all the stats collected by collector consists of a number of tags against which the stat is to be indexed. With the current schema, we need to do as many writes as the number of tags for the stat.

# 2. Problem statement
Currently all the stats collected by collector consists of a number of tags against which the stat is to be indexed. With the current schema, we need to do as many writes as the number of tags for the stat. If high number of stats are sent to collector, it will scheme will not scale. Hence, the number of writes per stat should be reduced.

# 3. Proposed solution
Currently we do one write in database per tag. Instead, we can create an encoded string in **tag1=value1;tag2=value2;tag3=value3...** format. We will have 4 such fields and each tag will go into 1 of the four buckets depending on the hashing of the tag name. Apart from that we will have separate columns for well-known tags like name, source, key and proxy. Name field will be a clustering column while we will index the encoded tags string, source, key and proxy fields with SASI index, which will allow these fields to be queried. The new schema will look like below -  

```
CREATE TABLE "ContrailAnalyticsCql".stattablev4 (
    key int,              \\ T2
    key2 int,             \\ partition_number
    key3 text,            \\ StatName
    key4 text,            \\ StatAttr
    column1 text,         \\ name
    column2 int,          \\ T1
    column3 uuid,         \\ UUID
    column4 text,         \\ T2:source
    column5 text,         \\ T2:key
    column6 text,         \\ T2:proxy
    column7 text,         \\ T2:tag1=value1;tag8=value2;..
    column8 text,         \\ T2:tag2=value1;tag5=value2;..
    column9 text,         \\ T2:tag4=value1;tag3=value2;..
    column10 text,        \\ T2:tag7=value1;tag2=value2;..
    value text,           \\ value
    PRIMARY KEY ((key, key2, key3, key4), column1, column2)
) WITH CLUSTERING ORDER BY (column1 ASC, column2 ASC)

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

Apart from this, Currently there is no support for containers(set, list and map) as tags in stats. We want to index against individual elements in the container so that it can be searched. To support this,
1) For Set/List:
	suppose we have a set named **labels** as a tag. Each element in the set would be considered as a tag in the format **labels=element** and stored as mentioned above.
	We will add an operator called CONTAINS to query these. User can query like **labels CONTAINS element** in the WHERE clause of the query. When a set/list is included in the SELECT clause, the entire container will be returned.	
2) For Map:
	suppose we have a map named **custom_attributes** (with entries {attr1:val1} and {attr2:val2}) as a tag. Each element in the map would be considered as a tag in the **custom_attributes.attr*=val*** format and stored as mentioned above.
	The external schema for such fields will have entries like **{'name':'custom_attributes.*', 'datatype':'string', 'indexed': 'true'}**. If User wants to look for entries where custom_attributes.attr1 = val1, he will have **custom_attributes.attr1=val1** in the WHERE CLAUSE. For the select clause, a user can decide to get the entire map in result by including custom_attributes in the SELECT clause or user can also decide to get individual entries in the result by providing the map.key (e.g. custom_attributes.attr1) in the SELECT CLAUSE.

## 3.1 Alternatives considered
None
## 3.2 API schema changes
As mentioned in Section 3, to provide the ability to search individual elements of map, the api will have fields called **map_name.***. Also a new operator called **CONTAINS** is added to query set/list.
## 3.3 User workflow impact
None
## 3.4 UI changes
None
## 3.5 Notification impact
None
# 4. Implementation
# 5. Performance and scaling impact
Because there will be only 1 write per stats, the number of writes would be less and hence write performance would increase by the number of tags (at least 2x as all the tags have source and name).
## 5.1 API and control plane
None
## 5.2 Forwarding performance
None
# 6. Upgrade
When upgrading, older data will not be any use once upgraded. We shall be providing a script to migrate older data to new format.
# 7. Deprecations
Range queries on U64 and Double tags will no longer be supported in the Where clause. Though this operations can still be done in the Filter clause.
# 8. Dependencies
None
# 9. Testing
## 9.1 Unit tests
All the existing Unit tests and systemless tests should be working.
## 9.2 Dev tests
## 9.3 System tests

# 10. Documentation Impact

# 11. Reference
