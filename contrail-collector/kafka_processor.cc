/*
 * Copyright (c) 2017 Juniper Networks, Inc. All rights reserved.
 */

#include "viz_collector.h"
#include <analytics/viz_constants.h>
#include "OpServerProxy.h"
#include <tbb/mutex.h>
#include <boost/bind.hpp>
#include <boost/assign/list_of.hpp>
#include <boost/assert.hpp>
#include "base/util.h"
#include "base/logging.h"
#include "base/parse_object.h"
#include <set>
#include <cstdlib>
#include <utility>
#include <pthread.h>
#include <algorithm>
#include <iterator>
#include <librdkafka/rdkafkacpp.h>
#include <librdkafka/rdkafka.h>
#include <sandesh/sandesh_uve.h>
#include <sandesh/common/vns_types.h>
#include <sandesh/common/vns_constants.h>

#include "rapidjson/document.h"
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

#include "kafka_processor.h"
#include "kafka_types.h"
#include <base/connection_info.h>
#include "viz_sandesh.h"

using std::map;
using std::string;
using std::vector;
using std::pair;
using std::make_pair;
using std::set;
using boost::shared_ptr;
using boost::assign::list_of;
using boost::system::error_code;
using process::ConnectionState;
using process::ConnectionType;
using process::ConnectionStatus;

class KafkaDeliveryReportCb : public RdKafka::DeliveryReportCb {
 public:
  unsigned int count;
  // This is to count the number of successful
  // kafka operations
  KafkaDeliveryReportCb() : count(0) {}

  void dr_cb (RdKafka::Message &message) {
    if (message.err() != RdKafka::ERR_NO_ERROR) {
        if (message.msg_opaque() != 0) {
            LOG(ERROR, "Message delivery for " << message.key() << " " <<
                message.errstr() << " gen " <<
                string((char *)(message.msg_opaque())));
        } else {
            LOG(ERROR, "Message delivery for " << message.key() << " " <<
                message.errstr());
        }
    } else {
        count++;
    }
    char * cc = (char *)message.msg_opaque();
    delete[] cc;
  }
};


class KafkaEventCb : public RdKafka::EventCb {
 public:
  bool disableKafka;
  KafkaEventCb() : disableKafka(false) {}

  void event_cb (RdKafka::Event &event) {
    switch (event.type())
    {
      case RdKafka::Event::EVENT_ERROR:
        LOG(ERROR, RdKafka::err2str(event.err()) << " : " << event.str());
        if (event.err() == RdKafka::ERR__ALL_BROKERS_DOWN) disableKafka = true;
        break;

      case RdKafka::Event::EVENT_LOG:
        LOG(INFO, "LOG-" << event.severity() << "-" << event.fac().c_str() <<
            ": " << event.str().c_str());
        break;

      default:
        LOG(INFO, "EVENT " << event.type() <<
            " (" << RdKafka::err2str(event.err()) << "): " <<
            event.str());
        break;
    }
  }
};

static inline unsigned int djb_hash (const char *str, size_t len) {
    unsigned int hash = 5381;
    for (size_t i = 0 ; i < len ; i++)
        hash = ((hash << 5) + hash) + str[i];
    return hash;
}

class KafkaPartitionerCb : public RdKafka::PartitionerCb {
  public:
    int32_t partitioner_cb (const RdKafka::Topic *topic,
                                  const std::string *key,
                                  int32_t partition_cnt,
                                  void *msg_opaque) {
        int32_t pt = djb_hash(key->c_str(), key->size()) % partition_cnt;
        LOG(DEBUG,"PartitionerCb key " << key->c_str()  << " len " << key->size() <<
                 key->size() << " count " << partition_cnt << " pt " << pt); 
        return pt;
    }
};


KafkaEventCb k_event_cb;
KafkaDeliveryReportCb k_dr_cb;

void
KafkaProcessor::KafkaPub(unsigned int pt,
                  const string& skey,
                  const string& gen,
                  const string& value) {
    if (k_event_cb.disableKafka) {
        LOG(INFO, "Kafka ignoring KafkaPub");
        return;
    }

    if (producer_) {
        char* gn = new char[gen.length()+1];
        strcpy(gn,gen.c_str());

        // Key in Kafka Topic includes UVE Key, Type
        producer_->produce(topic_[pt].get(), 0, 
            RdKafka::Producer::MSG_COPY,
            const_cast<char *>(value.c_str()), value.length(),
            &skey, (void *)gn);
    }
}

