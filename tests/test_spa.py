from fastapi.testclient import TestClient

from factful.api.app import create_app


def build_dist(tmp_path) -> object:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>factful spa</body></html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('hi')", encoding="utf-8")
    (dist / "favicon.ico").write_text("icon", encoding="utf-8")
    return dist


def make_app(frontend_dist) -> TestClient:
    app = create_app(
        env={
            "DATABASE_URL": "sqlite:///:memory:",
            "AUTH_MODE": "mock",
            "SESSION_SECRET": "test-secret",
        },
        frontend_dist=frontend_dist,
    )
    return TestClient(app)


def test_serves_index_at_root(tmp_path) -> None:
    client = make_app(build_dist(tmp_path))
    response = client.get("/")
    assert response.status_code == 200
    assert "factful spa" in response.text


def test_spa_fallback_serves_index_for_client_routes(tmp_path) -> None:
    client = make_app(build_dist(tmp_path))
    for path in ["/stories/42", "/settings", "/stories/7/edit"]:
        response = client.get(path)
        assert response.status_code == 200
        assert "factful spa" in response.text


def test_serves_asset_files(tmp_path) -> None:
    client = make_app(build_dist(tmp_path))
    response = client.get("/assets/app.js")
    assert response.status_code == 200
    assert response.text == "console.log('hi')"


def test_serves_root_level_static_files(tmp_path) -> None:
    client = make_app(build_dist(tmp_path))
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.text == "icon"


def test_api_routes_not_shadowed(tmp_path) -> None:
    client = make_app(build_dist(tmp_path))
    assert client.get("/api/auth/me").status_code == 401
    response = client.post("/api/auth/mock", json={"email": "alice@example.com"})
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_path_traversal_cannot_escape_dist(tmp_path) -> None:
    dist = build_dist(tmp_path)
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    client = make_app(dist)
    response = client.get("/../secret.txt")
    assert "top secret" not in response.text
    assert response.status_code in (200, 404)


def test_missing_dist_means_no_spa_routes(tmp_path) -> None:
    client = make_app(tmp_path / "dist")
    assert client.get("/").status_code == 404
    assert client.get("/settings").status_code == 404
