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

import httplib
import logging
import re
import socket
import urllib
import urlparse

from swiftclient import client

from wsgidav import dav_error
from wsgidav import dav_provider

requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)

swiftclient_log = logging.getLogger("swiftclient")
swiftclient_log.setLevel(logging.WARNING)


def sanitize(name):
    """
    Sanitize object names

    - remove multiple slashes in name
    - remove leading slash
    """
    return re.sub('/+', '/', name).lstrip('/')

def getnames(path):
    elements = [x for x in path.split('/') if x]
    return (elements[0], '/'.join(elements[1:]))


class DownloadFile(object):
    """A file-like object for downloading files from Openstack Swift."""

    def __init__(self, storage_url, auth_token, container, objname):
        self.headers = {'X-Auth-Token': auth_token}
        self.storage_url = storage_url
        self.container = urllib.quote(container)
        self.objname = urllib.quote(objname)

        self.conn = None
        self.resp = None

        conn = self.get_conn()
        conn.request('HEAD', self.path, None, self.headers)
        resp = conn.getresponse()
        conn.close()
        self.closed = True
        if resp.status < 200 or resp.status >= 300:
            raise Exception

    def get_conn(self):
        url = urlparse.urlparse(self.storage_url)
        self.path = "%s/%s/%s" % (url.path, self.container, self.objname)
        if url.scheme == "http":
            conn = httplib.HTTPConnection(url.netloc)
        elif url.scheme == "https":
            conn = httplib.HTTPSConnection(url.netloc)
        else:
            raise Exception
        return conn

    def read(self, size):
        if not self.resp:
            self.conn = self.get_conn()
            self.conn.request('GET', self.path, None, self.headers)
            self.resp = self.conn.getresponse()
        return self.resp.read(size)

    def seek(self, position):
        pass

    def close(self):
        self.conn.close()


class UploadFile(object):
    """A file-like object for uploading files to Openstack Swift."""

    def __init__(self, storage_url, token, container, objname, content_length):
        headers = {'X-Auth-Token': token,
                   'Content-Length': str(content_length),
                   'Transfer-Encoding': 'chunked'}

        container = urllib.quote(container)
        objname = urllib.quote(objname)

        url = urlparse.urlparse(storage_url)
        path = "%s/%s/%s" % (url.path, container, objname)
        if url.scheme == "http":
            self.conn = httplib.HTTPConnection(url.netloc)
        elif url.scheme == "https":
            self.conn = httplib.HTTPSConnection(url.netloc)
        else:
            raise Exception

        self.closed = False
        self.conn.request('PUT', path, None, headers)

    def write(self, data):
        self.conn.send('%x\r\n%s\r\n' % (len(data), data))

    def close(self):
        if not self.closed:
            self.conn.send('0\r\n\r\n')
            self.conn.close()
            self.closed = True