bool
KafkaProcessor::KafkaTimer() {
    {
        uint64_t new_tick_time = ClockMonotonicUsec() / 1000;
        // We track how long it has been since the timer was last called
        // This is because the execution time of this function is highly variable.
        // StartKafka can take several seconds
        kafka_elapsed_ms_ += (new_tick_time - kafka_tick_ms_);
        kafka_tick_ms_ = new_tick_time;
    }

    // Connection Status is periodically updated
    // based on Kafka piblish activity.
    // Update Connection Status more often during startup or during failures
    if ((((kafka_tick_ms_ - kafka_start_ms_) < kActivityCheckPeriod_ms_) &&
         (kafka_elapsed_ms_ >= kActivityCheckPeriod_ms_/3)) ||
        (k_event_cb.disableKafka &&
         (kafka_elapsed_ms_ >= kActivityCheckPeriod_ms_/3)) ||
        (kafka_elapsed_ms_ > kActivityCheckPeriod_ms_)) {
        
        kafka_elapsed_ms_ = 0;

        if (k_dr_cb.count==0) {
            LOG(ERROR, "No Kafka Callbacks");
            ConnectionState::GetInstance()->Update(ConnectionType::KAFKA_PUB,
                brokers_, ConnectionStatus::DOWN, process::Endpoint(), std::string());
        } else {
            ConnectionState::GetInstance()->Update(ConnectionType::KAFKA_PUB,
                brokers_, ConnectionStatus::UP, process::Endpoint(), std::string());
            LOG(INFO, "Got Kafka Callbacks " << k_dr_cb.count);
        }
        k_dr_cb.count = 0;

        if (k_event_cb.disableKafka) {
            LOG(ERROR, "Kafka Needs Restart");
            class RdKafka::Metadata *metadata;
            /* Fetch metadata */
            RdKafka::ErrorCode err = producer_->metadata(true, NULL,
                                  &metadata, 5000);
            if (err != RdKafka::ERR_NO_ERROR) {
                LOG(ERROR, "Failed to acquire metadata: " << RdKafka::err2str(err));
            } else {
                LOG(ERROR, "Kafka Metadata Detected");
                LOG(ERROR, "Metadata for " << metadata->orig_broker_id() <<
                    ":" << metadata->orig_broker_name());

                if (collector_ && redis_up_) {
                    LOG(ERROR, "Kafka Restarting Redis");
                    collector_->RedisUpdate(true);
                    k_event_cb.disableKafka = false;
                }
            }
            LOG(DEBUG, "Deleting metadata !!!");
            delete metadata;
        }
    } 

    if (producer_) {
        producer_->poll(0);
    }
    return true;
}


KafkaProcessor::KafkaProcessor(EventManager *evm, VizCollector *collector,
             const std::map<std::string, std::string>& aggconf,
             const std::string brokers,
             const std::string topic, 
             uint16_t partitions,
             const Options::Kafka &kafka_options) :
    partitions_(partitions),
    aggconf_(aggconf),
    evm_(evm),
    collector_(collector),
    brokers_(brokers),
    ssl_enable_(kafka_options.ssl_enable),
    kafka_keyfile_(kafka_options.keyfile),
    kafka_certfile_(kafka_options.certfile),
    kafka_ca_cert_(kafka_options.ca_cert),
    topicpre_(topic),
    redis_up_(false),
    kafka_elapsed_ms_(0),
    kafka_start_ms_(UTCTimestampUsec()/1000),
    kafka_tick_ms_(0),
    kafka_timer_(TimerManager::CreateTimer(*evm->io_service(),
                 "Kafka Timer", 
                 TaskScheduler::GetInstance()->GetTaskId(
                 "Kafka Timer"))) {

    kafka_timer_->Start(1000,
        boost::bind(&KafkaProcessor::KafkaTimer, this), NULL);
    if (brokers.empty()) return;
    ConnectionState::GetInstance()->Update(ConnectionType::KAFKA_PUB,
        brokers_, ConnectionStatus::INIT, process::Endpoint(), std::string());
    assert(StartKafka());
}

void
KafkaProcessor::StopKafka(void) {
    if (producer_) {
        for (unsigned int i=0; i<partitions_; i++) {
            topic_[i].reset();
        }
        topic_.clear();
        producer_.reset();
        LOG(ERROR, "Kafka Stopped");
    }
}

bool
KafkaProcessor::StartKafka(void) {
    string errstr;
    RdKafka::Conf *conf = RdKafka::Conf::create(RdKafka::Conf::CONF_GLOBAL);
    conf->set("metadata.broker.list", brokers_, errstr);
    conf->set("event_cb", &k_event_cb, errstr);
    conf->set("dr_cb", &k_dr_cb, errstr);
    conf->set("api.version.request", "false", errstr);
    conf->set("broker.version.fallback", "0.9.0.1", errstr);
    if (ssl_enable_) {
        conf->set("security.protocol", "SSL", errstr);
        conf->set("ssl.key.location", kafka_keyfile_, errstr);
        conf->set("ssl.certificate.location", kafka_certfile_, errstr);
        conf->set("ssl.ca.location", kafka_ca_cert_, errstr);
    }
    producer_.reset(RdKafka::Producer::create(conf, errstr));
    LOG(ERROR, "Kafka new Prod " << errstr);
    delete conf;
    if (!producer_) {
        return false;
    }
    for (unsigned int i=0; i<partitions_; i++) {
        std::stringstream ss;
        ss << topicpre_;
        ss << i;
        errstr = string();
        shared_ptr<RdKafka::Topic> sr(RdKafka::Topic::create(producer_.get(), ss.str(), NULL, errstr));
        LOG(ERROR,"Kafka new topic " << ss.str() << " Err" << errstr);
 
        topic_.push_back(sr);
        if (!topic_[i])
            return false;
    }

    return true;
}

void
KafkaProcessor::Shutdown() {
    TimerManager::DeleteTimer(kafka_timer_);
    kafka_timer_ = NULL;
    StopKafka();
}

KafkaProcessor::~KafkaProcessor() {
    assert(kafka_timer_ == NULL);
}
