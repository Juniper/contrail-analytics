/*
 * Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
 */

#include "contrail-collector/redis_connection.h"

RedisAsyncConnection * rac_alloc(EventManager *evm, const std::string & redis_ip,
            unsigned short redis_port,
            RedisAsyncConnection::ClientConnectCbFn client_connect_cb,
            RedisAsyncConnection::ClientDisconnectCbFn client_disconnect_cb,
            bool redis_ssl_enable, const std::string & redis_keyfile,
            const std::string & redis_certfile, const std::string & redis_ca_cert) {
    RedisAsyncConnection * rac =
            new RedisAsyncConnection( evm, redis_ip, redis_port,
                            client_connect_cb, client_disconnect_cb,
                            redis_ssl_enable, redis_keyfile, redis_certfile, redis_ca_cert);
    rac->RAC_Connect();
    return rac;
}
RedisAsyncConnection * rac_alloc_nocheck(EventManager *evm, const std::string & redis_ip,
            unsigned short redis_port,
            RedisAsyncConnection::ClientConnectCbFn client_connect_cb,
            RedisAsyncConnection::ClientDisconnectCbFn client_disconnect_cb,
            bool redis_ssl_enable, const std::string & redis_keyfile,
            const std::string & redis_certfile, const std::string & redis_ca_cert) {
    RedisAsyncConnection * rac =
            new RedisAsyncConnection( evm, redis_ip, redis_port,
                            client_connect_cb, client_disconnect_cb,
                            redis_ssl_enable, redis_keyfile, redis_certfile, redis_ca_cert);
    rac->RAC_Connect();
    return rac;
}
