from swiftdav.swiftdav import SwiftProvider, WsgiDAVDomainController
from waitress import serve
from wsgidav.wsgidav_app import DEFAULT_CONFIG, WsgiDAVApp

proxy = 'http://127.0.0.1:8080/auth/v1.0'
insecure = False  # Set to True to disable SSL certificate validation

config = DEFAULT_CONFIG.copy()
config.update({
    "provider_mapping": {"": SwiftProvider()},
    "verbose": 1,
    "propsmanager": True,
    "locksmanager": True,
    "acceptbasic": True,
    "acceptdigest": False,
    "defaultdigest": False,
    "domaincontroller": WsgiDAVDomainController(proxy, insecure)
    })
app = WsgiDAVApp(config)

serve(app, host="0.0.0.0", port=8000, max_request_body_size=5*1024*1024*1024)
