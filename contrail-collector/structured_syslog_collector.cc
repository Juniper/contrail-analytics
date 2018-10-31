//
// Copyright (c) 2017 Juniper Networks, Inc. All rights reserved.
//

#include <io/io_types.h>

#include <analytics/collector_uve_types.h>
#include "db_handler.h"
#include "structured_syslog_collector.h"

StructuredSyslogCollector::StructuredSyslogCollector(EventManager *evm,
    uint16_t structured_syslog_port, const vector<string> &structured_syslog_tcp_forward_dst,
    const std::string &structured_syslog_kafka_broker,
    const std::string &structured_syslog_kafka_topic,
    uint16_t structured_syslog_kafka_partitions,
    const Options::Kafka &kafka_options,
    DbHandlerPtr db_handler,
    ConfigClientCollector *config_client) {
    StatWalker::StatTableInsertFn stat_db_cb = NULL;
    if (db_handler) {
        stat_db_cb = boost::bind(&DbHandler::StatTableInsert, db_handler,
                        _1, _2, _3, _4, _5, GenDb::GenDbIf::DbAddColumnCb());
    }
    server_.reset(new structured_syslog::StructuredSyslogServer(evm, structured_syslog_port,
                    structured_syslog_tcp_forward_dst, structured_syslog_kafka_broker,
                    structured_syslog_kafka_topic,
                    structured_syslog_kafka_partitions,
                    kafka_options,
                    config_client,
                    stat_db_cb));
}

StructuredSyslogCollector::~StructuredSyslogCollector() {
}

bool StructuredSyslogCollector::Initialize() {
    server_->Initialize();
    return true;
}

void StructuredSyslogCollector::Shutdown() {
    server_->Shutdown();
}

