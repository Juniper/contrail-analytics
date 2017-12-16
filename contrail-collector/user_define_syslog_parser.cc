/*
 * Copyright (c) 2017 Juniper Networks, Inc. All rights reserved.
 */

#include <iostream>
#include <cstring>
#include <boost/algorithm/string.hpp>
#include <boost/lexical_cast.hpp>
#include <boost/regex.hpp>
#include <vector>
#include <base/logging.h>
#include <tbb/mutex.h>
#include "user_define_syslog_parser.h"
#include "rapidjson/stringbuffer.h"
#include "rapidjson/writer.h"

using contrail_rapidjson::Document;
using contrail_rapidjson::StringBuffer;
using contrail_rapidjson::Value;
using contrail_rapidjson::Writer;

namespace bt = boost::posix_time;

tbb::mutex mutex;
#define SYSLOG_DEFAULT_DOMAIN "default"

std::string SYSLOG_RFC5424    =  "SYSLOG5424";
std::string SYSLOG_RPI        =  "syslog5424_pri";
std::string SYSLOG_VERSION    =  "syslog5424_ver";
std::string SYSLOG_TS         =  "syslog5424_ts";
std::string SYSLOG_HOST       =  "hostname";
std::string SYSLOG_APP        =  "appname";
std::string SYSLOG_PROC       =  "procid";
std::string SYSLOG_MSG_ID     =  "msgid";
std::string SYSLOG_SD_BODY    =  "syslog5424_sd";
std::string SYSLOG_MSG_BODY   =  "syslog5424_msg";

UserDefineSyslogParser::UserDefineSyslogParser(EventManager *evm,
                                     SyslogListeners *syslog_listener,
                                     StatWalker::StatTableInsertFn stat_db_cb) {
    gp_.reset(new GrokParser());
    gp_->init();
    add_RFC5424_pattern();
    syslog_listener_ = syslog_listener;
    db_insert_cb_ = stat_db_cb;
    syslog_listener_->RegistUserParserCb("UserDefSyslog",
              boost::bind(&UserDefineSyslogParser::syslog_parse, this, _1, _2));
}

UserDefineSyslogParser::~UserDefineSyslogParser() {
}

