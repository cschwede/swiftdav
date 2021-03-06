# Copyright 2014 Christian Schwede <christian.schwede@enovance.com>
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

import time
import unittest

from nose.tools import nottest
import swiftclient
import tinydav


class TestSwiftDav(unittest.TestCase):
    def setUp(self):
        self.webdav = tinydav.WebDAVClient("127.0.0.1", 8000)
        self.webdav.setbasicauth("test;tester", "testing")
        self.swiftclient = swiftclient.Connection(
            'http://127.0.0.1:8080/auth/v1.0', 'test:tester', 'testing')
        self.dirname = 'swiftdav_test_%s' % str(time.time())
        self.filename = 'testfile'
        self.fullname = '/%s/%s' % (self.dirname, self.filename)
        self.dirn2 = 'swiftdav_test_2_%s' % str(time.time())
        self.filen2 = 'testfile2'
        self.fullname2 = '/%s/%s' % (self.dirname, self.filen2)
        self.data = 'dummy'
        self.objectnames = [
            self.filename,
            self.filename + '/',
            self.filename + '/a',
            self.filen2,
            self.filen2 + '/',
            self.filen2 + '/a',
            self.filen2 + '/a/b',
            self.filen2 + '/a/b/c',
        ]

    def tearDown(self):
       for cont in [self.dirname, self.dirn2]:
            for obj in self.objectnames:
                try:
                    self.swiftclient.delete_object(cont, obj)
                except swiftclient.ClientException:
                    pass
                try:
                    self.swiftclient.delete_container(cont)
                except swiftclient.ClientException:
                    pass

    def test_mkdir(self):
        response = self.webdav.mkcol(self.dirname)
        self.assertEqual(201, response)
        self.assertTrue(self.swiftclient.head_container(self.dirname))

    def test_rmdir(self):
        self.swiftclient.put_container(self.dirname)
        self.webdav.delete(self.dirname)
        self.assertRaises(swiftclient.ClientException,
                          self.swiftclient.head_container,
                          self.dirname)

    def test_create_file(self):
        self.swiftclient.put_container(self.dirname)
        self.webdav.put(self.fullname, self.data)

        time.sleep(0.5)
        header, body = self.swiftclient.get_object(self.dirname, self.filename)
        self.assertEqual(self.data, body)

    def test_modify_file(self):
        self.swiftclient.put_container(self.dirname)
        self.swiftclient.put_object(self.dirname, self.filename, "")

        self.webdav.put(self.fullname, self.data)
        time.sleep(0.5)
        header, body = self.swiftclient.get_object(self.dirname, self.filename)
        self.assertEqual(self.data, body)

    def test_read_file(self):
        self.swiftclient.put_container(self.dirname)
        self.swiftclient.put_object(self.dirname, self.filename, self.data)

        response = self.webdav.get(self.fullname)
        self.assertEqual(200, response)
        self.assertEqual(self.data, response.content)

    def test_delete_file(self):
        self.swiftclient.put_container(self.dirname)
        self.swiftclient.put_object(self.dirname, self.filename, self.data)

        response = self.webdav.delete(self.fullname)
        self.assertEqual(204, response)
        self.assertRaises(swiftclient.ClientException,
                          self.swiftclient.head_object,
                          self.dirname, self.filename)

    def test_move_container(self):
		self.swiftclient.put_container(self.dirname)
		response = self.webdav.move(self.dirname + '/', self.dirn2 + '/')
		self.assertEqual(201, response)
		self.assertRaises(swiftclient.ClientException,
                          self.swiftclient.head_container,
                          self.dirname)
		self.assertTrue(self.swiftclient.head_container(self.dirn2))

    def test_move_pseudofolder(self):
        response = self.webdav.mkcol(self.dirname)
        response = self.webdav.mkcol(self.dirname + '/' + self.filename + '/')
        self.assertEqual(201, response)
        response = self.webdav.move(self.dirname + '/' + self.filename + '/', 
                                    self.dirname + '/' + self.filen2 + '/')
        self.assertEqual(201, response)

        # Ensure file is removed from source
        self.assertRaises(swiftclient.ClientException,
                          self.swiftclient.head_object,
                          self.dirname, self.filename + '/')

    def test_move_non_empty_pseudofolder(self):
        self.webdav.mkcol(self.dirname)
        self.webdav.mkcol(self.dirname + '/' + self.filename + '/')
        self.webdav.put(self.dirname + '/' + self.filename + '/a', self.data)
        self.assertRaises(tinydav.HTTPUserError,
                          self.webdav.move,
                          self.dirname + '/' + self.filename + '/',
                          self.dirname + '/' + self.filen2 + '/')

    def test_upload_with_match_and_since(self):
        self.swiftclient.put_container(self.dirname)
        headers = {
            'IF_NONE_MATCH': '*',
            'IF_MODIFIED_SINCE': 'Mon, 02 Jun 2014 00:00:00 GMT',
        }
        self.webdav.put(self.fullname, self.data, headers=headers)
        time.sleep(0.5)
        header, body = self.swiftclient.get_object(self.dirname, self.filename)
        self.assertEqual(self.data, body)

    def test_upload_with_match(self):
        self.swiftclient.put_container(self.dirname)

        headers = {
            'IF_NONE_MATCH': '*',
        }
        self.webdav.put(self.fullname, self.data, headers=headers)
        time.sleep(0.5)
        header, body = self.swiftclient.get_object(self.dirname, self.filename)
        self.assertEqual(self.data, body)

    def test_last_modified_etag(self):
        self.swiftclient.put_container(self.dirname)
        self.swiftclient.put_object(self.dirname, self.filename, "")
        data = self.swiftclient.head_object(self.dirname, self.filename)

        etag = data.get('etag')
        timestamp = data.get('x-timestamp')
        creationdate = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.localtime(float(timestamp)))

        resp = self.webdav.propfind(
            self.fullname, properties=["creationdate", "getetag"])
        self.assertTrue(etag in resp.content)
        self.assertTrue(creationdate in resp.content)

    @nottest
    def test_upload_bigfile(self):
        # Speed depends highly on the used Swift cluster (remote, SSD, ...)
        self.swiftclient.put_container(self.dirname)
        data = ' ' * 1024 * 1024 * 25 # 25 MiB
        start = time.time()
        self.webdav.put(self.fullname, data)
        end = time.time()
        time_taken = end - start
        time.sleep(0.5)
        response = self.swiftclient.head_object(self.dirname, self.filename)
        self.assertEqual(len(data), int(response.get('content-length')))
        self.assertTrue(time_taken < 2.5)
