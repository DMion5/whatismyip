"""Tests for whatismyip.db — metrics storage and dashboard aggregation."""

import sqlite3
from datetime import datetime, time, timedelta, timezone

import pytest

import whatismyip.db as db_module
from whatismyip import create_app
from whatismyip.db import (
    METRICS_TIMEZONE,
    ensure_metrics_store,
    get_metrics_dashboard,
    log_metrics_event,
)


@pytest.fixture
def app(tmp_path):
    db_module._metrics_cache.clear()
    db = tmp_path / "metrics.sqlite3"
    return create_app({"TESTING": True, "METRICS_DB_PATH": str(db)})


@pytest.fixture
def metrics_clock(monkeypatch):
    clock = {"now": datetime(2026, 11, 2, 15, 0, tzinfo=METRICS_TIMEZONE)}

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["now"].astimezone(tz)

    monkeypatch.setattr(db_module, "datetime", FrozenDateTime)
    return clock


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
        data = get_metrics_dashboard()

    assert data["total_hostinfo"] == 3
    assert data["total_campus"] == 2
    assert data["total_remote"] == 1


def test_get_metrics_dashboard_uses_cache(app):
    with app.app_context():
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

        data = get_metrics_dashboard(days=2)

    row = next(item for item in data["daily_series"] if item["day"] == str(yesterday))
    assert row == {"day": str(yesterday), "count": 3, "v4": 2, "v6": 1}


def test_metrics_cache_is_scoped_to_database(app, tmp_path):
    with app.app_context():
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


@pytest.mark.parametrize("days", [1, 30, 60, 90])
@pytest.mark.parametrize("month, day", [(3, 9), (11, 2)])
def test_metrics_ranges_share_today_inclusive_boundaries(
    app, metrics_clock, days, month, day
):
    metrics_clock["now"] = datetime(2026, month, day, 15, tzinfo=METRICS_TIMEZONE)
    now = metrics_clock["now"].astimezone(timezone.utc)
    first_day = metrics_clock["now"].date() - timedelta(days=days - 1)
    start = datetime.combine(first_day, time.min, tzinfo=METRICS_TIMEZONE).astimezone(
        timezone.utc
    )
    timestamps = [
        start - timedelta(microseconds=1),
        start,
        now - timedelta(minutes=1),
        now,
        now + timedelta(minutes=1),
    ]
    with app.app_context():
        app.config["METRICS_RETENTION_DAYS"] = 90
        ensure_metrics_store()
        with sqlite3.connect(app.config["METRICS_DB_PATH"]) as conn:
            for timestamp in timestamps:
                conn.execute(
                    """
                    INSERT INTO metrics_events (
                        created_at, event_type, ip_version, is_campus,
                        isp, org, country, network_purpose
                    ) VALUES (?, 'hostinfo', 4, 1, 'Provider', 'Organization', 'US', 'Wired')
                    """,
                    (timestamp.isoformat(),),
                )
                conn.execute(
                    """
                    INSERT INTO metrics_events (
                        created_at, event_type, dns_filtering, dns_geo
                    ) VALUES (?, 'dns_result', 'active', 'Test resolver')
                    """,
                    (timestamp.isoformat(),),
                )
                conn.execute(
                    "INSERT INTO page_views (created_at, page) VALUES (?, 'Home')",
                    (timestamp.isoformat(),),
                )
        data = get_metrics_dashboard(days=days)

    assert data["total_hostinfo"] == data["total_campus"] == 2
    assert data["total_remote"] == 0
    assert len(data["daily_series"]) == len(data["daily_page_views_series"]) == days
    assert data["daily_series"][0]["day"] == first_day.isoformat()
    assert data["daily_series"][-1]["day"] == metrics_clock["now"].date().isoformat()
    assert sum(row["count"] for row in data["daily_series"]) == 2
    assert sum(row["v4"] for row in data["daily_series"]) == 2
    assert sum(row["v6"] for row in data["daily_series"]) == 0
    assert sum(row["count"] for row in data["daily_page_views_series"]) == 2
    for key in (
        "ip_versions",
        "isp_breakdown",
        "org_breakdown",
        "country_breakdown",
        "campus_breakdown",
        "purpose_breakdown",
        "dns_filtering_breakdown",
        "dns_geo_breakdown",
        "page_view_breakdown",
    ):
        assert sum(row["count"] for row in data[key]) == 2, key
    assert data["start_date"] == first_day.isoformat()
    assert data["end_date"] == metrics_clock["now"].date().isoformat()
    assert data["range_label"] == ("Today" if days == 1 else f"Last {days} days")


@pytest.mark.parametrize("days", [1, 30, 60, 90])
def test_empty_metrics_range_has_zero_filled_calendar_days(app, days):
    with app.app_context():
        app.config["METRICS_RETENTION_DAYS"] = 90
        data = get_metrics_dashboard(days=days)
    assert data["total_hostinfo"] == 0
    assert len(data["daily_series"]) == len(data["daily_page_views_series"]) == days
    assert all(row["count"] == 0 for row in data["daily_series"])
    assert all(row["count"] == 0 for row in data["daily_page_views_series"])


@pytest.mark.parametrize("days", [0, -1, 91])
def test_metrics_dashboard_rejects_ranges_outside_retention(app, days):
    with app.app_context():
        app.config["METRICS_RETENTION_DAYS"] = 90
        with pytest.raises(ValueError, match="retention limit"):
            get_metrics_dashboard(days=days)


def test_metrics_cache_keeps_separate_ranges(app):
    with app.app_context():
        today = get_metrics_dashboard(days=1)
        month = get_metrics_dashboard(days=30)
        assert get_metrics_dashboard(days=1) is today
        assert get_metrics_dashboard(days=30) is month
    assert today is not month


def test_metrics_cache_expires_after_one_minute(app):
    with app.app_context():
        first = get_metrics_dashboard(days=1)
        key = next(iter(db_module._metrics_cache))
        cached_at, data = db_module._metrics_cache[key]
        db_module._metrics_cache[key] = (
            cached_at - db_module._METRICS_CACHE_TTL,
            data,
        )
        second = get_metrics_dashboard(days=1)
    assert first is not second


def test_metrics_cache_changes_at_reporting_midnight(app, metrics_clock):
    metrics_clock["now"] = datetime(2026, 11, 2, 23, 59, tzinfo=METRICS_TIMEZONE)
    with app.app_context():
        first = get_metrics_dashboard(days=1)
        metrics_clock["now"] += timedelta(minutes=1)
        second = get_metrics_dashboard(days=1)
    assert first is not second
    assert first["end_date"] == "2026-11-02"
    assert second["end_date"] == "2026-11-03"


def test_metrics_cache_has_a_bounded_size(app, monkeypatch):
    monkeypatch.setattr(db_module, "_METRICS_CACHE_MAX_ENTRIES", 2)
    with app.app_context():
        first = get_metrics_dashboard(days=1)
        get_metrics_dashboard(days=30)
        get_metrics_dashboard(days=60)
        assert len(db_module._metrics_cache) == 2
        assert get_metrics_dashboard(days=1) is not first
        assert len(db_module._metrics_cache) == 2
