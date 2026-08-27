"""Tests for the manually invoked Aruba site-listing utility."""

from scripts.list_aruba_sites import (
    format_address,
    request_access_token,
    request_sites,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.post_calls = []
        self.get_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return FakeResponse({"access_token": "generated-test-token"})

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        offset = kwargs["params"]["offset"]
        if offset == 0:
            return FakeResponse(
                {
                    "items": [
                        {"id": "1", "siteName": "North Campus"},
                        {"id": "2", "siteName": "South Campus"},
                    ],
                    "total": 3,
                }
            )
        return FakeResponse(
            {"items": [{"id": "3", "siteName": "Downtown Campus"}], "total": 3}
        )


def test_requests_token_without_exposing_credentials():
    session = FakeSession()

    token = request_access_token(
        session, "client-id", "client-secret", "https://sso.example.test/token"
    )

    assert token == "generated-test-token"
    assert session.post_calls == [
        (
            "https://sso.example.test/token",
            {
                "headers": {"accept": "application/json"},
                "data": {
                    "grant_type": "client_credentials",
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                },
                "timeout": 15,
                "allow_redirects": False,
            },
        )
    ]


def test_requests_every_site_page():
    session = FakeSession()

    sites = request_sites(
        session, "https://us5.api.central.arubanetworks.com/", "test-token"
    )

    assert [site["id"] for site in sites] == ["1", "2", "3"]
    assert [call[1]["params"]["offset"] for call in session.get_calls] == [0, 2]
    assert all(
        call[1]["headers"]["authorization"] == "Bearer test-token"
        for call in session.get_calls
    )


def test_formats_nested_site_address():
    assert (
        format_address(
            {
                "address": {
                    "address": "1 Capen",
                    "city": "Buffalo",
                    "state": "NY",
                    "zipCode": "14260",
                    "country": "US",
                }
            }
        )
        == "1 Capen, Buffalo, NY, 14260, US"
    )
