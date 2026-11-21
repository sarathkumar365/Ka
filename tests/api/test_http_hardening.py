def test_write_from_other_localhost_port_is_refused(make_client):
    c = make_client()
    r = c.post("/api/auth/logout", headers={"origin": "http://localhost:5555"})
    assert r.status_code == 403
    assert c.post("/api/auth/logout", headers={"origin": "http://localhost"}).status_code == 200


def test_bad_content_length_is_400(make_client):
    c = make_client()
    r = c.post("/api/intake/onboarding", content=b"x", headers={"content-length": "abc"})
    assert r.status_code == 400


def test_security_headers_on_every_response(make_client):
    r = make_client(login=False).get("/api/auth/status")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "same-origin"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
