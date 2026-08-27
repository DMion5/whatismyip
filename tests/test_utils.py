"""Tests for network classification utilities."""

import ipaddress

import pytest

from whatismyip import create_app
from whatismyip.utils import (
    enrich_with_aruba_mobility,
    get_nac_info,
    is_campus_ip,
    is_vpn_ip,
)


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


def test_nac_wireless_record_is_enriched_with_aruba_mobility(app, monkeypatch):
    class FakeXmc:
        error = False
        message = ""

        def __init__(self, *_args, **_kwargs):
            pass

        def getEndSystemByMac(self, _mac):
            return {
                "macAddress": "C2:54:EA:89:12:5F",
                "switchIP": "192.0.2.1",
                "switchPortId": "UB-101-AP01 (00:11:22:33:44:55):eduroam",
            }

        def getEndSystemByIp(self, _ip):
            return None

        def getMacAddress(self, _mac):
            return {"groups": "Wireless"}

    monkeypatch.setitem(
        app.config, "CAMPUS_NETWORKS", [ipaddress.ip_network("192.0.2.0/24")]
    )
    monkeypatch.setitem(app.config, "ARUBA_CENTRAL_ACCESS_TOKEN", "test-token")
    monkeypatch.setattr("whatismyip.utils.XMC_NBI", FakeXmc)
    monkeypatch.setattr(
        "whatismyip.utils.get_nit_building_by_id",
        lambda building_id: {"building_id": building_id},
    )
    monkeypatch.setattr(
        "whatismyip.aruba.get_aruba_client_details",
        lambda _mac: {
            "client_mac": "c2:54:ea:89:12:5f",
            "name": "Dharma's iPhone",
            "ssid": "eduroam",
            "access_point": "UB-202-AP02",
            "auth_type": "802.1X",
            "encryption_method": "WPA2-Enterprise",
            "channel": "44",
            "site": "Capen Hall",
            "snr": 31,
        },
    )
    monkeypatch.setattr(
        "whatismyip.aruba.get_aruba_mobility",
        lambda _mac: {
            "client_mac": "c2:54:ea:89:12:5f",
            "ssid": "eduroam",
            "destination_ap": "UB-202-AP02",
            "rssi": -61,
        },
    )

    with app.app_context():
        result = get_nac_info("192.0.2.50", "c2:54:ea:89:12:5f")
        result = enrich_with_aruba_mobility(result, "c2:54:ea:89:12:5f")

    assert result["aruba_mobility"]["destination_ap"] == "UB-202-AP02"
    assert result["aruba_client"]["auth_type"] == "802.1X"
    assert result["aruba_client"]["snr"] == 31
    assert result["aruba_site_location"]["name"] == "Capen Hall"
    assert result["endSystem"]["wireless_provider"] == "Aruba Central"
    assert "wireless_bssid" not in result["endSystem"]
    # Mobility history must not replace NAC's current AP or its building.
    assert result["endSystem"]["wireless_ap_name"] == "UB-101-AP01"
    assert result["nit_building"] == {"building_id": "101"}
    assert "wireless_signal" not in result