class ObjectResource(dav_provider.DAVNonCollection):
    def __init__(self, container, objectname, environ, objects=None):
        self.container = container
        self.objectname = objectname
        self.environ = environ
        self.objects = objects

        path = '/' + self.container + '/' + self.objectname
        dav_provider.DAVNonCollection.__init__(self, path, environ)
        self.auth_token = self.environ.get('swift_auth_token')
        self.storage_url = self.environ.get('swift_storage_url')

        self.headers = None
        self.tmpfile = None
        self.http_connection = client.http_connection(
            self.storage_url,
            insecure=self.environ.get('insecure'))

    def supportRanges(self):
        return False

    def get_headers(self):
        """Execute HEAD object request.

        Since this info is used in different methods (see below),
        do it once and then use this info.
        """

        if self.headers is None:
            data = self.objects.get(self.objectname)
            if data:
                self.headers = {'content-length': data.get('bytes'),
                                'etag': data.get('hash'), }
            else:
                try:
                    self.headers = client.head_object(
                        self.storage_url,
                        self.auth_token,
                        self.container,
                        self.objectname,
                        http_conn=self.http_connection)
                except client.ClientException:
                    self.headers = {}
                    pass

    def getContent(self):
        return DownloadFile(self.storage_url, self.auth_token,
                            self.container, self.objectname)

    def getContentLength(self):
        self.get_headers()
        return int(self.headers.get('content-length'))

    def getContentType(self):
        self.get_headers()
        return self.headers.get('content-type', 'application/octet-stream')

    def getCreationDate(self):
        self.get_headers()
        timestamp = self.headers.get('x-timestamp')
        if timestamp is not None:
            timestamp = float(timestamp)
        return timestamp

    def getEtag(self):
        self.get_headers()
        return self.headers.get('etag')

    def getLastModified(self):
        """Return LastModified, which is identical to CreationDate."""

        return self.getCreationDate()

    def delete(self):
        try:
                client.delete_object(self.storage_url,
                                     self.auth_token,
                                     self.container,
                                     self.objectname,
                                     http_conn=self.http_connection)
        except client.ClientException:
            pass

    def handleCopy(self, destPath, depthInfinity):
        return False

    def beginWrite(self, contentType=None):
        content_length = self.environ.get('CONTENT_LENGTH')

        self.tmpfile = UploadFile(self.storage_url, self.auth_token,
                                  self.container, self.objectname,
                                  content_length)
        return self.tmpfile


    def endWrite(self, withErrors):
        if self.tmpfile:
            self.tmpfile.close()
            raise dav_error.DAVError(dav_error.HTTP_CREATED)

    def supportRecursiveMove(self, destPath):
        return False

    def copyMoveSingle(self, destPath, isMove):
        src_cont, src = getnames(self.path)
        dst_cont, dst = getnames(destPath)

        headers = {'X-Copy-From': self.path}

        # Ensure target container exists
        if src_cont != dst_cont:
            try:
                client.head_container(self.storage_url,
                                  self.auth_token,
                                  dst_cont,
                                  http_conn=self.http_connection)
            except client.ClientException:
                client.put_container(self.storage_url,
                                  self.auth_token,
                                  dst_cont,
                                  http_conn=self.http_connection)

        try:
            client.put_object(self.storage_url,
                              self.auth_token,
                              dst_cont,
                              sanitize(dst),
                              headers=headers,
                              http_conn=self.http_connection)

            if isMove:
                client.delete_object(self.storage_url,
                                     self.auth_token,
                                     src_cont,
                                     src,
                                     http_conn=self.http_connection)
        except client.ClientException:
            pass


