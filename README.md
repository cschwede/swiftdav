swiftdav
========

Storage backend for wsgidav using Openstack Swift. Sample config uses Pylons Waitress
to allow chunked uploads; this is required by some clients (eg. OS X Finder).

Quick Install
-------------

1) Install swiftdav:

    git clone git://github.com/cschwede/swiftdav.git
    cd swiftdav
    sudo python setup.py install

2) Modify server.py and configure your Swift proxy settings. Defaults to 'http://127.0.0.1:8080/auth/v1.0'

3) Run wsgidav with OpenStack Swift backend:

    python server.py 

4) You have to use ';' instead of ':' to separate account and user in your username,
   for example 'test;tester'. Basic auth uses ':' already to separate username and password.


Testing
-------

swiftclient recently switched from using httplib to requests. Instead of
rewriting the existing tests just use litmus for testing; this ensures
that the webdav functionality passes well-known tests. You need a running
Swift cluster for tests, a SAIO installation works fine.

Source code: http://www.webdav.org/neon/litmus/

    tar xzvf litmus-0.13.tar.gz 
    cd litmus-0.13/
    ./configure 
    make
    
    swift delete litmus
    make URL=http://127.0.0.1:8000/ CREDS='test\;tester testing' check 
