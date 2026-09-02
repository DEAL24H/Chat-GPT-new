import json
import os
from datetime import date, timedelta, datetime, timezone
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
from google.oauth2 import service_account

OUT = "data/analytics.json"
PROPERTY_ID = os.environ.get("GA4_PROPERTY_ID", "").strip()
SERVICE_JSON = os.environ.get("GA4_SERVICE_ACCOUNT_JSON", "").strip()


def number(row, index=0):
    try:
        return float(row.metric_values[index].value)
    except Exception:
        return 0


def report(client, dimensions, metrics, start="30daysAgo", end="yesterday", limit=100):
    req = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name=x) for x in dimensions],
        metrics=[Metric(name=x) for x in metrics],
        date_ranges=[DateRange(start_date=start, end_date=end)],
        limit=limit,
    )
    return client.run_report(req)


def main():
    if not PROPERTY_ID or not SERVICE_JSON:
        print("GA4 chưa được cấu hình; giữ analytics.json ở trạng thái chưa cấu hình.")
        return

    credentials = service_account.Credentials.from_service_account_info(
        json.loads(SERVICE_JSON),
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    )
    client = BetaAnalyticsDataClient(credentials=credentials)

    totals = report(client, [], ["activeUsers", "sessions", "screenPageViews", "engagementRate", "newUsers"], limit=1)
    t = totals.rows[0] if totals.rows else None
    result = {
        "configured": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "period_days": 30,
        "totals": {
            "active_users": int(number(t, 0)) if t else 0,
            "sessions": int(number(t, 1)) if t else 0,
            "pageviews": int(number(t, 2)) if t else 0,
            "engagement_rate": round(number(t, 3) * 100, 1) if t else 0,
            "new_users": int(number(t, 4)) if t else 0,
        },
        "daily": [],
        "top_pages": [],
        "countries": [],
        "devices": [],
        "message": "",
    }

    daily = report(client, ["date"], ["activeUsers", "sessions", "screenPageViews"], limit=31)
    for r in daily.rows:
        result["daily"].append({
            "date": r.dimension_values[0].value,
            "active_users": int(number(r, 0)),
            "sessions": int(number(r, 1)),
            "pageviews": int(number(r, 2)),
        })

    pages = report(client, ["pageTitle", "pagePath"], ["screenPageViews", "activeUsers"], limit=10)
    for r in pages.rows:
        result["top_pages"].append({
            "title": r.dimension_values[0].value,
            "path": r.dimension_values[1].value,
            "pageviews": int(number(r, 0)),
            "active_users": int(number(r, 1)),
        })

    countries = report(client, ["country"], ["activeUsers", "sessions"], limit=10)
    for r in countries.rows:
        result["countries"].append({
            "country": r.dimension_values[0].value,
            "active_users": int(number(r, 0)),
            "sessions": int(number(r, 1)),
        })

    devices = report(client, ["deviceCategory"], ["activeUsers", "sessions"], limit=10)
    for r in devices.rows:
        result["devices"].append({
            "device": r.dimension_values[0].value,
            "active_users": int(number(r, 0)),
            "sessions": int(number(r, 1)),
        })

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Đã cập nhật {OUT}")


if __name__ == "__main__":
    main()
