"""Tests for Aruba Central wireless mobility enrichment."""

from dataclasses import dataclass
from typing import Any

import pytest

from whatismyip import create_app
from whatismyip.aruba import (
    _clear_token_cache,
    get_aruba_client_details,
    get_aruba_mobility,
    normalize_mac_address,
)


@dataclass
class FakeResponse:
    status_code: int
    payload: Any = None
    json_error: Exception | None = None

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


@pytest.fixture
def app(tmp_path):
    _clear_token_cache()
    application = create_app(
        {
            "TESTING": True,
            "METRICS_DB_PATH": str(tmp_path / "metrics.sqlite3"),
            "ARUBA_CENTRAL_BASE_URL": "https://us5.api.central.arubanetworks.com",
            "ARUBA_CENTRAL_TOKEN_URL": "https://sso.example.test/token",
            "ARUBA_CENTRAL_CLIENT_ID": "",
            "ARUBA_CENTRAL_CLIENT_SECRET": "",
            "ARUBA_CENTRAL_ACCESS_TOKEN": "",
            "ARUBA_CENTRAL_SITE_ID": "",
            "ARUBA_CENTRAL_SITE_NAME": "",
        }
    )
    yield application
    _clear_token_cache()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("c2:54:ea:89:12:5f", "c2:54:ea:89:12:5f"),
        ("C2-54-EA-89-12-5F", "c2:54:ea:89:12:5f"),
        ("c254.ea89.125f", "c2:54:ea:89:12:5f"),
        ("not-a-mac", None),
        ("", None),
    ],
)
def test_normalize_mac_address(raw, expected):
    assert normalize_mac_address(raw) == expected


def test_mobility_lookup_uses_correct_endpoint_and_normalizes_response(
    app, monkeypatch
):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(
            200,
            {
                "items": [
                    {
                        "occurredAt": 1_787_853_714_000,
                        "roamTime": "42",
                        "wlanName": "eduroam",
                        "sourceAp": "UB-101-AP01",
                        "destinationAp": "UB-101-AP02",
                        "fromChannel": "36",
                        "toChannel": "44",
                        "fromBssid": "00:11:22:33:44:55",
                        "toBssid": "00:11:22:33:44:66",
                        "rssi": "-61",
                        "radioBand": "5GHz",
                        "roamProtocol": "11r",
                    }
                ]
            },
        )

    monkeypatch.setattr("whatismyip.aruba.requests.get", fake_get)
    app.config["ARUBA_CENTRAL_ACCESS_TOKEN"] = "short-lived-test-token"

    with app.app_context():
        result = get_aruba_mobility("C2-54-EA-89-12-5F")

    assert calls[0][0] == (
        "https://us5.api.central.arubanetworks.com/network-monitoring/v1/"
        "clients/c2:54:ea:89:12:5f/mobility-trail"
    )
    assert "%22" not in calls[0][0]
    assert calls[0][1]["headers"] == {
        "accept": "application/json",
        "authorization": "Bearer short-lived-test-token",
    }
    assert calls[0][1]["params"] == {"sort": "occurredAt DESC", "limit": 1}
    assert calls[0][1]["timeout"] == 5
    assert result == {
        "client_mac": "c2:54:ea:89:12:5f",
        "occurred_at": 1_787_853_714_000,
        "ssid": "eduroam",
        "source_ap": "UB-101-AP01",
        "destination_ap": "UB-101-AP02",
        "from_channel": "36",
        "channel": "44",
        "rssi": -61,
        "radio_band": "5GHz",
        "roam_protocol": "11r",
        "roam_time_ms": 42,
    }


