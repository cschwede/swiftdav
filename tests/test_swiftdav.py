# -*- coding: iso-8859-1 -*-

import time
import unittest
import httplib

import mock
import swiftclient
from paste.fixture import TestApp 
from wsgidav.wsgidav_app import DEFAULT_CONFIG, WsgiDAVApp
from swiftdav.swiftdav import SwiftProvider, WsgiDAVDomainController, UploadFile, DownloadFile


class UtilTest(unittest.TestCase):                          
    class DummyResponse(object):
        def __init__(self, data="", status=200):
            self.status = status
            self.data = data

        def read(self, size):
            return self.data

    def test_uploadfile(self):
        with mock.patch('httplib.HTTPConnection') as mock_class:
            instance = mock_class.return_value

            uf = UploadFile("http://127.0.0.1/",
                                  "token", "container", "object", "4")
            uf.write("Hello")
            uf.close()

            mock_class.assert_called_with("127.0.0.1")
            instance.send.assert_called_with('0\r\n\r\n')

            instance.close.assert_called_with()
            expected = [mock.call('5\r\nHello\r\n'), mock.call('0\r\n\r\n')]
            assert instance.send.mock_calls == expected

    def test_downloadfile(self):
        with mock.patch('httplib.HTTPConnection') as mock_class:
            instance = mock_class.return_value
            dummy_response = self.DummyResponse("Hello World!", 200)
            instance.getresponse = mock.Mock(return_value=dummy_response)

            uf = DownloadFile("http://127.0.0.1/", "token", "container", "object")
            assert uf.read(10) == "Hello World!"
            uf.close()

            mock_class.assert_called_with("127.0.0.1")
            instance.close.assert_called_with()


class CloudDavTest(unittest.TestCase):                          

    def setUp(self):
        provider = SwiftProvider()
        domaincontroller = WsgiDAVDomainController('http://dummy/')

        config = DEFAULT_CONFIG.copy()
        config.update({
            "provider_mapping": {"": provider},
            "acceptbasic": True,
            "acceptdigest": False,
            "defaultdigest": False,
            "domaincontroller": domaincontroller,
            })

        wsgi_app = WsgiDAVApp(config)
        self.app = TestApp(wsgi_app)
        
        self.storage_url = "http://127.0.0.1/dummy_url/"
        self.auth_token = "AUTH_dummy"
        self.exception = swiftclient.client.ClientException('')
        swiftclient.client.get_auth = mock.Mock(return_value=(self.storage_url, 
                                                              self.auth_token))
 
        creds = ("account;user" + ":" + "password").encode("base64").strip()
        self.headers = {"Authorization": "Basic %s" % creds, }

    def test_create_container(self):
        app = self.app
        
        swiftclient.client.put_container = mock.Mock()
        app._gen_request("MKCOL", "/container", headers=self.headers, status=201)
    
        swiftclient.client.put_container.assert_called_with(self.storage_url,
                                                            self.auth_token,
                                                            'container')

    def test_list_containers(self):
        app = self.app

        swiftclient.client.get_account = mock.Mock(return_value=(None, 
            [{'name': 'container'}]))
        swiftclient.client.head_container = mock.Mock()

        res = app.get("/", headers=self.headers, status=200)
        assert "WsgiDAV - Index of /" in res, "Could not list root share" 
        assert "/container/" in res, "Missing container name" 

    def test_get_nonexisting_container(self):
        app = self.app
        swiftclient.client.head_container = mock.Mock(side_effect=self.exception)
        app.get("/not-existing-container/", headers=self.headers, status=404)

    def test_unauthenticated(self):
        app = self.app
        app.get("/", status=401)

    def test_delete_container(self):
        app = self.app
        
        swiftclient.client.delete_container = mock.Mock()
        swiftclient.client.head_container = mock.Mock()

        # Non-empty collection/container -> 207 multi-status
        swiftclient.client.get_container = mock.Mock(return_value=([], [{'name': 'x'}]))
        app.delete("/container", headers=self.headers, status=207)
    
        # Empty container
        swiftclient.client.get_container = mock.Mock(return_value=([], []))
        app.delete("/container", headers=self.headers, status=204)
    
        swiftclient.client.delete_container.assert_called_with(self.storage_url,
                                                               self.auth_token,
                                                               'container')

    """
    def test_rename_object(self):
        " Object copy/move/rename is not support -> 403 Forbidden expected"
        app = self.app

        headers = self.headers
        headers['Destination'] = '/container/new' 
        res = app._gen_request("MOVE", "/container/abc", headers=headers, status=403)
    """

    def test_rename_container(self):
        app = self.app
        swiftclient.client.delete_container = mock.Mock()
        swiftclient.client.head_container = mock.Mock()
        swiftclient.client.put_container = mock.Mock()

        headers = self.headers
        headers['Destination'] = '/newname' 
        res = app._gen_request("MOVE", "/container", headers=headers, status=204)
        
        swiftclient.client.delete_container.assert_called_with(self.storage_url,
                                                               self.auth_token,
                                                               'container')
 
        swiftclient.client.put_container.assert_called_with(self.storage_url,
                                                            self.auth_token,
                                                            'newname')
 
    def test_list_objects(self):
        app = self.app

        swiftclient.client.head_container = mock.Mock()
        swiftclient.client.get_container = mock.Mock(return_value=([], 
            [{'name': 'objectname'}]))

        now = time.time()

        object_headers = {'content-length': 1,
                          'content-type': 'application/octet-stream',
                          'x-timestamp': float(now) }

        swiftclient.client.head_object = mock.Mock(return_value=object_headers)

        res = app.get('/container/', headers=self.headers, status=200)
        assert "/container/objectname" in res, "Missing object in container list" 

    def test_get_object(self):
        app = self.app

        object_headers = {'content-length': 12,
                          'content-type': 'application/octet-stream',
                          }

        swiftclient.client.head_container = mock.Mock()
        swiftclient.client.head_object = mock.Mock(return_value=object_headers)
        
        with mock.patch('swiftdav.swiftdav.DownloadFile') as mock_class:
            instance = mock_class.return_value
            instance.read.return_value = "Hello World!"

            res = app.get('http://localhost/container/object',
                              headers=self.headers, status=200)

            mock_class.assert_called_with("http://127.0.0.1/dummy_url/",
                                          self.auth_token,
                                          'container', 'object')

            instance.read.assert_called_with(12)
            instance.close.assert_called_with()
            assert "Hello World!" == res.body

    def test_put_object(self):
        app = self.app

        swiftclient.client.head_container = mock.Mock()
        with mock.patch('swiftdav.swiftdav.UploadFile') as mock_class:
            instance = mock_class.return_value
            headers = self.headers
            headers['Content-Length'] = "4"
            app.put("http://127.0.0.1/container/object", params="data",
                    headers=headers, status=204)

            mock_class.assert_called_with("http://127.0.0.1/dummy_url/",
                                          self.auth_token,
                                          'container', 'object', '4')

            instance.write.assert_called_with('data')
            instance.close.assert_called_with()


if __name__ == "__main__":
    unittest.main()   