/* add RFC5424 pattern
*  create a new grok for RFC5424 pattern
*  This grok will be used to get RFC5424
*  header info, sd body string and message
*  body string.
*/
/*
SYSLOG5424PRINTASCII [!-~]+
SYSLOG5424PRI  <%{NONNEGINT:syslog5424_pri}>
SYSLOG5424SD   \[%{DATA}\]+
SYSLOG5424BASE %{SYSLOG5424PRI}%{NONNEGINT:syslog5424_ver} 
               +(?:%{TIMESTAMP_ISO8601:syslog5424_ts}|-) 
               +(?:%{HOSTNAME:syslog5424_host}|-) 
               +(-|%{SYSLOG5424PRINTASCII:syslog5424_app}) 
               +(-|%{SYSLOG5424PRINTASCII:syslog5424_proc}) 
               +(-|%{SYSLOG5424PRINTASCII:syslog5424_msgid}) 
               +(?:%{SYSLOG5424SD:syslog5424_sd}|-|)
SYSLOG5424LINE %{SYSLOG5424BASE} +%{GREEDYDATA:syslog5424_msg}
*/
void UserDefineSyslogParser::add_RFC5424_pattern() {
    std::string name = SYSLOG_RFC5424;
    domain_to_parser_map_[SYSLOG_DEFAULT_DOMAIN].insert(name);
    parser_to_domain_map_[name] = SYSLOG_DEFAULT_DOMAIN;

    SyslogParserInfo rfc5424_parser;
    rfc5424_parser.pattern = "%{SYSLOG5424BASE} +%{GREEDYDATA:"
             + SYSLOG_MSG_BODY
             + "}";

    string sub_pattern;

    sub_pattern = "SYSLOG5424PRINTASCII [!-~]+";
    rfc5424_parser.sub_patterns.push_back(sub_pattern);

    sub_pattern = "SYSLOG5424PRI <%{NONNEGINT:"
             + SYSLOG_RPI
             + "}>";
    rfc5424_parser.sub_patterns.push_back(sub_pattern);

    sub_pattern = "SYSLOG5424SD \\[%{DATA}\\]+";
    rfc5424_parser.sub_patterns.push_back(sub_pattern);

    sub_pattern = "SYSLOG5424BASE %{SYSLOG5424PRI}%{NONNEGINT:"
             + SYSLOG_VERSION +
             + "} +(?:%{TIMESTAMP_ISO8601:"
             + SYSLOG_TS
             + "}|-) +(?:%{HOSTNAME:"
             + SYSLOG_HOST
             + "}|-) +(-|%{SYSLOG5424PRINTASCII:"
             + SYSLOG_APP
             + "}) +(-|%{SYSLOG5424PRINTASCII:"
             + SYSLOG_PROC
             + "}) +(-|%{SYSLOG5424PRINTASCII:"
             + SYSLOG_MSG_ID
             + "}) +(?:%{SYSLOG5424SD:"
             + SYSLOG_SD_BODY
             + "}|-|)";
    rfc5424_parser.sub_patterns.push_back(sub_pattern);

    rfc5424_parser.tag_list.insert(SYSLOG_RPI);
    rfc5424_parser.tag_list.insert(SYSLOG_VERSION);
    rfc5424_parser.tag_list.insert(SYSLOG_TS);
    rfc5424_parser.tag_list.insert(SYSLOG_HOST);
    rfc5424_parser.tag_list.insert(SYSLOG_APP);
    rfc5424_parser.tag_list.insert(SYSLOG_PROC);
    rfc5424_parser.tag_list.insert(SYSLOG_MSG_ID);
    rfc5424_parser.tag_list.insert(SYSLOG_SD_BODY);
    rfc5424_parser.tag_list.insert(SYSLOG_MSG_BODY);

    syslog_parser_cfg_list_[name] = rfc5424_parser;

    gp_->create_grok_instance(name);
    gp_->add_pattern(name, name + " " + rfc5424_parser.pattern);
    for (size_t i = 0; i < rfc5424_parser.sub_patterns.size(); i++) {
        gp_->add_pattern(name, rfc5424_parser.sub_patterns[i]);
    }
    gp_->compile_pattern(name);
}

/* configuration client callback fucntion.
*  two object can be accepted now:
*     -  syslog_parser
*     -  rfc5424
*/
void 
UserDefineSyslogParser::rx_config(const contrail_rapidjson::Document &jdoc, bool add_update) {
    #if 1
    contrail_rapidjson::StringBuffer sb;
    contrail_rapidjson::Writer<contrail_rapidjson::StringBuffer> writer(sb);
    jdoc.Accept(writer);
    LOG(ERROR, sb.GetString());
    #endif
    if (jdoc.IsObject() && jdoc.HasMember("syslog_parser")) {
        std::string name;
        std::string parent_name;
        const contrail_rapidjson::Value& parser = jdoc["syslog_parser"];
        if (parser.HasMember("fq_name")) {
            const contrail_rapidjson::Value& fq_name = parser["fq_name"];
            contrail_rapidjson::SizeType sz = fq_name.Size();
            name = fq_name[sz-1].GetString();
            parent_name = fq_name[sz-2].GetString();
        } else {
            LOG(ERROR, "Object syslog_parser miss FQ name!");
            return;
        }
        if (add_update) {
            //add_update_parser_config(name, parent_name, jdoc);
        } else {
            //delete_parser_config(name, parent_name, jdoc);
        }
    } else if (jdoc.IsObject() && jdoc.HasMember("rfc5424")) {
        std::string name;
        const contrail_rapidjson::Value& rfc5424 = jdoc["rfc5424"];
        if (rfc5424.HasMember("fq_name")) {
            const contrail_rapidjson::Value& fq_name = rfc5424["fq_name"];
            contrail_rapidjson::SizeType sz = fq_name.Size();
            name = fq_name[sz-1].GetString();
        } else {
            LOG(ERROR, "Object rfc5424 miss FQ name!");
            return;
        } 
        if (add_update) {
            //add_update_rfc5424_config(name, jdoc);
        } else {
            //delete_rfc5424_config(name, jdoc);
        }
    }
}