def test_client_details_lookup_normalizes_requested_wireless_fields(app, monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(
            200,
            {
                "clientName": "Dharma's iPhone",
                "macAddress": "c2:54:ea:89:12:5f",
                "wlanName": "eduroam",
                "connectedTo": "wls-cap-101",
                "authenticationType": "802.1X",
                "wirelessSecurity": "WPA2-Enterprise",
                "wirelessChannel": "44",
                "wirelessBand": "5GHZ",
                "siteName": "North Campus",
                "snr": "31",
                "bssid": "00:11:22:33:44:66",
            },
        )

    monkeypatch.setattr("whatismyip.aruba.requests.get", fake_get)
    app.config["ARUBA_CENTRAL_ACCESS_TOKEN"] = "short-lived-test-token"

    with app.app_context():
        result = get_aruba_client_details("C2-54-EA-89-12-5F")

    assert calls[0][0] == (
        "https://us5.api.central.arubanetworks.com/network-monitoring/v1/"
        "clients/c2:54:ea:89:12:5f"
    )
    assert calls[0][1]["params"] is None
    assert result == {
        "client_mac": "c2:54:ea:89:12:5f",
        "name": "Dharma's iPhone",
        "ssid": "eduroam",
        "access_point": "wls-cap-101",
        "auth_type": "802.1X",
        "encryption_method": "WPA2-Enterprise",
        "channel": "44",
        "radio_band": "5GHZ",
        "site": "North Campus",
        "snr": 31,
    }
    assert "bssid" not in result


def test_static_token_accepts_bearer_prefix(app, monkeypatch):
    authorization = []

    def fake_get(_url, **kwargs):
        authorization.append(kwargs["headers"]["authorization"])
        return FakeResponse(200, {"items": [{"destinationAp": "wls-cc3-5"}]})

    monkeypatch.setattr("whatismyip.aruba.requests.get", fake_get)
    app.config["ARUBA_CENTRAL_ACCESS_TOKEN"] = "  Bearer test-token  "

    with app.app_context():
        assert get_aruba_mobility("c2:54:ea:89:12:5f") is not None

    assert authorization == ["Bearer test-token"]


def test_client_credentials_token_is_cached(app, monkeypatch):
    post_calls = []
    get_calls = []

    def fake_post(url, **kwargs):
        post_calls.append((url, kwargs))
        return FakeResponse(
            200, {"access_token": "generated-token", "expires_in": 7199}
        )

    def fake_get(url, **kwargs):
        get_calls.append((url, kwargs))
        return FakeResponse(200, {"items": [{"rssi": "-67"}]})

    monkeypatch.setattr("whatismyip.aruba.requests.post", fake_post)
    monkeypatch.setattr("whatismyip.aruba.requests.get", fake_get)
    app.config.update(
        ARUBA_CENTRAL_CLIENT_ID="client-id",
        ARUBA_CENTRAL_CLIENT_SECRET="client-secret",
    )

    with app.app_context():
        assert get_aruba_mobility("c2:54:ea:89:12:5f")["rssi"] == -67
        assert get_aruba_mobility("c2:54:ea:89:12:5f")["rssi"] == -67

    assert len(post_calls) == 1
    assert post_calls[0][0] == "https://sso.example.test/token"
    assert post_calls[0][1]["data"] == {
        "grant_type": "client_credentials",
        "client_id": "client-id",
        "client_secret": "client-secret",
    }
    assert len(get_calls) == 2
    assert all(
        call[1]["headers"]["authorization"] == "Bearer generated-token"
        for call in get_calls
    )


def test_unauthorized_generated_token_is_refreshed_once(app, monkeypatch):
    tokens = iter(("first-token", "second-token"))
    authorization_headers = []

    def fake_post(_url, **_kwargs):
        return FakeResponse(200, {"access_token": next(tokens), "expires_in": 7199})

    def fake_get(_url, **kwargs):
        authorization_headers.append(kwargs["headers"]["authorization"])
        if len(authorization_headers) == 1:
            return FakeResponse(401)
        return FakeResponse(200, {"items": [{"destinationAp": "UB-101-AP02"}]})

    monkeypatch.setattr("whatismyip.aruba.requests.post", fake_post)
    monkeypatch.setattr("whatismyip.aruba.requests.get", fake_get)
    app.config.update(
        ARUBA_CENTRAL_CLIENT_ID="client-id",
        ARUBA_CENTRAL_CLIENT_SECRET="client-secret",
    )

    with app.app_context():
        result = get_aruba_mobility("c2:54:ea:89:12:5f")

    assert result["destination_ap"] == "UB-101-AP02"
    assert authorization_headers == ["Bearer first-token", "Bearer second-token"]


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(404),
        FakeResponse(429),
        FakeResponse(200, {"items": []}),
        FakeResponse(200, None),
        FakeResponse(200, json_error=ValueError("bad JSON")),
    ],
)
def test_mobility_lookup_failures_return_none(app, monkeypatch, response):
    monkeypatch.setattr(
        "whatismyip.aruba.requests.get", lambda _url, **_kwargs: response
    )
    app.config["ARUBA_CENTRAL_ACCESS_TOKEN"] = "short-lived-test-token"

    with app.app_context():
        assert get_aruba_mobility("c2:54:ea:89:12:5f") is None
