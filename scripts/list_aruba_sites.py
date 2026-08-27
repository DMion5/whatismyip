#!/usr/bin/env python3
"""Manually list Aruba Central sites from inside an application pod.

Usage:
    python scripts/list_aruba_sites.py

This utility is not imported or invoked by the web application. It requests a
short-lived access token from the client credentials already present in the
pod, uses that token to retrieve every site, and keeps the token in this
process only for the duration of the command.
"""

import csv
import json
import os
import sys
from typing import Any

import requests

DEFAULT_BASE_URL = "https://us5.api.central.arubanetworks.com"
DEFAULT_TOKEN_URL = "https://sso.common.cloud.hpe.com/as/token.oauth2"
PAGE_SIZE = 1000
TIMEOUT = 15


def _environment_value(name: str, default: str = "") -> str:
    """Read the OpenShift/Flask name first, with an unprefixed fallback."""
    return os.getenv(f"FLASK_{name}") or os.getenv(name) or default


def request_access_token(
    session: requests.Session, client_id: str, client_secret: str, token_url: str
) -> str:
    """Exchange Aruba client credentials for a short-lived access token."""
    response = session.post(
        token_url,
        headers={"accept": "application/json"},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=TIMEOUT,
        allow_redirects=False,
    )
    response.raise_for_status()
    payload = response.json()
    access_token = payload.get("access_token") if isinstance(payload, dict) else None
    if not access_token:
        raise ValueError("Aruba token response did not include access_token")
    return str(access_token)


def request_sites(
    session: requests.Session, base_url: str, access_token: str
) -> list[dict[str, Any]]:
    """Retrieve all sites from Aruba Central using offset pagination."""
    sites: list[dict[str, Any]] = []
    offset = 0
    url = f"{base_url.rstrip('/')}/network-monitoring/v1/sites-health"

    while True:
        response = session.get(
            url,
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {access_token}",
            },
            params={
                "limit": PAGE_SIZE,
                "offset": offset,
                "sort": "siteName ASC",
            },
            timeout=TIMEOUT,
            allow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ValueError("Aruba sites response did not include an items list")

        page = [item for item in items if isinstance(item, dict)]
        sites.extend(page)
        offset += len(items)

        try:
            total = int(payload["total"])
        except (KeyError, TypeError, ValueError):
            total = None

        if not items or (total is not None and offset >= total):
            break
        if total is None and len(items) < PAGE_SIZE:
            break

    return sites


def format_address(site: dict[str, Any]) -> str:
    """Return a readable address from Central's nested address object."""
    address = site.get("address")
    if isinstance(address, str):
        return address
    if not isinstance(address, dict):
        return ""
    return ", ".join(
        str(address[key])
        for key in ("address", "city", "state", "zipCode", "country")
        if address.get(key)
    )


def print_sites(sites: list[dict[str, Any]]) -> None:
    """Print tab-separated site IDs, names, and addresses."""
    writer = csv.writer(sys.stdout, dialect="excel-tab", lineterminator="\n")
    writer.writerow(("SITE ID", "SITE NAME", "ADDRESS"))
    for site in sorted(
        sites, key=lambda item: str(item.get("siteName", "")).casefold()
    ):
        writer.writerow(
            (site.get("id", ""), site.get("siteName", ""), format_address(site))
        )


def main() -> int:
    """Run the explicitly invoked pod utility."""
    client_id = _environment_value("ARUBA_CENTRAL_CLIENT_ID")
    client_secret = _environment_value("ARUBA_CENTRAL_CLIENT_SECRET")
    if not client_id or not client_secret:
        print(
            "error: FLASK_ARUBA_CENTRAL_CLIENT_ID and "
            "FLASK_ARUBA_CENTRAL_CLIENT_SECRET must be set",
            file=sys.stderr,
        )
        return 2

    token_url = _environment_value("ARUBA_CENTRAL_TOKEN_URL", DEFAULT_TOKEN_URL)
    base_url = _environment_value("ARUBA_CENTRAL_BASE_URL", DEFAULT_BASE_URL)

    try:
        with requests.Session() as session:
            access_token = request_access_token(
                session, client_id, client_secret, token_url
            )
            sites = request_sites(session, base_url, access_token)
    except (requests.RequestException, json.JSONDecodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print_sites(sites)
    print(f"\nTotal sites: {len(sites)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
