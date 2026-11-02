"""Metrics blueprint — aggregate usage dashboard."""

from flask import Blueprint, Response, abort, current_app, render_template, request

from whatismyip.db import get_metrics_dashboard, log_page_view

bp = Blueprint("metrics", __name__)


@bp.route("/metrics")
def metrics() -> Response | tuple[str, int, dict[str, str]]:
    """Display aggregate usage metrics."""
    username = current_app.config.get("METRICS_USERNAME", "")
    password = current_app.config.get("METRICS_PASSWORD", "")
    if username and password:
        auth = request.authorization
        if not auth or auth.username != username or auth.password != password:
            return (
                "Unauthorized",
                401,
                {"WWW-Authenticate": 'Basic realm="Metrics"'},
            )
    retention_days = current_app.config["METRICS_RETENTION_DAYS"]
    default_days = min(current_app.config["METRICS_TIME_WINDOW_DAYS"], retention_days)
    available_days = sorted(
        {1, default_days, retention_days, *range(30, retention_days, 30)}
    )
    requested_days = request.args.getlist("days")
    days = default_days
    if requested_days:
        try:
            days = int(requested_days[0])
        except ValueError:
            abort(400, description="Choose one of the available statistics ranges.")
        if len(requested_days) != 1 or days not in available_days:
            abort(400, description="Choose one of the available statistics ranges.")

    log_page_view("Metrics")
    return render_template(
        "metrics.html",
        metrics=get_metrics_dashboard(days=days),
        available_days=available_days,
        default_days=default_days,
        retention_days=retention_days,
    )
