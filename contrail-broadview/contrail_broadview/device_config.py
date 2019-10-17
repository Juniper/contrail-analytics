#
# Copyright (c) 2015 Juniper Networks, Inc. All rights reserved.
#

from __future__ import print_function
from future import standard_library
standard_library.install_aliases()
from builtins import object
import copy
from six.moves import configparser

class DeviceConfig(object):
    def __init__(self, name, cfg={}):
        self._raw = cfg
        self._name = name
        self._prop = None

    def name(self):
        return self._name

    def ip(self):
        return self._raw['ip']

    def port(self):
        return int(self._raw['port'])

    def switch_properties(self):
        return self._prop

    def set_switch_properties(self, p):
        self._prop = p

    def asics(self):
        if self._prop:
            for ai in self._prop['result']['asic-info']:
                yield ai[0]

    @staticmethod
    def from_file(filename):
        devices = []
        devcfg = configparser.SafeConfigParser()
        devcfg.optionxform = str
        devcfg.read([filename])
        print(devcfg)
        for dev in devcfg.sections():
            nd = dict(devcfg.items(dev))
            devices.append(DeviceConfig(dev, nd))
        return devices
