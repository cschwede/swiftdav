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

from swiftdav import swiftdav
import waitress
from wsgidav import wsgidav_app

# Settings for auth V1, for example tempauth or swauth
proxy = 'http://127.0.0.1:8080/auth/v1.0'
auth_version = 1

# In case of Keystone use the following setting (example):
# proxy = 'http://127.0.0.1:5000/v2.0'
# auth_version = 2

insecure = False  # Set to True to disable SSL certificate validation

config = wsgidav_app.DEFAULT_CONFIG.copy()
config.update({
    "provider_mapping": {"": swiftdav.SwiftProvider()},
    "verbose": 1,
    "propsmanager": True,
    "locksmanager": True,
    "acceptbasic": True,
    "acceptdigest": False,
    "defaultdigest": False,
    "domaincontroller": swiftdav.WsgiDAVDomainController(
        proxy, insecure, auth_version=auth_version)
})
app = wsgidav_app.WsgiDAVApp(config)

waitress.serve(
    app, host="0.0.0.0", port=8000, max_request_body_size=5*1024*1024*1024)