/* deal with syslog_parser add/update.
*  name        : fq_name
*  parent_name : parent fq_name
*  jdoc        : json document for configuration 
*/
void
UserDefineSyslogParser::add_update_parser_config(std::string name, std::string parent_name,
                                     const contrail_rapidjson::Document &jdoc) {
    tbb::mutex::scoped_lock lock(mutex);
    const contrail_rapidjson::Value& parser_d = jdoc["syslog_parser"];
    if (syslog_parser_cfg_list_.find(name) == syslog_parser_cfg_list_.end()) {
        syslog_parser_cfg_list_[name] = SyslogParserInfo(); 
    }
    SyslogParserInfo *pParser = &syslog_parser_cfg_list_[name];

    if (parser_d.HasMember("parent_type")) {
        if (parser_to_domain_map_.find(name) != parser_to_domain_map_.end()) {
            std::string domain = parser_to_domain_map_[name];
            domain_to_parser_map_[domain].erase(name); 
        }
        domain_to_parser_map_[parent_name].insert(name);
        parser_to_domain_map_[name] = parent_name;
    }

    if (parser_d.HasMember("pattern")) {
        pParser->pattern = "";
        pParser->sub_patterns.clear();
        pParser->pattern = parser_d["pattern"]["pattern_string"].GetString();
        for (contrail_rapidjson::SizeType i = 0; 
             i < parser_d["pattern"]["sub_patterns"].Size(); i++) {
            std::string sub_name =
                parser_d["pattern"]["sub_patterns"][i]["pattern_name"].GetString();
            std::string sub_pattern =
                parser_d["pattern"]["sub_patterns"][i]["pattern"].GetString();
            sub_pattern = sub_name + " " + sub_pattern;
            pParser->sub_patterns.push_back(sub_pattern);
        }

        /*first, we need delete old pattern and old grok*/
        gp_->del_grok_instance(name);
        /*add new grok instance again with new pattern*/
        gp_->create_grok_instance(name);
        gp_->add_pattern(name, name + " " + pParser->pattern);
        for (size_t i = 0; i < pParser->sub_patterns.size(); i++) {
            gp_->add_pattern(name, pParser->sub_patterns[i]);
        }
        if (false == gp_->compile_pattern(name)) {
            LOG(ERROR, "compile pattern " << name << " failed");
            GenericStatsAlarm  parser_alarm;
            parser_alarm.set_name(name);
            GenericStatsAlarmUVE::Send(parser_alarm);
            pParser->pattern_compile_error = true;
        } else {
            if (pParser->pattern_compile_error == true) {
                GenericStatsAlarm  parser_alarm;
                parser_alarm.set_name(name);
                parser_alarm.set_deleted(true);
                GenericStatsAlarmUVE::Send(parser_alarm);
                pParser->pattern_compile_error = false;
            }
        }
    }

    if (parser_d.HasMember("query_tags")) {
        pParser->tag_list.clear();
        for (contrail_rapidjson::SizeType i = 0;
             i < parser_d["query_tags"]["tag_list"].Size(); i++) {
            pParser->tag_list.insert(parser_d["query_tags"]["tag_list"][i].GetString());
        }
    }

    if (parser_d.HasMember("metrics")) {
        pParser->metric_name.clear();
        pParser->metric_type.clear();
        for (contrail_rapidjson::SizeType i = 0;
             i < parser_d["metrics"]["metric_list"].Size(); i++) {
            std::string name =
                        parser_d["metrics"]["metric_list"][i]["name"].GetString();
            std::string type =
                        parser_d["metrics"]["metric_list"][i]["data_type"].GetString();
            pParser->metric_name.insert(name);
            pParser->metric_type[name] = type; 
        }
    }
}

