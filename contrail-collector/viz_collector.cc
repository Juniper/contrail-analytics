/*
 * Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
 */

#include "viz_collector.h"
#include <boost/lexical_cast.hpp>
#include <boost/bind.hpp>
#include <iostream>
#include <vector>

#include "base/logging.h"
#include "base/task.h"
#include "base/address_util.h"
#include "base/parse_object.h"
#include "io/event_manager.h"

#include "sandesh/sandesh_session.h"

#include "ruleeng.h"
#include "structured_syslog_collector.h"
#include "viz_sandesh.h"
#include <zookeeper/zookeeper_client.h>


#include "rapidjson/document.h"
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

using std::stringstream;
using std::string;
using std::map;
using std::make_pair;
using boost::system::error_code;
using namespace zookeeper::client;

VizCollector::VizCollector(EventManager *evm, unsigned short listen_port,
            const std::string &listen_ip,
            bool structured_syslog_collector_enabled,
            unsigned short structured_syslog_listen_port,
            const vector<string> &structured_syslog_tcp_forward_dst,
            const std::string &structured_syslog_kafka_broker,
            const std::string &structured_syslog_kafka_topic,
            uint16_t structured_syslog_kafka_partitions,
            const std::string &redis_uve_ip, unsigned short redis_uve_port,
            const std::string &redis_password,
            const std::map<std::string, std::string>& aggconf,
            const std::string &brokers,
            uint16_t partitions, bool dup,
            const std::string &kafka_prefix,
            const Options::Cassandra &cassandra_options,
            const std::string &zookeeper_server_list,
            bool use_zookeeper,
            const DbWriteOptions &db_write_options,
            const SandeshConfig &sandesh_config,
            ConfigClientCollector *config_client,
            std::string host_ip,
            const Options::Kafka &kafka_options) :
    osp_(new OpServerProxy(evm, this, redis_uve_ip, redis_uve_port,
         redis_password, aggconf, brokers, partitions, kafka_prefix,
         kafka_options)),
    redis_gen_(0), partitions_(partitions) {
    if (!cassandra_options.cassandra_ips_.empty()) {
        db_initializer_.reset(new DbHandlerInitializer(evm,
            DbGlobalName(dup, host_ip),
            std::string("collector:DbIf"),
            boost::bind(&VizCollector::DbInitializeCb, this),
            cassandra_options,
            zookeeper_server_list, use_zookeeper,
            db_write_options, config_client));
    } else {
        db_initializer_.reset();
    }

    ruleeng_.reset(new Ruleeng(
                        db_initializer_?db_initializer_->GetDbHandler():DbHandlerPtr(),
                        osp_.get()));
    collector_ = new Collector(evm, listen_port, listen_ip, sandesh_config,
                        db_initializer_?db_initializer_->GetDbHandler():DbHandlerPtr(),
                        osp_.get(),
                        boost::bind(&Ruleeng::rule_execute,
                                     ruleeng_.get(), _1, _2, _3, _4));

    error_code error;
    if (dup)
        name_ = ResolveCanonicalName(host_ip) + "dup";
    else
        name_ = ResolveCanonicalName(host_ip);
    if (structured_syslog_collector_enabled) {
        structured_syslog_collector_.reset(new StructuredSyslogCollector(evm,
            structured_syslog_listen_port, structured_syslog_tcp_forward_dst,
            structured_syslog_kafka_broker,
            structured_syslog_kafka_topic,
            structured_syslog_kafka_partitions,
            kafka_options,
            db_initializer_?db_initializer_->GetDbHandler():DbHandlerPtr(),
            config_client));
    }

    host_ip_ = host_ip;
    if (use_zookeeper) {
        std::string hostname = ResolveCanonicalName(host_ip);
        zoo_client_.reset(new ZookeeperClient(hostname.c_str(),
            zookeeper_server_list.c_str()));
        AddNodeToZooKeeper(host_ip_);
    }
}

VizCollector::VizCollector(EventManager *evm, DbHandlerPtr db_handler,
        Ruleeng *ruleeng, Collector *collector, OpServerProxy *osp,
        const std::string &host_ip) :
    db_initializer_(new DbHandlerInitializer(evm, DbGlobalName(false, host_ip),
        std::string("collector::DbIf"),
        boost::bind(&VizCollector::DbInitializeCb, this),
        db_handler)),
    osp_(osp),
    ruleeng_(ruleeng),
    collector_(collector),
    redis_gen_(0), partitions_(0) {
    error_code error;
    name_ = ResolveCanonicalName(host_ip);
}

VizCollector::~VizCollector() {
}

std::string VizCollector::DbGlobalName(bool dup,
    const std::string &host_ip) {
    return Collector::DbGlobalName(dup, host_ip);
}

bool VizCollector::SendRemote(const string& destination,
        const string& dec_sandesh) {
    if (collector_){
        return collector_->SendRemote(destination, dec_sandesh);
    } else {
        return false;
    }
}

void VizCollector::WaitForIdle() {
    static const int kTimeout = 15;
    TaskScheduler *scheduler = TaskScheduler::GetInstance();

    for (int i = 0; i < (kTimeout * 1000); i++) {
        if (scheduler->IsEmpty()) {
            break;
        }
        usleep(1000);
    }
}

void VizCollector::Shutdown() {
    // First shutdown collector
    collector_->Shutdown();
    DelNodeFromZoo();
    WaitForIdle();

    // Wait until all connections are cleaned up.
    for (int cnt = 0; collector_->ConnectionsCount() != 0 && cnt < 15; cnt++) {
        sleep(1);
    }
    TcpServerManager::DeleteServer(collector_);

    osp_->Shutdown();
    WaitForIdle();

    if (structured_syslog_collector_) {
        structured_syslog_collector_->Shutdown();
        WaitForIdle();
    }
    if (db_initializer_) {
        db_initializer_->Shutdown();
    }
    LOG(DEBUG, __func__ << " viz_collector done");
}

