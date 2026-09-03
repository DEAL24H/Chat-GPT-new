import json
import os
from datetime import datetime, timezone
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
from google.api_core.exceptions import PermissionDenied
import google.auth
from google.auth.transport.requests import Request
import requests

OUT = "data/analytics.json"
PROPERTY_ID = os.environ.get("GA4_PROPERTY_ID", "").strip()


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


def diagnose_access(credentials):
    """Show exactly which GA4 properties the authenticated service account can see."""
    try:
        if not credentials.valid:
            credentials.refresh(Request())
        headers = {"Authorization": f"Bearer {credentials.token}"}
        found = []
        page_token = ""
        while True:
            params = {"pageSize": 200}
            if page_token:
                params["pageToken"] = page_token
            response = requests.get(
                "https://analyticsadmin.googleapis.com/v1beta/accountSummaries",
                headers=headers,
                params=params,
                timeout=30,
            )
            print(f"GA4 Admin API diagnostic HTTP {response.status_code}")
            if not response.ok:
                print(response.text[:3000])
                return
            data = response.json()
            for account in data.get("accountSummaries", []):
                for prop in account.get("propertySummaries", []):
                    prop_id = str(prop.get("property", "")).replace("properties/", "")
                    found.append((prop_id, prop.get("displayName", ""), account.get("displayName", "")))
            page_token = data.get("nextPageToken", "")
            if not page_token:
                break

        print(f"GA4 properties visible to authenticated service account: {len(found)}")
        for prop_id, name, account_name in found:
            print(f"  - property={prop_id} name={name!r} account={account_name!r}")
        if PROPERTY_ID and not any(p[0] == PROPERTY_ID for p in found):
            print(f"TARGET PROPERTY {PROPERTY_ID} IS NOT VISIBLE TO THIS SERVICE ACCOUNT.")
        else:
            print(f"TARGET PROPERTY {PROPERTY_ID} IS VISIBLE TO THIS SERVICE ACCOUNT.")
    except Exception as exc:
        print(f"GA4 Admin API diagnostic failed: {type(exc).__name__}: {exc}")


def main():
    if not PROPERTY_ID:
        print("GA4_PROPERTY_ID chưa được cấu hình; giữ analytics.json ở trạng thái chưa cấu hình.")
        return

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/analytics.readonly"]
    )
    client = BetaAnalyticsDataClient(credentials=credentials)

    try:
        totals = report(client, [], ["activeUsers", "sessions", "screenPageViews", "engagementRate", "newUsers"], limit=1)
    except PermissionDenied:
        print(f"GA4 Data API denied access to property {PROPERTY_ID}; running access diagnostic...")
        diagnose_access(credentials)
        raise

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
