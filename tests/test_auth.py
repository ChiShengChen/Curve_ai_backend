import uuid


def test_register_and_login(client):
    username = f"user_{uuid.uuid4().hex}"
    resp = client.post(
        "/register",
        json={"username": username, "password": "secret", "role": "user"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data and "refresh_token" in data

    resp = client.post("/login", json={"username": username, "password": "secret"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data and "refresh_token" in data
