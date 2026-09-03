# GA4 cho DEAL24H

DEAL24H đang dùng Google Analytics 4 với Measurement ID `G-R7E164DCZL`.

## Đã hoàn tất trong repo

- Mã GA4 được gắn vào trang chủ.
- Bộ tạo SEO `bot/seo_generator.py` tự gắn GA4 vào các trang danh mục và brand do bot tạo.
- `scripts/verify_ga4.py` kiểm tra toàn bộ HTML public và làm workflow thất bại nếu trang thiếu GA4.
- Admin có mục Analytics đọc snapshot tại `data/analytics.json`.
- `.github/workflows/analytics.yml` định kỳ lấy số liệu GA4 và cập nhật snapshot.

## Phần còn cần cấu hình bên ngoài repo

Để GitHub Actions có thể đọc số liệu GA4 và đưa vào Admin, repository cần 2 GitHub Actions Secrets:

1. `GA4_PROPERTY_ID` — Property ID số của tài sản GA4 DEAL24H. Đây không phải Measurement ID `G-R7E164DCZL` và cũng không phải Data Stream ID `15663857270`.
2. `GA4_SERVICE_ACCOUNT_JSON` — nội dung JSON của Google Cloud service account đã được cấp quyền đọc Google Analytics Data API cho property DEAL24H.

**Không commit JSON service account vào repository và không đưa JSON này vào website.**

## Cách lấy Property ID

Trong Google Analytics: Admin → Cài đặt tài sản → Chi tiết tài sản. Sao chép số Property ID.

## Cách cấp quyền API

Tạo hoặc dùng một Google Cloud service account, bật Google Analytics Data API, sau đó thêm email của service account vào quyền truy cập của property GA4 với quyền đọc/phân tích phù hợp. Tạo JSON key cho service account và lưu toàn bộ JSON đó vào GitHub Actions Secret `GA4_SERVICE_ACCOUNT_JSON`.

## Sau khi secrets được cấu hình

Chạy workflow `Analytics Snapshot` thủ công một lần. Nếu thành công, `data/analytics.json` sẽ chuyển sang `configured: true` và chứa:

- active users
- sessions
- pageviews
- new users
- engagement rate
- dữ liệu theo ngày
- trang được xem nhiều
- quốc gia
- thiết bị

Admin sẽ đọc snapshot này mà không cần chứa credential Google trong trình duyệt.

## Lưu ý về dữ liệu lịch sử

GA4 chỉ cung cấp dữ liệu đã được thu thập bởi property. Việc gắn Measurement ID vào repo không tạo lại dữ liệu truy cập của những ngày trước khi tracking hoạt động.