/* deal with syslog_parser deletion
*  name        : fq_name
*  parent_name : parent fq_name
*  jdoc        : json document for configuration
*/
void
UserDefineSyslogParser::delete_parser_config(std::string name, std::string parent_name,
                                     const contrail_rapidjson::Document &jdoc) {
    tbb::mutex::scoped_lock lock(mutex);
    const contrail_rapidjson::Value& parser_d = jdoc["syslog_parser"];
    if (syslog_parser_cfg_list_.find(name) == syslog_parser_cfg_list_.end()) {
        LOG(ERROR,"Delete parser: No parser " << name);
        return;
    }
    SyslogParserInfo *pParser = &syslog_parser_cfg_list_[name];

    if (parser_d.HasMember("parent_type")) {
        if (parser_to_domain_map_.find(name) != parser_to_domain_map_.end()) {
            domain_to_parser_map_[parent_name].erase(name);
            parser_to_domain_map_.erase(name);
        }
    }

    if (parser_d.HasMember("pattern")) {
        pParser->pattern = "";
        pParser->sub_patterns.clear();
        if (pParser->pattern_compile_error == true) {
            GenericStatsAlarm  parser_alarm;
            parser_alarm.set_name(name);
            parser_alarm.set_deleted(true);
            GenericStatsAlarmUVE::Send(parser_alarm);
            pParser->pattern_compile_error = false;
        }         
        gp_->del_grok_instance(name);
    }

    if (parser_d.HasMember("query_tags")) {
        pParser->tag_list.clear();
    }

    if (parser_d.HasMember("metrics")) {
        pParser->metric_name.clear();
        pParser->metric_type.clear();
    }
}

/* deal with rfc5424 add/update
*  name        : fq_name
*  jdoc        : json document for configuration
*/
void
UserDefineSyslogParser::add_update_rfc5424_config(std::string name,
                                     const contrail_rapidjson::Document &jdoc) {
    tbb::mutex::scoped_lock lock(mutex);
    const contrail_rapidjson::Value& rfc5424_d = jdoc["rfc5424"];
    if (rfc5424_cfg_list_.find(name) == rfc5424_cfg_list_.end()) {
        rfc5424_cfg_list_[name] = Rfc5424CfgInfo();
    }
    Rfc5424CfgInfo *prfc5424Info = &rfc5424_cfg_list_[name];
    prfc5424Info->hostname_as_tag =
                         rfc5424_d["rfc5424_config"]["hostname_as_tag"].GetBool();
    prfc5424Info->appname_as_tag =
                         rfc5424_d["rfc5424_config"]["appname_as_tag"].GetBool();
    prfc5424Info->procid_as_tag =
                         rfc5424_d["rfc5424_config"]["procid_as_tag"].GetBool();
    prfc5424Info->msgid_as_tag =
                         rfc5424_d["rfc5424_config"]["msgid_as_tag"].GetBool();
}

/* deal with rfc5424 deletion
*  name        : fq_name
*  jdoc        : json document for configuration
*/
void
UserDefineSyslogParser::delete_rfc5424_config(std::string name,
                                     const contrail_rapidjson::Document &jdoc) {
    tbb::mutex::scoped_lock lock(mutex);
    if (rfc5424_cfg_list_.find(name) == rfc5424_cfg_list_.end()) {
        LOG(ERROR, "Delete rfc5424, no instance " << name);
        return;
    }
    rfc5424_cfg_list_.erase(name);
}


/*
 * parser  timestamp.
 * input : iso timestamp string.
 * output: timestamp with ms which is relative to 1970/01/01
*/
time_t
UserDefineSyslogParser::parse_timestamp(std::string time_s) {
    bool is_plus_tz = false;
    if (time_s.find("+") != std::string::npos) {
        is_plus_tz = true;
    }

    std::vector<string> date_time;
    boost::split(date_time, time_s, boost::is_any_of("T"));
    std::vector<string> time_tz;
    boost::split(time_tz, date_time[1], boost::is_any_of("+-Z"));
    bt::ptime local = bt::time_from_string(date_time[0] 
                                       + " "
                                       + time_tz[0]);
    bt::ptime epoch(boost::gregorian::date(1970,1,1));
    if (time_tz.size() == 2) {
        bt::time_duration diff = bt::duration_from_string(time_tz[1]);
        if (is_plus_tz) {
            return ((local - epoch).total_microseconds() 
                    - diff.total_microseconds());
        } else {
            return ((local - epoch).total_microseconds()
                    + diff.total_microseconds());
        }
    } else {
        return (local - epoch).total_microseconds();
    }
}