class ObjectCollection(dav_provider.DAVCollection):
    def __init__(self, container, environ, prefix=None, path=None):
        self.path = path
        path = container
        if path[0] != '/':
            path = '/' + path
        if prefix:
            path += '/' + prefix
        dav_provider.DAVCollection.__init__(self, path, environ)
        self.name = path
        self.prefix = prefix
        self.container = container
        if self.prefix:
            self.prefix += '/'
        self.auth_token = self.environ.get('swift_auth_token')
        self.storage_url = self.environ.get('swift_storage_url')
        self.objects = {}

        self.http_connection = client.http_connection(
            self.storage_url,
            insecure=self.environ.get('insecure'))

    def is_subdir(self, name):
        """Checks if given name is a subdir.

        This is a workaround for Swift (and other object storages).

        There are several possibilites for a given URL in the form /ABC/XYZ.
        1. /ABC/XYZ is the full path to an object. In this case there are
            more possibilites, for example get the object, check if it exists,
            put a new object under this name.
        2. /ABC/XYZ should list the contents of container ABC with a prefix XYZ

        The latter one will return en empty result set, thus this will be used
        to differentiate between the possibilites.
        """

        name = name.strip('/')

        obj = self.objects.get(name, self.objects.get(name + '/'))
        if not obj:
            _, objects = client.get_container(self.storage_url,
                                              self.auth_token,
                                              container=self.container,
                                              http_conn=self.http_connection)
            for obj in objects:
                objname = obj.get('name')
                self.objects[objname] = obj

            _, objects = client.get_container(self.storage_url,
                                              self.auth_token,
                                              container=self.container,
                                              delimiter='/',
                                              prefix=name,
                                              http_conn=self.http_connection)
            for obj in objects:
                objname = obj.get('name', obj.get('subdir'))
                self.objects[objname] = obj

        obj = self.objects.get(name, self.objects.get(name + '/', {}))
        if obj.get('subdir') or \
                obj.get('content_type') == 'application/directory':
            return True

        return False

    def getMemberNames(self):
        _stat, objects = client.get_container(self.storage_url,
                                              self.auth_token,
                                              container=self.container,
                                              delimiter='/',
                                              prefix=self.prefix,
                                              http_conn=self.http_connection)

        self.objects = {}

        childs = []
        for obj in objects:
            name = obj.get('name')
            if name and name != self.prefix:
                name = name.encode("utf8")
                childs.append(name)
                self.objects[name] = obj
            subdir = obj.get('subdir')
            if subdir and subdir != self.prefix:
                subdir = subdir.rstrip('/')
                subdir = subdir.encode("utf8")
                # there might be two entries:
                # 1. object with type application/directory and no trailing '/'
                # 2. subdir entry with trailing '/'
                if subdir not in childs:
                    childs.append(subdir)
                    self.objects[subdir] = obj
        return childs

    def getMember(self, objectname):
        """Get member for this ObjectCollection.

        Checks if requested name is a subdir (see above)
        """

        if self.prefix and self.prefix not in objectname:
            objectname = self.prefix + objectname
        if self.is_subdir(objectname):
            return ObjectCollection(self.container, self.environ,
                                    prefix=objectname)
        if self.environ.get('REQUEST_METHOD') in ['PUT']:
            return ObjectResource(self.container, objectname,
                                  self.environ, self.objects)
        try:
            client.head_object(self.storage_url,
                               self.auth_token,
                               self.container,
                               objectname,
                               http_conn=self.http_connection)
            return ObjectResource(self.container, objectname,
                                  self.environ, self.objects)
        except client.ClientException:
            pass
        return None

    def delete(self):
        prefix = '/'.join(self.path.split('/')[2:])
        if '/' + self.container == self.path:
            try:
                client.delete_container(self.storage_url,
                                        self.auth_token,
                                        self.container,
                                        http_conn=self.http_connection)
            except client.ClientException:
                pass
        else:
            try:
                client.delete_object(self.storage_url,
                                     self.auth_token,
                                     self.container,
                                     prefix + '/',
                                     http_conn=self.http_connection)

            except client.ClientException:
                pass

    def createEmptyResource(self, name):
        client.put_object(self.storage_url,
                          self.auth_token,
                          self.container,
                          sanitize(name),
                          http_conn=self.http_connection)
        return ObjectResource(self.container, name, self.environ, self.objects)

    def createCollection(self, name):
        """Create a pseudo-folder."""
        if self.path:
            tmp = self.path.split('/')
            name = '/'.join(tmp[2:]) + '/' + name
        name = name.strip('/')
        try:
            client.head_object(self.storage_url,
                               self.auth_token,
                               self.container,
                               name,
                               http_conn=self.http_connection)
            raise dav_error.DAVError(dav_error.HTTP_METHOD_NOT_ALLOWED)
        except client.ClientException:
            pass

        try:
            client.head_object(self.storage_url,
                               self.auth_token,
                               self.container,
                               name + '/',
                               http_conn=self.http_connection)
            raise dav_error.DAVError(dav_error.HTTP_METHOD_NOT_ALLOWED)
        except client.ClientException:
            pass

        client.put_object(self.storage_url,
                          self.auth_token,
                          self.container,
                          sanitize(name).rstrip('/') + '/',
                          content_type='application/directory',
                          http_conn=self.http_connection)

    def supportRecursiveMove(self, destPath):
        return False

    def copyMoveSingle(self, destPath, isMove):
        src_cont, src = getnames(self.path)
        dst_cont, dst = getnames(destPath)


        # Ensure target container exists
        if src_cont != dst_cont:
            try:
                client.head_container(self.storage_url,
                                  self.auth_token,
                                  dst_cont,
                                  http_conn=self.http_connection)
            except client.ClientException:
                client.put_container(self.storage_url,
                                  self.auth_token,
                                  dst_cont,
                                  http_conn=self.http_connection)

        if self.is_subdir(src):
            client.put_object(self.storage_url,
                              self.auth_token,
                              dst_cont,
                              sanitize(dst).rstrip('/') + '/',
                              content_type='application/directory',
                              http_conn=self.http_connection)
            return

        headers = {'X-Copy-From': self.path}
        try:
            client.put_object(self.storage_url,
                              self.auth_token,
                              dst_cont,
                              sanitize(dst),
                              headers=headers,
                              http_conn=self.http_connection)

            if isMove:
                client.delete_object(self.storage_url,
                                     self.auth_token,
                                     src_cont,
                                     src,
                                     http_conn=self.http_connection)
        except client.ClientException:
            pass


