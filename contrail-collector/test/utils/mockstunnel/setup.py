#!/usr/bin/env python

from distutils.core import setup

setup(name='mockstunnel',
      version='1.0',
      description='Stunnel utility for Redis SSL tests',
      author='contrail',
      author_email='contrail-sw@juniper.net',
      url='http://opencontrail.org/',
      packages=['mockstunnel', ],
      data_files=[('lib/python2.7/site-packages/mockstunnel', ['stunnel.conf']),],
     )