/*
 * parse string and call stats walk.
 * input : 
 *    source    syslog source ip address with string
 *    ts        timestamp (ms realtive to 1970/01/01)
 *    domain_id appname:msgid from syslog header
 *    s         syslog body string
 * output: timestamp with ms which is relative to 1970/01/01
*/
void UserDefineSyslogParser::parse_to_stats(string source,
                           std::map<std::string, std::string> header_info,
                           uint64_t ts, string domain_id, string s) {
    std::map<std::string, std::string> body_info;
    std::string name = "";
    Rfc5424CfgInfo rfc5424cfg;
    SyslogParserInfo parser;
    do {
        tbb::mutex::scoped_lock lock(mutex);
        DomainToSyslogParser::iterator iter =
                                 domain_to_parser_map_.find(domain_id);
        for (std::set<std::string>::iterator it = iter->second.begin();
                                   it != iter->second.end(); it++) {
            if (gp_->match(*it, s, &body_info)) {
                name = *it;
                break;
            }
        }
        if (!name.empty()) {
            if (syslog_parser_cfg_list_.find(name) == syslog_parser_cfg_list_.end()) {
                LOG(DEBUG, "No parser " << name);
                return;
            }
            parser = syslog_parser_cfg_list_[name];
            rfc5424cfg = rfc5424_cfg_list_[domain_id];
        }
    } while(0);
    if (!parser.metric_name.empty()) {
        StatWalker::TagMap m_t;
        StatWalker::TagVal h_t;
        h_t.val = source;
        m_t.insert(make_pair("Source", h_t));
        StatWalker sw(db_insert_cb_, (uint64_t)ts, name, m_t);
        std::map<std::string, std::string>::iterator it;
        std::vector<std::string> attrib_v;
        for (it = body_info.begin(); it != body_info.end(); it++) {
            if (parser.tag_list.find(it->first) != parser.tag_list.end()) {
                h_t.val = it->second;
                m_t.insert(make_pair(it->first, h_t));
            }
            if (parser.metric_name.find(it->first) != parser.metric_name.end()) {
                attrib_v.push_back(it->first);
            }
        }
        
        DbHandler::Var value;
        for (uint32_t i = 0; i < attrib_v.size(); i++) {
             StatWalker::TagMap tagmap;
             DbHandler::AttribMap attribs;
             if (parser.metric_type[attrib_v[i]] == "int") {
                 value  = (uint64_t)boost::lexical_cast<long long>(body_info[attrib_v[i]]);
             } else {
                 value = body_info[attrib_v[i]];
             }
             attribs.insert(make_pair("value", value));
             sw.Push(attrib_v[i], tagmap, attribs);
             sw.Pop();
        }
    }
}

/* syslog parser
*  Match system log against all stored grok
*  @Input - strin: complete system log.
*/
void UserDefineSyslogParser::syslog_parse(std::string source, std::string strin) {
    /* 1. we use base_ to parser syslog header*/
    std::map<std::string, std::string> header_info;
    std::string name = "";
    do {
        tbb::mutex::scoped_lock lock(mutex);
        DomainToSyslogParser::iterator iter =
                              domain_to_parser_map_.find(SYSLOG_DEFAULT_DOMAIN);
        for (std::set<std::string>::iterator it = iter->second.begin();
                                   it != iter->second.end(); it++) {
            if (gp_->match(*it, strin, &header_info)) {
                name = *it;
                break;
            }
        }
    } while(0);
    if (name.empty()) {
        LOG(DEBUG, "dropped: no pattern match in base_");
        return;
    }

    if (name == SYSLOG_RFC5424) {
        rfc5424_parse(source, header_info);
    }
}

