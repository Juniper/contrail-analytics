#!/usr/bin/env python

#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

#
# mockstunnel
#
# This module helps start and stop stunnel instances for unit-testing
# stunnel must be pre-installed for this to work
#

import os
import signal
import subprocess
import logging
import socket
import time

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

stunnel_ver = '5.55'
stunnel_bdir = '/tmp/cache-' + os.environ['USER'] + '-systemless_test'
stunnel_url = stunnel_bdir + '/stunnel-'+stunnel_ver+'.tar.gz'
stunnel_exe = stunnel_bdir + '/bin/stunnel'

def install_stunnel():
    if not os.path.exists(stunnel_bdir):
        output,_ = call_command_("mkdir " + stunnel_bdir)

    if not os.path.exists(stunnel_url):
        process = subprocess.Popen(['wget', '-P', stunnel_bdir,
                                    'https://www.stunnel.org/downloads/stunnel-'\
                                    + stunnel_ver + '.tar.gz'],
                                   cwd=stunnel_bdir)
        process.wait()
        if process.returncode is not 0:
            raise SystemError('wget '+stunnel_url)
    if not os.path.exists(stunnel_bdir + '/stunnel-'+stunnel_ver):
        process = subprocess.Popen(['tar', 'xzvf', stunnel_url],
                                   cwd=stunnel_bdir)
        process.wait()
        if process.returncode is not 0:
            raise SystemError('untar '+stunnel_url)
    if not os.path.exists(stunnel_exe):
        process = subprocess.Popen(['./configure', '--prefix=' + stunnel_bdir], cwd=stunnel_bdir + '/stunnel-'+stunnel_ver)
        process.wait()
        if process.returncode is not 0:
            raise SystemError('./configure'+stunnel_url)
        process = subprocess.Popen(['make'], cwd=stunnel_bdir + '/stunnel-'+stunnel_ver)
        process.wait()
        if process.returncode is not 0:
            raise SystemError('make'+stunnel_url)
        process = subprocess.Popen(['make', 'install'],
                                   cwd=stunnel_bdir + '/stunnel-'+stunnel_ver)
        process.wait()
        if process.returncode is not 0:
            raise SystemError('install '+stunnel_url)

def get_stunnel_path():
    if not os.path.exists(stunnel_exe):
        install_stunnel()
    return stunnel_exe

def start_stunnel(stunnelPort, redisPort, keyfile, certfile):
    '''
    Client uses this function to start an instance of stunnel
    Arguments:
        cport : An unused TCP port for stunnel to use as the client port
    '''
    exe = get_stunnel_path()
    stunnel_conf = "stunnel.conf"

    conftemplate = os.path.dirname(os.path.abspath(__file__)) + "/" +\
        stunnel_conf
    stunnelbase = "/tmp/stunnel.%s.%d/" % (os.getenv('USER', 'None'), stunnelPort)
    output, _ = call_command_("rm -rf " + stunnelbase)
    output, _ = call_command_("mkdir " + stunnelbase)
    output, _ = call_command_("mkdir " + stunnelbase + "cache")

    stunnel_cert = stunnelbase + "stunnel.pem"
    f1 = open(keyfile, "r")
    f2 = open(certfile, "r")
    f  = open(stunnel_cert, "w")
    for files in [f1, f2]:
        f.write(files.read())

    stunnel_pid = stunnelbase + "stunnel.pid"
    logging.info('Stunnel listening on port %d' % stunnelPort)

    print(conftemplate)
    output, _ = call_command_("cp " + conftemplate + " " + stunnelbase +
                              stunnel_conf)
    replace_string_(stunnelbase + stunnel_conf,
                    [("127.0.0.1:6666", "127.0.0.1:" + str(stunnelPort)),
                     ("127.0.0.1:6379" , "127.0.0.1:" + str(redisPort)),
                     ("cert =", "cert = " + stunnel_cert),
                     ("pid =", "pid = " + stunnel_pid)])
    command = exe + " " + stunnelbase + stunnel_conf
    subprocess.Popen(command.split(' '),
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    return True

def stop_stunnel(stunnelPort):
    '''
    Client uses this function to stop an instance of stunnel
    This will only work for stunnel instances that were started by this module
    Arguments:
        cport : The Client Port for the instance of stunnel to be stopped
    '''
    stunnelbase = "/tmp/stunnel.%s.%d/" % (os.getenv('USER', 'None'), stunnelPort)
    stunnel_pid = stunnelbase + "stunnel.pid"
    with open(stunnel_pid, "r") as f:
        pid = f.read(16)
    output, _ = call_command_("kill " + pid.rstrip())
    output, _ = call_command_("rm -rf " + stunnelbase)

def replace_string_(filePath, findreplace):
    "replaces all findStr by repStr in file filePath"
    print filePath
    tempName = filePath + '~~~'
    input = open(filePath)
    output = open(tempName, 'w')
    s = input.read()
    for couple in findreplace:
        outtext = s.replace(couple[0], couple[1])
        s = outtext
    output.write(outtext)
    output.close()
    input.close()
    os.rename(tempName, filePath)


def call_command_(command):
    print(command)
    process = subprocess.Popen(command.split(' '),
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    return process.communicate()


if __name__ == "__main__":
    cs = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cs.bind(("", 0))
    cport = cs.getsockname()[1]
    cs.close()
    start_stunnel(cport, 1000, None, None)
