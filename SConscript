#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

# -*- mode: python; -*-
# src directory

import sys
import platform

Import('contrail_common_base_doc_files')
Import('contrail_common_io_doc_files')
#requires chnage in controller/src/SConscript
#Analytics section: controller/src/analytics/analytics.sandesh
Import('controller_vns_sandesh_doc_files')

subdirs_no_dup = [
          'contrail-collector',
          'contrail-query-engine',
          'contrail-opserver',
           ]

subdirs_dup = [
          'contrail-snmp-collector',
          'contrail-topology',
           ]

variant_dir_map = {}
variant_dir_map['contrail-collector'] = 'analytics'
variant_dir_map['contrail-query-engine'] = 'query_engine'
variant_dir_map['contrail-snmp-collector'] = 'contrail-snmp-collector'
variant_dir_map['contrail-topology'] = 'contrail-topology'
variant_dir_map['contrail-opserver'] = 'opserver'

include = ['#/src/contrail-analytics', '#/build/include', '#src/contrail-common', '#controller/lib']

libpath = ['#/build/lib']

libs = ['boost_system', 'log4cplus', 'pthread']

common = DefaultEnvironment().Clone()

if common['OPT'] == 'production' or common.UseSystemTBB():
    libs.append('tbb')
else:
    libs.append('tbb_debug')

common.Append(LIBPATH = libpath)
common.Prepend(LIBS = libs)
common.Append(CCFLAGS = '-Wall -Werror -Wsign-compare')
if not sys.platform.startswith('darwin'):
    if platform.system().startswith('Linux'):
       if not platform.linux_distribution()[0].startswith('XenServer'):
          common.Append(CCFLAGS = ['-Wno-unused-local-typedefs'])
if sys.platform.startswith('freebsd'):
    common.Append(CCFLAGS = ['-Wno-unused-local-typedefs'])
common.Append(CPPPATH = include)
common.Append(CCFLAGS = ['-DRAPIDJSON_NAMESPACE=contrail_rapidjson'])

BuildEnv = common.Clone()

if sys.platform.startswith('linux'):
    BuildEnv.Append(CCFLAGS = ['-DLINUX'])
elif sys.platform.startswith('darwin'):
    BuildEnv.Append(CCFLAGS = ['-DDARWIN'])

if sys.platform.startswith('freebsd'):
    BuildEnv.Prepend(LINKFLAGS = ['-lprocstat'])

#
# Message documentation for common modules
#

# base
BuildEnv['BASE_DOC_FILES'] = contrail_common_base_doc_files

# IO
BuildEnv['IO_DOC_FILES'] = contrail_common_io_doc_files

# SANDESH
BuildEnv['VNS_SANDESH_DOC_FILES'] = controller_vns_sandesh_doc_files

# Analytics (contrail-collector)
contrail_collector_doc_files = []
analytics_doc_target = common['TOP'] + '/' + variant_dir_map['contrail-collector'] + '/'
contrail_collector_doc_files += common.SandeshGenDoc('#src/contrail-analytics/contrail-collector/analytics.sandesh', analytics_doc_target)
contrail_collector_doc_files += common.SandeshGenDoc('#src/contrail-analytics/contrail-collector/viz.sandesh', analytics_doc_target)
contrail_collector_doc_files += common.SandeshGenDoc('#src/contrail-analytics/contrail-collector/redis.sandesh', analytics_doc_target)
BuildEnv['ANALYTICS_DOC_FILES'] = contrail_collector_doc_files
#Export('contrail_collector_doc_files')


BuildEnv['INSTALL_DOC_PKG'] = BuildEnv['INSTALL_DOC'] + '/contrail-docs/html'
BuildEnv['INSTALL_MESSAGE_DOC'] = BuildEnv['INSTALL_DOC_PKG'] + '/messages'


for dir in subdirs_no_dup:
    BuildEnv.SConscript(dir + '/SConscript',
                         exports='BuildEnv',
                         variant_dir=BuildEnv['TOP'] + '/' + variant_dir_map[dir],
                         duplicate=0)

for dir in subdirs_dup:
    BuildEnv.SConscript(dirs=[dir],
                         exports='BuildEnv',
                         variant_dir=BuildEnv['TOP'] + '/' + variant_dir_map[dir],
                         duplicate=1)

#AnalyticsEnv.SConscript(dirs=['contrail-snmp-collector'],
#        exports='AnalyticsEnv',
#        variant_dir=BuildEnv['TOP'] + '/contrail-snmp-collector',
#        duplicate=1)

#AnalyticsEnv.SConscript(dirs=['contrail-topology'],
#        exports='AnalyticsEnv',
#        variant_dir=BuildEnv['TOP'] + '/contrail-topology',
#        duplicate=1)
