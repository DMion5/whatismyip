"""Tests for whatismyip.db — metrics storage and dashboard aggregation."""

import sqlite3
from datetime import datetime, time, timedelta, timezone

import pytest

from whatismyip import create_app
from whatismyip.db import (
    METRICS_TIMEZONE,
    ensure_metrics_store,
    get_metrics_dashboard,
    log_metrics_event,
)


@pytest.fixture
def app(tmp_path):
    db = tmp_path / "metrics.sqlite3"
    return create_app({"TESTING": True, "METRICS_DB_PATH": str(db)})


# --- ensure_metrics_store ---


def test_ensure_metrics_store_creates_table(app):
    with app.app_context():
        ensure_metrics_store()
        db_path = app.config["METRICS_DB_PATH"]

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "metrics_events" in tables


def test_ensure_metrics_store_is_idempotent(app):
    with app.app_context():
        ensure_metrics_store()
        ensure_metrics_store()  # second call must not raise


def test_ensure_metrics_store_prunes_expired_rows(app, monkeypatch):
    import whatismyip.db as db_module

    monkeypatch.setitem(app.config, "METRICS_RETENTION_DAYS", 30)
    with app.app_context():
        ensure_metrics_store()
        db_path = app.config["METRICS_DB_PATH"]
        old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO metrics_events (created_at, event_type) VALUES (?, ?)",
                (old, "hostinfo"),
            )
            conn.execute(
                "INSERT INTO metrics_events (created_at, event_type) VALUES (?, ?)",
                (recent, "hostinfo"),
            )
            conn.execute(
                "INSERT INTO page_views (created_at, page) VALUES (?, ?)",
                (old, "Home"),
            )
            conn.execute(
                "INSERT INTO page_views (created_at, page) VALUES (?, ?)",
                (recent, "Home"),
            )

        db_module._schema_initialized_for = None
        ensure_metrics_store()

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM metrics_events").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM page_views").fetchone()[0] == 1


# --- log_metrics_event ---


def test_log_metrics_event_writes_row(app):
    with app.app_context():
        log_metrics_event(
            "hostinfo",
            ip_version=4,
            isp="Test ISP",
            city="Buffalo",
            is_campus=True,
        )
        db_path = app.config["METRICS_DB_PATH"]

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM metrics_events WHERE event_type = 'hostinfo'"
        ).fetchone()

    assert row is not None
    assert row["ip_version"] == 4
    assert row["isp"] == "Test ISP"
    assert row["city"] == "Buffalo"
    assert row["is_campus"] == 1


def test_log_metrics_event_dns_result(app):
    with app.app_context():
        log_metrics_event(
            "dns_result",
            dns_filtering="active",
            dns_geo="US",
        )
        db_path = app.config["METRICS_DB_PATH"]

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM metrics_events WHERE event_type = 'dns_result'"
        ).fetchone()

    assert row is not None
    assert row["dns_filtering"] == "active"
    assert row["dns_geo"] == "US"


def test_log_metrics_event_does_not_raise_on_bad_db(app, monkeypatch):
    monkeypatch.setitem(app.config, "METRICS_DB_PATH", "/no/such/dir/metrics.sqlite3")
    with app.app_context():
        log_metrics_event("hostinfo")  # must not raise


# --- get_metrics_dashboard ---


def test_get_metrics_dashboard_returns_expected_keys(app):
    with app.app_context():
        data = get_metrics_dashboard()

    expected = {
        "window_days",
        "total_hostinfo",
        "total_campus",
        "total_remote",
        "daily_series",
        "daily_max",
        "ip_versions",
        "isp_breakdown",
        "org_breakdown",
        "country_breakdown",
        "campus_breakdown",
        "purpose_breakdown",
        "dns_filtering_breakdown",
        "dns_geo_breakdown",
    }
    assert expected <= data.keys()


def test_get_metrics_dashboard_counts_events(app):
    with app.app_context():
        log_metrics_event("hostinfo", is_campus=True)
        log_metrics_event("hostinfo", is_campus=True)
        log_metrics_event("hostinfo", is_campus=False)
        # clear cache so dashboard re-queries
        import whatismyip.db as db_module

        db_module._metrics_cache["data"] = None

        data = get_metrics_dashboard()

    assert data["total_hostinfo"] == 3
    assert data["total_campus"] == 2
    assert data["total_remote"] == 1


def test_get_metrics_dashboard_uses_cache(app):
    with app.app_context():
        import whatismyip.db as db_module

        db_module._metrics_cache["data"] = None
        first = get_metrics_dashboard()
        # write a new event — should NOT appear because cache is warm
        log_metrics_event("hostinfo")
        second = get_metrics_dashboard()

    assert first is second


def test_get_metrics_dashboard_splits_daily_ipv4_and_ipv6(app):
    with app.app_context():
        ensure_metrics_store()
        yesterday = datetime.now(METRICS_TIMEZONE).date() - timedelta(days=1)
        created_at = (
            datetime.combine(yesterday, time(hour=12), tzinfo=METRICS_TIMEZONE)
            .astimezone(timezone.utc)
            .isoformat()
        )
        with sqlite3.connect(app.config["METRICS_DB_PATH"]) as conn:
            conn.executemany(
                """
                INSERT INTO metrics_events (created_at, event_type, ip_version)
                VALUES (?, 'hostinfo', ?)
                """,
                [(created_at, 4), (created_at, 4), (created_at, 6)],
            )

        import whatismyip.db as db_module

        db_module._metrics_cache["data"] = None
        data = get_metrics_dashboard(days=2)

    row = next(item for item in data["daily_series"] if item["day"] == str(yesterday))
    assert row == {"day": str(yesterday), "count": 3, "v4": 2, "v6": 1}


def test_metrics_cache_is_scoped_to_database(app, tmp_path):
    with app.app_context():
        import whatismyip.db as db_module

        db_module._metrics_cache["data"] = None
        log_metrics_event("hostinfo", is_campus=True)
        first = get_metrics_dashboard()

    second_app = create_app(
        {
            "TESTING": True,
            "METRICS_DB_PATH": str(tmp_path / "other-metrics.sqlite3"),
        }
    )
    with second_app.app_context():
        second = get_metrics_dashboard()

    assert first["total_hostinfo"] == 1
    assert second["total_hostinfo"] == 0
