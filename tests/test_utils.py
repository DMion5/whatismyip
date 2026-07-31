"""Tests for network classification utilities."""

import ipaddress

import pytest

from whatismyip import create_app
from whatismyip.utils import is_campus_ip, is_vpn_ip


@pytest.fixture
def app(tmp_path):
    return create_app(
        {"TESTING": True, "METRICS_DB_PATH": str(tmp_path / "metrics.sqlite3")}
    )


def test_vpn_network_is_treated_as_campus(app, monkeypatch):
    monkeypatch.setitem(app.config, "CAMPUS_NETWORKS", [])
    monkeypatch.setitem(
        app.config, "VPN_NETWORKS", [ipaddress.ip_network("198.51.100.0/24")]
    )

    with app.app_context():
        assert is_vpn_ip("198.51.100.25") is True
        assert is_campus_ip("198.51.100.25") is True
        assert is_vpn_ip("203.0.113.25") is False


def test_network_classification_rejects_invalid_address(app):
    with app.app_context():
        assert is_campus_ip("not-an-ip") is False
        assert is_vpn_ip("not-an-ip") is False
