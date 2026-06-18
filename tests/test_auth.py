class TestRegister:
    def test_register_success(self, client):
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": "newuser",
                "email": "new@example.com",
                "password": "password123",
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["username"] == "newuser"
        assert data["email"] == "new@example.com"
        assert "id" in data

    def test_register_duplicate_username(self, client):
        payload = {
            "username": "dupuser",
            "email": "dup@example.com",
            "password": "password123",
        }
        client.post("/api/v1/auth/register", json=payload)
        resp = client.post(
            "/api/v1/auth/register",
            json={**payload, "email": "other@example.com"},
        )
        assert resp.status_code == 409

    def test_register_validation_error(self, client):
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": "ab", "email": "bad", "password": "short"},
        )
        assert resp.status_code == 422


class TestLogin:
    def test_login_success(self, client):
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "loginuser",
                "email": "login@example.com",
                "password": "password123",
            },
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "loginuser", "password": "password123"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_login_invalid_password(self, client):
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "loginuser2",
                "email": "login2@example.com",
                "password": "password123",
            },
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "loginuser2", "password": "wrong"},
        )
        assert resp.status_code == 401


class TestMe:
    def test_me_authenticated(self, client, auth_headers):
        resp = client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["username"] == "testuser"

    def test_me_unauthenticated(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401
