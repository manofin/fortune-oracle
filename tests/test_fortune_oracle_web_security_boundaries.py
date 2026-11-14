"""Invalid client inputs preserve the previously saved profile."""

import secrets
import pytest
from test_fortune_oracle_web import app, session, PROFILE


@pytest.mark.parametrize('change', [{'birth_time': '１２:３０'}, {'birth_time': '١٢:٣٠'},
    {'display_name': '\ud800'}, {'timezone': '\ud800'}, {'birth_date': '\ud800'}])
def test_invalid_unicode_preserves_profile(app, change):
    client = app.test_client(); headers = session(client)
    assert client.put('/api/profile', headers=headers, json=PROFILE).status_code == 200
    before = client.get('/api/session').json['profile']
    assert client.put('/api/profile', headers=headers, json={**PROFILE, **change}).status_code == 400
    assert client.get('/api/session').json['profile'] == before
    assert client.get('/api/chart').json['computed'] is True


def test_non_ascii_csrf_and_methods(app):
    client = app.test_client(); headers = session(client)
    assert client.put('/api/profile', headers=headers, json=PROFILE).status_code == 200
    before = client.get('/api/session').json['profile']
    assert client.put('/api/profile', headers={'X-CSRF-Token': secrets.token_hex(32) + 'é'}, json=PROFILE).status_code == 403
    assert client.get('/api/session').json['profile'] == before
    for path, method in [('/api/profile', 'POST'), ('/api/chart', 'PUT'), ('/api/session', 'DELETE')]:
        assert client.open(path, method=method).status_code == 405
        assert app.test_client().open(path, method=method).status_code == 405