void VizCollector::DbInitializeCb() {
    ruleeng_->Init();
    if (structured_syslog_collector_) {
        structured_syslog_collector_->Initialize();
    }
}

bool VizCollector::Init() {
    if (db_initializer_) {
        return db_initializer_->Initialize();
    }
    return true;
}

void VizCollector::SendGeneratorStatistics() {
    if (collector_) {
        collector_->SendGeneratorStatistics();
    }
}

void VizCollector::SendDbStatistics() {
    if (!db_initializer_) {
        return;
    }
    DbHandlerPtr db_handler(db_initializer_->GetDbHandler());
    // DB stats
    std::vector<GenDb::DbTableInfo> vdbti, vstats_dbti;
    GenDb::DbErrors dbe;
    db_handler->GetStats(&vdbti, &dbe, &vstats_dbti);

    // TODO: Change DBStats to return a map directly
    map<string,GenDb::DbTableStat> mtstat, msstat;

    for (size_t idx=0; idx<vdbti.size(); idx++) {
        GenDb::DbTableStat dtis;
        dtis.set_reads(vdbti[idx].get_reads());
        dtis.set_read_fails(vdbti[idx].get_read_fails());
        dtis.set_writes(vdbti[idx].get_writes());
        dtis.set_write_fails(vdbti[idx].get_write_fails());
        dtis.set_write_back_pressure_fails(vdbti[idx].get_write_back_pressure_fails());
        mtstat.insert(make_pair(vdbti[idx].get_table_name(), dtis));
    } 

    for (size_t idx=0; idx<vstats_dbti.size(); idx++) {
        GenDb::DbTableStat dtis;
        dtis.set_reads(vstats_dbti[idx].get_reads());
        dtis.set_read_fails(vstats_dbti[idx].get_read_fails());
        dtis.set_writes(vstats_dbti[idx].get_writes());
        dtis.set_write_fails(vstats_dbti[idx].get_write_fails());
        dtis.set_write_back_pressure_fails(
            vstats_dbti[idx].get_write_back_pressure_fails());
        msstat.insert(make_pair(vstats_dbti[idx].get_table_name(), dtis));
    } 
    
    CollectorDbStats cds;
    cds.set_name(name_);
    cds.set_table_info(mtstat);
    cds.set_errors(dbe);
    cds.set_stats_info(msstat);

    SessionTableDbInfo stds;
    db_handler->GetSessionTableDbInfo(&stds);
    cds.set_session_table_stats(stds);

    cass::cql::DbStats cql_stats;
    if (db_handler->GetCqlStats(&cql_stats)) {
        cds.set_cql_stats(cql_stats);
    }
    CollectorDbStatsTrace::Send(cds);
}

bool VizCollector::GetCqlMetrics(cass::cql::Metrics *metrics) {
    if (!db_initializer_) {
        return true;
    }
    DbHandlerPtr db_handler(db_initializer_->GetDbHandler());
    return db_handler->GetCqlMetrics(metrics);
}

void VizCollector::AddNodeToZooKeeper(const std::string &host_ip) {
    error_code error;
    std::string hostname = ResolveCanonicalName(host_ip);
    std::string path = "/analytics-discovery-";
    zoo_client_->CreateNode(path.c_str(),
                                    hostname.c_str(),
                                    Z_NODE_TYPE_PERSISTENT);

    path += "/" + g_vns_constants.COLLECTOR_DISCOVERY_SERVICE_NAME;
    zoo_client_->CreateNode(path.c_str(),
                                    hostname.c_str(),
                                    Z_NODE_TYPE_PERSISTENT);

    path += "/" + hostname;
    if (zoo_client_->CheckNodeExist(path.c_str())) {
        zoo_client_->DeleteNode(path.c_str());
    }
    Module::type module = Module::COLLECTOR;
    std::string module_id(g_vns_constants.ModuleNames.find(module)->second);
    NodeType::type node_type =
        g_vns_constants.Module2NodeType.find(module)->second;
    std::string type_name =
        g_vns_constants.NodeTypeNames.find(node_type)->second;
    std::ostringstream instance_str;
    instance_str << getpid();
    std::string instance_id = instance_str.str();
    std::map<std::string, std::string> key_val_pair;
    key_val_pair.insert(make_pair("hostname", hostname));
    key_val_pair.insert(make_pair("type_name", type_name));
    key_val_pair.insert(make_pair("module_id", module_id));
    key_val_pair.insert(make_pair("instance_id", instance_id));
    key_val_pair.insert(make_pair("ip_address", host_ip_));
    std::map<std::string, std::string>::iterator it;
    contrail_rapidjson::Document dd;
    dd.SetObject();
    for (it = key_val_pair.begin(); it != key_val_pair.end(); it++) {
        contrail_rapidjson::Value val(contrail_rapidjson::kStringType);
        contrail_rapidjson::Value skey(contrail_rapidjson::kStringType);
        val.SetString(it->second.c_str(), dd.GetAllocator());
        dd.AddMember(skey.SetString(it->first.c_str(), dd.GetAllocator()),
                    val, dd.GetAllocator());
    }
    contrail_rapidjson::StringBuffer sb;
    contrail_rapidjson::Writer<contrail_rapidjson::StringBuffer> writer(sb);
    dd.Accept(writer);
    string jsonline(sb.GetString());
    zoo_client_->CreateNode(path.c_str(),
                                    jsonline.c_str(),
                                    Z_NODE_TYPE_EPHEMERAL);
}

void VizCollector::DelNodeFromZoo() {
    zoo_client_->Shutdown();
}

