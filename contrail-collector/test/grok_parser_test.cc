/*
 * Copyright (c) 2017 Juniper Networks, Inc. All rights reserved.
 */

#include <testing/gunit.h>
#include "grok_parser.h"
#include <base/logging.h>
#include <iostream>
#include <boost/thread.hpp>
#include <boost/chrono.hpp>

std::string msg2("Jan  1 06:25:43 mailserver14 postfix/cleanup[21403]: BEF25A72965: message-id=<20130101142543.5828399CCAF@mailserver14.example.com>");
std::string msg3("55.3.244.1 GET /index.html 15824 0.043");
std::string pat2("OTHER_LOG %{SYSLOGBASE} %{POSTFIX_QUEUEID:queue_id}: %{GREEDYDATA:syslog_message}");
std::string pat3("HTTP_LOG %{IP:client} %{WORD:method} %{URIPATHPARAM:request} %{NUMBER:bytes} %{NUMBER:duration}");

class GrokParserTest : public ::testing::Test {
public:
    virtual void SetUp() {
    }

    virtual void TearDown() {
    }
};

TEST_F(GrokParserTest, DISABLED_Add_Match_n_Delete) {
    GrokParser gp;
    gp.create_grok_instance("OTHER_LOG");
    gp.add_pattern("OTHER_LOG", pat2);
    gp.add_pattern("OTHER_LOG", "POSTFIX_QUEUEID [0-9A-F]{10,11}");
    gp.del_grok_instance("OTHER_LOG");
    gp.create_grok_instance("OTHER_LOG");
    EXPECT_TRUE(gp.match("OTHER_LOG", msg2, NULL));
}

int main(int argc, char **argv) {
    LoggingInit();
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}