/* rfc5424 format syslog parser
*  source      :  source ip/hostname
*  header_info :  header parse result
*/
void 
UserDefineSyslogParser::rfc5424_parse(std::string source,
                                  std::map<std::string, std::string> header_info) {
    string appname;
    string msgid;
    if (header_info.find(SYSLOG_APP) != header_info.end()) {
        if (!header_info[SYSLOG_APP].empty()) {
            appname = header_info[SYSLOG_APP];
        }
    }
    if (header_info.find(SYSLOG_MSG_ID) != header_info.end()) {
        if (!header_info[SYSLOG_MSG_ID].empty()) {
            msgid = header_info[SYSLOG_MSG_ID];
        }
    }
    std::string domain_id = appname + "-" + msgid;

    Rfc5424CfgList::iterator iter = rfc5424_cfg_list_.find(domain_id);
    if (iter == rfc5424_cfg_list_.end()) {
        LOG(DEBUG, "dropped:no parser config to domain_id: " << domain_id);
        return;
    }
    time_t ts = parse_timestamp(header_info[SYSLOG_TS]);
    /* 2. parse msgbody*/
    if (!header_info[SYSLOG_MSG_BODY].empty()) {
        parse_to_stats(source, header_info, ts, domain_id, header_info[SYSLOG_MSG_BODY]);
    }

    /*3. parse SD*/
    if (!header_info[SYSLOG_SD_BODY].empty()) {
        std::vector<std::string> sds;
        size_t len = header_info[SYSLOG_SD_BODY].length() - 2;
        std::string sub = header_info[SYSLOG_SD_BODY].substr(1, len);
        boost::split(sds, sub, boost::is_any_of("]["), boost::token_compress_on);
        for (std::vector<std::string>::iterator s = sds.begin();
                                                s != sds.end(); s++) {
            parse_to_stats(source, header_info, ts, domain_id, *s);
        }
    }
}

/*
 * get configuration for introspect to verify configuration
 * output parameter: config_info, define by introspect sandesh
*/
void
UserDefineSyslogParser::get_config(std::vector<LogParserConfigInfo> *config_info,
                                   std::vector<LogParserConfigInfo> *preconfig,
                  std::vector<LogParserPreInstallPatternInfo> *preinstall_info) {
    tbb::mutex::scoped_lock lock(mutex);
    for (SyslogParserList::iterator it = syslog_parser_cfg_list_.begin();
                              it != syslog_parser_cfg_list_.end(); it++) {
        LogParserConfigInfo parserInfo;
        std::string domain;
        parserInfo.set_name(it->first);
        if (parser_to_domain_map_.find(it->first) != parser_to_domain_map_.end()) {
            domain = parser_to_domain_map_[it->first];
            parserInfo.set_domain(domain);
        }
        PatterInfo pattern;
        pattern.set_pattern(it->second.pattern);
        pattern.set_sub_patterns(it->second.sub_patterns);
        std::vector<std::string> 
             tags(it->second.tag_list.begin(), it->second.tag_list.end());
        parserInfo.set_tags(tags);
        std::vector<std::string>
             metrics(it->second.metric_name.begin(), it->second.metric_name.end());
        parserInfo.set_metrics(metrics);
        if (domain == SYSLOG_DEFAULT_DOMAIN) {
            preconfig->push_back(parserInfo);
        } else {
            config_info->push_back(parserInfo);
        }
    }

    std::vector<std::string> base_pattern = gp_->get_base_pattern();
    for (uint32_t i = 0; i < base_pattern.size(); i++) {
        LogParserPreInstallPatternInfo preinstall_pattern;
        size_t pos = base_pattern[i].find(" ");
        string name = base_pattern[i].substr(0, pos);
        string pattern = base_pattern[i].substr(pos + 1);
        preinstall_pattern.set_name(name);
        preinstall_pattern.set_pattern(pattern);
        preinstall_info->push_back(preinstall_pattern);
    }
}
