from unittest.mock import patch

from orchestration.schedule import serve_daily


def test_daily_schedule_uses_reporting_timezone(monkeypatch):
    monkeypatch.setenv("REPORTING_TIMEZONE", "Europe/Berlin")
    with patch("orchestration.schedule.check_roas_and_alert_flow.serve") as serve:
        serve_daily()
    kwargs = serve.call_args.kwargs
    assert kwargs["schedule"].cron == "0 8 * * *"
    assert kwargs["schedule"].timezone == "Europe/Berlin"
    assert kwargs["limit"] == 1
