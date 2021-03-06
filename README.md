# swiftdav

Webdav server using Openstack Swift as a backend. Sample config uses Pylons
Waitress to allow chunked uploads; this is required by some clients (eg. OSX).

## Quick Install

1) Install swiftdav:

    git clone git://github.com/cschwede/swiftdav.git
    cd swiftdav
    sudo python setup.py install

2) Modify server.py and configure your Swift proxy settings. Defaults to 'http://127.0.0.1:8080/auth/v1.0'.
   If you are using Keystone you need to set the auth_version to 2 and use the Keystone URL.

3) Run wsgidav with OpenStack Swift backend:

    python server.py 

4) You have to use ';' instead of ':' to separate account and user in your username,
   for example 'test;tester'. Basic auth uses ':' already to separate username and password.

## Notes

### davfs2
If you're using [davfs2](http://savannah.nongnu.org/projects/davfs2/) you could use the following settings in /etc/davfs2/davfs2.conf:

    use_locks       0
    precheck        0

Due to Swifts eventual consistency there is no guarentee that locking and prechecking succeeds.
However, swiftdav supports some fake locking because some clients require this to enable
write access.

### Renaming
Renaming is currently only allowed for empty containers and empty pseudofolders. Copying, moving
and renaming of containers and objects is only possible by executing a remote COPY and this
requires a lot of resources and is a non-atomic operation. This can create various problems on
the client side and is thus no longer supported.

### Windows
There are a few settings you might need to change:

1. Slow response on Windows 7: http://support.microsoft.com/kb/2445570
2. Problems with files larger than 50MB: http://support.microsoft.com/kb/2668751
3. Error "The folder name is not valid": http://support.microsoft.com/kb/928692

Testing
-------

Functional tests require a running server and Swift installation (SAIO). Just
start them with your favorite test runner, eg.:

    nosetests

There is an additional shell script to execute some basic operations on a davfs2
mountpoint located in test/test_davfs2.sh.

You can also run the litmus test suite. However, a lot of tests will fail because copying
and moving of objects as well as proper locking are not supported.

Source code: http://www.webdav.org/neon/litmus/

    tar xzvf litmus-0.13.tar.gz 
    cd litmus-0.13/
    ./configure 
    make
    
    swift delete litmus
    make URL=http://127.0.0.1:8000/ CREDS='test\;tester testing' check 
