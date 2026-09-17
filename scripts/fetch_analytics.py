import json
import os
import time
from datetime import datetime, timezone
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
from google.api_core.exceptions import DeadlineExceeded, ServiceUnavailable, ResourceExhausted, InternalServerError, PermissionDenied
import google.auth
from google.auth.transport.requests import Request
import requests

OUT = "data/analytics.json"
PROPERTY_ID = os.environ.get("GA4_PROPERTY_ID", "").strip()
TRANSIENT_ERRORS = (DeadlineExceeded, ServiceUnavailable, ResourceExhausted, InternalServerError)


def number(row, index=0):
    try:
        return float(row.metric_values[index].value)
    except Exception:
        return 0


def report(client, dimensions, metrics, start="30daysAgo", end="yesterday", limit=100, max_attempts=4):
    req = RunReportRequest(property=f"properties/{PROPERTY_ID}", dimensions=[Dimension(name=x) for x in dimensions], metrics=[Metric(name=x) for x in metrics], date_ranges=[DateRange(start_date=start, end_date=end)], limit=limit)
    for attempt in range(1, max_attempts + 1):
        try:
            return client.run_report(req)
        except PermissionDenied:
            raise
        except TRANSIENT_ERRORS as exc:
            if attempt == max_attempts:
                raise
            delay = min(30, 2 ** (attempt - 1) * 2)
            print(f"GA4 transient error {type(exc).__name__}; retry {attempt}/{max_attempts - 1} in {delay}s")
            time.sleep(delay)


def diagnose_access(credentials):
    try:
        if not credentials.valid:
            credentials.refresh(Request())
        response = requests.get("https://analyticsadmin.googleapis.com/v1beta/accountSummaries", headers={"Authorization": f"Bearer {credentials.token}"}, params={"pageSize": 200}, timeout=30)
        print(f"GA4 Admin API diagnostic HTTP {response.status_code}")
        if response.ok:
            found = []
            for account in response.json().get("accountSummaries", []):
                for prop in account.get("propertySummaries", []):
                    prop_id = str(prop.get("property", "")).replace("properties/", "")
                    found.append((prop_id, prop.get("displayName", ""), account.get("displayName", "")))
            print(f"GA4 properties visible to authenticated service account: {len(found)}")
            for prop_id, name, account_name in found:
                print(f"  - property={prop_id} name={name!r} account={account_name!r}")
            print(f"TARGET PROPERTY {PROPERTY_ID} {'IS' if any(p[0] == PROPERTY_ID for p in found) else 'IS NOT'} VISIBLE TO THIS SERVICE ACCOUNT.")
        else:
            print(response.text[:3000])
    except Exception as exc:
        print(f"GA4 Admin API diagnostic failed: {type(exc).__name__}: {exc}")


def main():
    if not PROPERTY_ID:
        print("GA4_PROPERTY_ID chưa được cấu hình; giữ analytics.json ở trạng thái chưa cấu hình.")
        return True
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/analytics.readonly"])
    client = BetaAnalyticsDataClient(credentials=credentials)
    try:
        totals = report(client, [], ["activeUsers", "sessions", "screenPageViews", "engagementRate", "newUsers"], limit=1)
        t = totals.rows[0] if totals.rows else None
        result = {"configured": True, "updated_at": datetime.now(timezone.utc).isoformat(), "period_days": 30, "totals": {"active_users": int(number(t, 0)) if t else 0, "sessions": int(number(t, 1)) if t else 0, "pageviews": int(number(t, 2)) if t else 0, "engagement_rate": round(number(t, 3) * 100, 1) if t else 0, "new_users": int(number(t, 4)) if t else 0}, "daily": [], "top_pages": [], "countries": [], "devices": [], "message": ""}
        daily = report(client, ["date"], ["activeUsers", "sessions", "screenPageViews"], limit=31)
        result["daily"] = [{"date": r.dimension_values[0].value, "active_users": int(number(r, 0)), "sessions": int(number(r, 1)), "pageviews": int(number(r, 2))} for r in daily.rows]
        pages = report(client, ["pageTitle", "pagePath"], ["screenPageViews", "activeUsers"], limit=10)
        result["top_pages"] = [{"title": r.dimension_values[0].value, "path": r.dimension_values[1].value, "pageviews": int(number(r, 0)), "active_users": int(number(r, 1))} for r in pages.rows]
        countries = report(client, ["country"], ["activeUsers", "sessions"], limit=10)
        result["countries"] = [{"country": r.dimension_values[0].value, "active_users": int(number(r, 0)), "sessions": int(number(r, 1))} for r in countries.rows]
        devices = report(client, ["deviceCategory"], ["activeUsers", "sessions"], limit=10)
        result["devices"] = [{"device": r.dimension_values[0].value, "active_users": int(number(r, 0)), "sessions": int(number(r, 1))} for r in devices.rows]
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Đã cập nhật {OUT}")
        return True
    except PermissionDenied:
        print(f"GA4 Data API denied access to property {PROPERTY_ID}; running access diagnostic...")
        diagnose_access(credentials)
        return False
    except TRANSIENT_ERRORS as exc:
        print(f"GA4 unavailable after retries ({type(exc).__name__}); keeping existing {OUT} snapshot.")
        return False


if __name__ == "__main__":
    # Analytics refresh is non-fatal; the previous snapshot remains usable.
    main()