class ContainerCollection(dav_provider.DAVCollection):
    def __init__(self, environ, path):
        dav_provider.DAVCollection.__init__(self, '/', environ)
        self.path = path

        self.auth_token = self.environ.get('swift_auth_token')
        self.storage_url = self.environ.get('swift_storage_url')
        self.http_connection = client.http_connection(
            self.storage_url,
            insecure=self.environ.get('insecure'))

    def getMemberNames(self):
        _, containers = client.get_account(
            self.storage_url,
            self.auth_token,
            http_conn=self.http_connection)
        return [container['name'].encode("utf8") for container in containers]

    def getMember(self, name):
        try:
            client.head_container(self.storage_url,
                                  self.auth_token,
                                  container=name,
                                  http_conn=self.http_connection)
            return ObjectCollection(name, self.environ, path=self.path)
        except client.ClientException as ex:
            if '404' in ex:
                raise dav_error.DAVError(dav_error.HTTP_NOT_FOUND)

    def getDisplayName(self):
        return '/'

    def supportModified(self):
        return False

    def getCreationDate(self):
        """Return CreationDate for container.

        Simply return 0.0 (epoch) since containers don't have this info
        """
        return 0.0

    def delete(self):
        name = self.path.strip('/')
        try:
            client.delete_container(
                self.storage_url,
                self.auth_token,
                name,
                http_conn=self.http_connection)
        except client.ClientException:
            raise dav_error.DAVError(dav_error.HTTP_INTERNAL_ERROR)

    def supportRecursiveMove(self, destPath):
        return False

    def getDirectoryInfo(self):
        return None

    def getEtag(self):
        return None

    def createCollection(self, name):
        client.put_container(
            self.storage_url,
            self.auth_token,
            name,
            http_conn=self.http_connection)


class SwiftProvider(dav_provider.DAVProvider):
    def __init__(self):
        super(SwiftProvider, self).__init__()

    def getResourceInst(self, path, environ):
        root = ContainerCollection(environ, path)
        return root.resolve("/", path)

    def exists(self, path, environ):
        return False


class WsgiDAVDomainController(object):

    def __init__(self, swift_auth_url, insecure=False):
        self.swift_auth_url = swift_auth_url
        self.insecure = insecure

    def __repr__(self):
        return self.__class__.__name__

    def getDomainRealm(self, _inputURL, _environ):
        return "/"

    def requireAuthentication(self, _realmname, _environ):
        return True

    def authDomainUser(self, _realmname, username, password, environ):
        """Returns True if this username/password pair is valid for the realm,
        False otherwise. Used for basic authentication.
        """

        try:
            username = username.replace(';', ':')
            (storage_url, auth_token) = client.get_auth(self.swift_auth_url,
                                                        username, password)
            environ["swift_storage_url"] = storage_url
            environ["swift_auth_token"] = auth_token
            environ["swift_usernampe"] = username
            environ["swift_password"] = password
            environ["swift_auth_url"] = self.swift_auth_url
            environ["insecure"] = self.insecure

            return True
        except client.ClientException:
            return False
        except socket.gaierror:
            return False
