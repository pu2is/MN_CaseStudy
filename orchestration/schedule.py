"""Serve one daily deployment after the upstream ingestion window."""

from prefect.schedules import Cron

from orchestration.flow import check_roas_and_alert_flow
from orchestration.settings import load_settings


def serve_daily() -> None:
    settings = load_settings()
    check_roas_and_alert_flow.serve(
        name="daily-marketing-performance",
        schedule=Cron("0 8 * * *", timezone=settings.reporting_timezone),
        limit=1,
    )


if __name__ == "__main__":
    serve_daily()
