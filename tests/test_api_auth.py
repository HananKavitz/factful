from authlib.integrations.base_client import MismatchingStateError
from fastapi.testclient import TestClient
from starlette.responses import RedirectResponse

from factful.api import auth
from factful.api.app import create_app
from factful.models import User


def make_client(auth_mode: str = "mock") -> TestClient:
    env = {
        "DATABASE_URL": "sqlite:///:memory:",
        "AUTH_MODE": auth_mode,
        "SESSION_SECRET": "test-secret",
    }
    if auth_mode == "google":
        env.update(
            GOOGLE_CLIENT_ID="test-client-id",
            GOOGLE_CLIENT_SECRET="test-client-secret",
        )
    return TestClient(create_app(env=env), follow_redirects=False)


class FakeGoogleClient:
    def __init__(
        self,
        *,
        userinfo: dict | None = None,
        token_error: Exception | None = None,
    ) -> None:
        self.userinfo_data = userinfo or {
            "sub": "google-123",
            "email": "alice@example.com",
            "name": "Alice",
            "picture": "https://example.com/me.png",
        }
        self.token_error = token_error
        self.redirect_uri: str | None = None

    async def authorize_redirect(self, request, redirect_uri):
        self.redirect_uri = redirect_uri
        return RedirectResponse("https://accounts.google.com/o/oauth2/auth?response_type=code")

    async def authorize_access_token(self, request):
        if self.token_error is not None:
            raise self.token_error
        return {"access_token": "tok"}

    async def userinfo(self, *, token):
        return self.userinfo_data


def install_fake_google(monkeypatch, client: TestClient, fake: FakeGoogleClient) -> None:
    monkeypatch.setattr(auth, "_build_google_client", lambda request: fake)


def test_me_unauthenticated_returns_401() -> None:
    client = make_client()
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_mock_login_then_me() -> None:
    client = make_client()
    response = client.post("/api/auth/mock", json={"email": "alice@example.com"})
    assert response.status_code == 200
    assert response.json()["email"] == "alice@example.com"
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "alice@example.com"


def test_mock_login_reuses_existing_user() -> None:
    client = make_client()
    first = client.post("/api/auth/mock", json={"email": "alice@example.com"}).json()
    second = client.post("/api/auth/mock", json={"email": "alice@example.com"}).json()
    assert first["id"] == second["id"]


def test_mock_login_normalizes_email() -> None:
    client = make_client()
    response = client.post("/api/auth/mock", json={"email": " Alice@Example.com "})
    assert response.status_code == 200
    assert response.json()["email"] == "alice@example.com"


def test_logout_clears_session() -> None:
    client = make_client()
    client.post("/api/auth/mock", json={"email": "alice@example.com"})
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_mock_login_rejected_in_google_mode() -> None:
    client = make_client(auth_mode="google")
    response = client.post("/api/auth/mock", json={"email": "alice@example.com"})
    assert response.status_code == 403


def test_google_login_rejected_in_mock_mode() -> None:
    client = make_client(auth_mode="mock")
    assert client.get("/api/auth/login").status_code == 403
    assert client.get("/api/auth/callback").status_code == 403


def test_google_login_redirects_to_google(monkeypatch) -> None:
    client = make_client(auth_mode="google")
    fake = FakeGoogleClient()
    install_fake_google(monkeypatch, client, fake)

    response = client.get("/api/auth/login")
    assert response.status_code == 307
    assert "accounts.google.com" in response.headers["location"]
    assert fake.redirect_uri.endswith("/api/auth/callback")


def test_google_callback_creates_user_and_sets_session(monkeypatch) -> None:
    client = make_client(auth_mode="google")
    fake = FakeGoogleClient()
    install_fake_google(monkeypatch, client, fake)

    response = client.get("/api/auth/callback?code=x&state=y")
    assert response.status_code == 303
    assert response.headers["location"] == "/"

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"
    assert me.json()["picture"] == "https://example.com/me.png"


def test_google_callback_reuses_existing_user(monkeypatch) -> None:
    client = make_client(auth_mode="google")
    fake = FakeGoogleClient()
    install_fake_google(monkeypatch, client, fake)

    client.get("/api/auth/callback?code=x&state=y")
    client.post("/api/auth/logout")
    client.get("/api/auth/callback?code=x&state=y")

    app = client.app
    with app.state.sessions() as db:
        users = db.query(User).all()
    assert len(users) == 1


def test_google_callback_rejects_state_mismatch(monkeypatch) -> None:
    client = make_client(auth_mode="google")
    fake = FakeGoogleClient(token_error=MismatchingStateError())
    install_fake_google(monkeypatch, client, fake)

    response = client.get("/api/auth/callback?code=x&state=bad")
    assert response.status_code == 400


def test_google_callback_rejects_missing_email(monkeypatch) -> None:
    client = make_client(auth_mode="google")
    fake = FakeGoogleClient(userinfo={"sub": "google-123", "name": "No Email"})
    install_fake_google(monkeypatch, client, fake)

    response = client.get("/api/auth/callback?code=x&state=y")
    assert response.status_code == 400
    assert client.get("/api/auth/me").status_code == 401
