"""HUD serves only explicit assets and preserves the existing control surface."""
import http.client
from tests.test_v301_companion_http import http_server, request


def test_hud_assets_are_local_and_have_correct_types(http_server):
    for route, mime in [('/hud.css','text/css'),('/hud.js','text/javascript'),
                        ('/hud-backdrop.png','image/png'),('/hud-core.png','image/png'),
                        ('/hud-icon-circuit-tree.svg','image/svg+xml')]:
        conn = http.client.HTTPConnection('127.0.0.1',http_server.server_address[1],timeout=4)
        conn.request('GET',route);r=conn.getresponse();data=r.read()
        assert r.status == 200 and r.getheader('Content-Type').startswith(mime)
        assert "default-src 'self'" in r.getheader('Content-Security-Policy')
        assert len(data)>50
        conn.close()
    assert request(http_server,'GET','/hud-../config.yaml')[0] == 404
    assert request(http_server,'GET','/PHOSPHOR_LICENSE.txt')[0] == 404
