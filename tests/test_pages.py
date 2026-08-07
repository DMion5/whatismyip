"""Tests for pages blueprint — static pages, redirects, file serving, error handlers."""

import pytest

from whatismyip import create_app


@pytest.fixture
def app(tmp_path):
    db = tmp_path / "metrics.sqlite3"
    return create_app({"TESTING": True, "METRICS_DB_PATH": str(db)})


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


# --- Trailing-slash redirects ---


@pytest.mark.parametrize(
    ("path", "location"),
    [
        ("/about/", "/about"),
        ("/faq/", "/faq"),
        ("/speedtest/", "/speedtest"),
        ("/connectivity/", "/connectivity"),
    ],
)
def test_trailing_slash_redirects(client, path, location):
    response = client.get(path)
    assert response.status_code == 308
    assert response.headers["Location"] == location


# --- Page content ---


def test_home_uses_my_ip_brand_and_placeholder_logo(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"<title>My IP | UB Information Technology</title>" in response.data
    assert b"<span>My IP</span>" in response.data
    assert b"logo/placeholder-logo.svg" in response.data
    assert b"logo/my%20ip%20logo.png" not in response.data
    assert b"IPv6 support is under construction." in response.data
    assert response.data.index(b'id="second_address_section"') < response.data.index(
        b"IPv6 support is under construction."
    )
    assert b'image/x-icon" sizes="32x32" href="/static/logo/favicon.ico' in response.data
    assert b'rel="shortcut icon" href="/static/logo/favicon.ico' in response.data


def test_about_credits_original_project(client):
    response = client.get("/about")

    assert response.status_code == 200
    assert b"https://github.com/unc-network/whatismyip" in response.data
    assert b"William E. Whitaker, Jr." in response.data
    assert b"UNC Information Technology Services" in response.data


def test_connectivity_page_renders(client):
    response = client.get("/connectivity")
    assert response.status_code == 200


# --- Static file serving ---


def test_robots_txt_is_served(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200


def test_sitemap_xml_is_served(client):
    response = client.get("/sitemap.xml")
    assert response.status_code == 200


def test_legacy_favicon_route_serves_ub_icon(client):
    response = client.get("/favicon.ico")

    assert response.status_code == 200
    assert response.mimetype == "image/x-icon"
    assert response.data.startswith(b"\x00\x00\x01\x00")


# --- IndexNow key file ---


def test_indexnow_key_returns_200_when_key_matches(app, client):
    app.config["INDEXNOW_KEY"] = "abc123"
    response = client.get("/abc123.txt")
    assert response.status_code == 200
    assert response.data == b"abc123"


def test_indexnow_key_returns_404_when_no_key_configured(client):
    response = client.get("/anything.txt")
    assert response.status_code == 404


def test_indexnow_key_returns_404_when_filename_does_not_match(app, client):
    app.config["INDEXNOW_KEY"] = "abc123"
    response = client.get("/wrongkey.txt")
    assert response.status_code == 404


# --- Error handlers ---


def test_404_handler_renders_template(client):
    response = client.get("/this-path-does-not-exist-at-all")
    assert response.status_code == 404
    assert b"404" in response.data


def test_500_handler_renders_template(client):
    response = client.get("/trigger-500")
    assert response.status_code == 500
    assert b"500" in response.data
