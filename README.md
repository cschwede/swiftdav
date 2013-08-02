swiftdav
========

Storage backend for wsgidav using Openstack Swift. 

Quick Install
-------------

1) Install swiftdav:

    git clone git://github.com/cschwede/swiftdav.git
    cd swiftdav
    sudo python setup.py install

2) Set your Swift proxy in swift.conf:

    proxy = 'http://127.0.0.1:8080/auth/v1.0'


3) Run wsgidav with OpenStack Swift backend:

    wsgidav --port 8000 --host=0.0.0.0 --config=swift.conf

4) You have to use ';' instead of ':' to separate account and user in your username,
   for example 'test;tester'. Basic auth uses ':' already to separate username and password.
