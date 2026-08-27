"""HPE Aruba Networking Central API integration for wireless enrichment."""

import re
import threading
import time
from typing import Any
from urllib.parse import quote

import requests
from flask import current_app as app

_DEFAULT_BASE_URL = "https://us5.api.central.arubanetworks.com"
_DEFAULT_TOKEN_URL = "https://sso.common.cloud.hpe.com/as/token.oauth2"
_TIMEOUT = 5

_token_lock = threading.Lock()
_token_cache: dict[str, Any] = {
    "access_token": None,
    "expires_at": 0.0,
    "client_id": None,
    "token_url": None,
}


def normalize_mac_address(mac_address: str) -> str | None:
    """Return a colon-delimited lowercase MAC address, or ``None`` if invalid."""
    compact = re.sub(r"[:.\-]", "", (mac_address or "").strip())
    if not re.fullmatch(r"[0-9A-Fa-f]{12}", compact):
        return None
    compact = compact.lower()
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


def _clear_token_cache() -> None:
    """Clear the process-local OAuth token cache (also used by tests)."""
    with _token_lock:
        _token_cache.update(
            {
                "access_token": None,
                "expires_at": 0.0,
                "client_id": None,
                "token_url": None,
            }
        )


def _request_client_credentials_token(force_refresh: bool = False) -> str | None:
    """Get and cache a Central access token using OAuth client credentials."""
    client_id = app.config.get("ARUBA_CENTRAL_CLIENT_ID", "")
    client_secret = app.config.get("ARUBA_CENTRAL_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return None

    token_url = app.config.get("ARUBA_CENTRAL_TOKEN_URL", _DEFAULT_TOKEN_URL)
    now = time.monotonic()
    with _token_lock:
        if (
            not force_refresh
            and _token_cache["access_token"]
            and _token_cache["expires_at"] > now
            and _token_cache["client_id"] == client_id
            and _token_cache["token_url"] == token_url
        ):
            return str(_token_cache["access_token"])

        try:
            response = requests.post(
                token_url,
                headers={"accept": "application/json"},
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=_TIMEOUT,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            app.logger.warning(
                "Aruba Central token request failed: %s", type(exc).__name__
            )
            return None

        if response.status_code != 200:
            app.logger.warning(
                "Aruba Central token endpoint returned %s", response.status_code
            )
            return None

        try:
            payload = response.json()
        except (TypeError, ValueError):
            app.logger.warning("Aruba Central token endpoint returned invalid JSON")
            return None

        access_token = (
            payload.get("access_token") if isinstance(payload, dict) else None
        )
        if not access_token:
            app.logger.warning("Aruba Central token response omitted access_token")
            return None

        try:
            expires_in = max(float(payload.get("expires_in", 7200)), 0)
        except (TypeError, ValueError):
            expires_in = 7200

        # Refresh at least one minute before Central considers the token expired.
        _token_cache.update(
            {
                "access_token": access_token,
                "expires_at": now + max(expires_in - 60, 0),
                "client_id": client_id,
                "token_url": token_url,
            }
        )
        return str(access_token)


def _get_access_token(force_refresh: bool = False) -> tuple[str | None, bool]:
    """Return ``(token, renewable)`` without exposing credentials to callers."""
    if app.config.get("ARUBA_CENTRAL_CLIENT_ID") and app.config.get(
        "ARUBA_CENTRAL_CLIENT_SECRET"
    ):
        return _request_client_credentials_token(force_refresh), True

    # Useful for short-lived testing only. Production should use client credentials.
    access_token = str(app.config.get("ARUBA_CENTRAL_ACCESS_TOKEN", "") or "").strip()
    if access_token.lower().startswith("bearer "):
        access_token = access_token[7:].strip()
    return access_token or None, False


def _as_int(value: Any) -> int | None:
    """Convert Central's numeric strings to integers without raising."""
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _normalize_mobility_event(client_mac: str, item: dict[str, Any]) -> dict[str, Any]:
    """Expose only the latest event fields used by the application."""
    return {
        "client_mac": client_mac,
        "occurred_at": item.get("occurredAt"),
        "ssid": item.get("wlanName"),
        "source_ap": item.get("sourceAp"),
        "destination_ap": item.get("destinationAp"),
        "from_channel": item.get("fromChannel"),
        "channel": item.get("toChannel"),
        "from_bssid": item.get("fromBssid"),
        "bssid": item.get("toBssid"),
        "rssi": _as_int(item.get("rssi")),
        "radio_band": item.get("radioBand"),
        "roam_protocol": item.get("roamProtocol"),
        "roam_time_ms": _as_int(item.get("roamTime")),
    }


def get_aruba_mobility(client_mac: str) -> dict[str, Any] | None:
    """Fetch and normalize the client's latest Aruba Central mobility event."""
    normalized_mac = normalize_mac_address(client_mac)
    if not normalized_mac:
        app.logger.warning("Skipping Aruba Central lookup for an invalid MAC address")
        return None

    token, renewable = _get_access_token()
    if not token:
        return None

    base_url = (
        app.config.get("ARUBA_CENTRAL_BASE_URL", _DEFAULT_BASE_URL) or _DEFAULT_BASE_URL
    ).rstrip("/")
    path_mac = quote(normalized_mac, safe=":")
    url = f"{base_url}/network-monitoring/v1/clients/{path_mac}/mobility-trail"
    params: dict[str, Any] = {"sort": "occurredAt DESC", "limit": 1}
    if app.config.get("ARUBA_CENTRAL_SITE_ID"):
        params["site-id"] = app.config["ARUBA_CENTRAL_SITE_ID"]
    elif app.config.get("ARUBA_CENTRAL_SITE_NAME"):
        params["site-name"] = app.config["ARUBA_CENTRAL_SITE_NAME"]

    response = None
    for attempt in range(2):
        try:
            response = requests.get(
                url,
                headers={
                    "accept": "application/json",
                    "authorization": f"Bearer {token}",
                },
                params=params,
                timeout=_TIMEOUT,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            app.logger.warning(
                "Aruba Central mobility request failed: %s", type(exc).__name__
            )
            return None

        if response.status_code != 401 or not renewable or attempt == 1:
            break
        token, _ = _get_access_token(force_refresh=True)
        if not token:
            return None

    if response is None:
        return None
    if response.status_code == 404:
        app.logger.debug("Aruba Central found no mobility trail for %s", normalized_mac)
        return None
    if response.status_code != 200:
        app.logger.warning(
            "Aruba Central mobility endpoint returned %s", response.status_code
        )
        return None

    try:
        payload = response.json()
    except (TypeError, ValueError):
        app.logger.warning("Aruba Central mobility endpoint returned invalid JSON")
        return None

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return None
    return _normalize_mobility_event(normalized_mac, items[0])
