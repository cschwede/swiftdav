# -*- encoding: utf-8 -*-
# Copyright 2013 Christian Schwede <info@cschwede.de>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# pylint:disable=E1101, C0103

__author__ = "Christian Schwede <info@cschwede.de>"
name = 'swiftdav'
version = '0.1'

import setuptools

setuptools.setup(
    name=name,
    version=version,
    description='Webdav server for Openstack Swift',
    license='Apache License (2.0)',
    author='Christian Schwede',
    author_email='info@cschwede.de',
    url='https://github.com/cschwede/%s' % (name),
    packages=setuptools.find_packages(),
    test_suite='nose.collector',
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.6',
        'Environment :: No Input/Output (Daemon)'],
    install_requires=['waitress', 'wsgidav', 'python-swiftclient'],
)
