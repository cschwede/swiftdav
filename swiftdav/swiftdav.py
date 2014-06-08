# pylint:disable=E1101, C0103

import httplib
import logging
import socket
import urllib
import urlparse

from swiftclient import client

from wsgidav.dav_provider import DAVProvider, DAVCollection, DAVNonCollection
from wsgidav.dav_error import DAVError, HTTP_NOT_FOUND, \
    HTTP_INTERNAL_ERROR, HTTP_METHOD_NOT_ALLOWED, HTTP_CREATED

requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)

swiftclient_log = logging.getLogger("swiftclient")
swiftclient_log.setLevel(logging.WARNING)


class DownloadFile(object):
    """A file-like object for downloading files from Openstack Swift."""

    def __init__(self, storage_url, auth_token, container, objname):
        headers = {'X-Auth-Token': auth_token}

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

        self.conn.request('GET', path, None, headers)
        self.resp = self.conn.getresponse()
        if self.resp.status < 200 or self.resp.status >= 300:
            raise Exception

    def read(self, size):
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

        self.conn.request('PUT', path, None, headers)

    def write(self, data):
        self.conn.send('%x\r\n%s\r\n' % (len(data), data))

    def close(self):
        self.conn.send('0\r\n\r\n')
        self.conn.close()


class ObjectResource(DAVNonCollection):
    def __init__(self, container, objectname, environ, objects=None):
        self.container = container
        self.objectname = objectname
        self.environ = environ
        self.objects = objects

        path = '/' + self.container + '/' + self.objectname
        DAVNonCollection.__init__(self, path, environ)
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
        return float(self.headers.get('x-timestamp', 0))

    def getEtag(self):
        self.get_headers()
        return self.headers.get('etag', '')

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
        dst = '/'.join(destPath.split('/')[2:])
        dst_cont = destPath.split('/')[1]
        try:
            client.head_object(self.storage_url,
                               self.auth_token,
                               self.container,
                               dst,
                               http_conn=self.http_connection)
        except client.ClientException:
            pass

        headers = {'X-Copy-From': self.path}
        try:
            client.put_object(self.storage_url,
                              self.auth_token,
                              dst_cont,
                              dst,
                              headers=headers,
                              http_conn=self.http_connection)
            if self.environ.get("HTTP_OVERWRITE", '') != "T":
                raise DAVError(HTTP_CREATED)
            return True
        except client.ClientException:
            return False

    def beginWrite(self, contentType=None):
        content_length = self.environ.get('CONTENT_LENGTH')

        self.tmpfile = UploadFile(self.storage_url, self.auth_token,
                                  self.container, self.objectname,
                                  content_length)
        return self.tmpfile

    def endWrite(self, withErrors):
        self.tmpfile.close()
        raise DAVError(HTTP_CREATED)

    def supportRecursiveMove(self, destPath):
        return False

    def copyMoveSingle(self, destPath, isMove):
        src = '/'.join(self.path.split('/')[2:])
        dst = '/'.join(destPath.split('/')[2:])
        src_cont = self.path.split('/')[1]
        dst_cont = destPath.split('/')[1]

        headers = {'X-Copy-From': '%s/%s' % (src_cont, src)}
        try:
            client.put_object(self.storage_url,
                              self.auth_token,
                              dst_cont,
                              dst,
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


class ObjectCollection(DAVCollection):
    def __init__(self, container, environ, prefix=None, path=None):
        self.path = path
        path = container
        if path[0] != '/':
            path = '/' + path
        if prefix:
            path += '/' + prefix
        DAVCollection.__init__(self, path, environ)
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
            raise DAVError(HTTP_METHOD_NOT_ALLOWED)
        except client.ClientException:
            pass

        try:
            client.head_object(self.storage_url,
                               self.auth_token,
                               self.container,
                               name + '/',
                               http_conn=self.http_connection)
            raise DAVError(HTTP_METHOD_NOT_ALLOWED)
        except client.ClientException:
            pass

        client.put_object(self.storage_url,
                          self.auth_token,
                          self.container,
                          name + '/',
                          content_type='application/directory',
                          http_conn=self.http_connection)

    def supportRecursiveMove(self, destPath):
        return False

    def copyMoveSingle(self, destPath, isMove):
        src = '/'.join(self.path.split('/')[2:])
        dst = '/'.join(destPath.split('/')[2:])

        src_cont = self.path.split('/')[1]
        dst_cont = destPath.split('/')[1]

        # Make sure target container exists
        try:
            client.put_container(self.storage_url,
                                 self.auth_token,
                                 dst_cont,
                                 http_conn=self.http_connection)
        except:
            pass

        _, objects = client.get_container(self.storage_url,
                                          self.auth_token,
                                          container=src_cont,
                                          delimiter='/',
                                          prefix=src,
                                          http_conn=self.http_connection)

        for obj in objects:
            objname = obj.get('name', obj.get('subdir'))
            headers = {'X-Copy-From': '%s/%s' % (self.container, objname)}
            newname = objname.replace(src, dst)
            if newname[-1] == '/':
                newname = newname.rstrip('/') + '/'
            try:
                client.put_object(self.storage_url,
                                  self.auth_token,
                                  dst_cont,
                                  newname,
                                  headers=headers,
                                  http_conn=self.http_connection)
                if isMove:
                    client.delete_object(self.storage_url,
                                         self.auth_token,
                                         src_cont,
                                         objname,
                                         http_conn=self.http_connection)
            except client.ClientException:
                pass

        # will only succeed if container is empty
        if isMove:
            try:
                client.delete_container(self.storage_url,
                                        self.auth_token,
                                        self.container,
                                        http_conn=self.http_connection)
            except client.ClientException:
                pass

class ContainerCollection(DAVCollection):
    def __init__(self, environ, path):
        DAVCollection.__init__(self, '/', environ)
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
        except client.ClientException, ex:
            if '404' in ex:
                raise DAVError(HTTP_NOT_FOUND)

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
            raise DAVError(HTTP_INTERNAL_ERROR)

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


class SwiftProvider(DAVProvider):
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
