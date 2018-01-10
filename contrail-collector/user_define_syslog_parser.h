/*
 * Copyright (c) 2017 Juniper Networks, Inc. All rights reserved.
 */

#ifndef SRC_USER_DEFINE_SYSLOG_PARSER_H_
#define SRC_USER_DEFINE_SYSLOG_PARSER_H_

#include <map>
#include <string>
#include <deque>
#include <set>
#include <vector>
#include "analytics_types.h"
#include "config_client_collector.h"
#include "grok_parser.h"
#include "generator.h"
#include "stat_walker.h"
#include "syslog_collector.h"

struct Rfc5424CfgInfo {
    bool hostname_as_tag;
    bool appname_as_tag;
    bool procid_as_tag;
    bool msgid_as_tag;
};

typedef std::map<std::string, Rfc5424CfgInfo> Rfc5424CfgList;

struct SyslogParserInfo {
    std::string pattern;
    bool pattern_compile_error;
    vector<std::string> sub_patterns;
    std::set<std::string> tag_list;
    std::set<std::string> metric_name;
    map<std::string, std::string> metric_type;
};

typedef std::map<std::string, SyslogParserInfo> SyslogParserList;
typedef std::map<std::string, std::string> SyslogParserToDomainMap;
typedef std::map<std::string, std::set<std::string> > DomainToSyslogParser;

class UserDefineSyslogParser {
public:
    UserDefineSyslogParser(EventManager *evm,
                           SyslogListeners *syslog_listener,
                           StatWalker::StatTableInsertFn stat_db_cb);
    ~UserDefineSyslogParser();

    /* Receive configuration*/
    void rx_config(const contrail_rapidjson::Document &jdoc, bool);

     /* Get config info*/
    void get_config(std::vector<LogParserConfigInfo> *config_info,
                    std::vector<LogParserConfigInfo> *preconfig,
             std::vector<LogParserPreInstallPatternInfo> *preinstall_pattern);

    /* receive syslog and parse*/
    void syslog_parse(std::string ip, std::string strin);

private:
    boost::scoped_ptr<GrokParser> gp_;
    Rfc5424CfgList rfc5424_cfg_list_;
    SyslogParserList syslog_parser_cfg_list_;
    SyslogParserToDomainMap parser_to_domain_map_;
    DomainToSyslogParser    domain_to_parser_map_;
    SyslogListeners *syslog_listener_;
    StatWalker::StatTableInsertFn db_insert_cb_;
    void add_RFC5424_pattern();
    void add_update_parser_config(std::string name, std::string parent_name,
                                  const contrail_rapidjson::Document &jdoc);
    void delete_parser_config(std::string name, std::string parent_name,
                                  const contrail_rapidjson::Document &jdoc);
    void add_update_rfc5424_config(std::string name,
                                  const contrail_rapidjson::Document &jdoc);
    void delete_rfc5424_config(std::string name,
                                  const contrail_rapidjson::Document &jdoc);
    time_t parse_timestamp(std::string time_s); 
    void parse_to_stats(string source,
                        std::map<std::string, std::string> header_info, 
                        uint64_t ts, string domain_id, string s);
    void rfc5424_parse(std::string source,
                        std::map<std::string, std::string> header_info);
    
};

#endif // SRC_USER_DEFINE_SYSLOG_PARSER_H_ 
