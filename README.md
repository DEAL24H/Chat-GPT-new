# ĐIỂM TIN 24H

Website tin tức tĩnh chạy trên GitHub Pages, dữ liệu được bot Python cập nhật tự động qua RSS.

## Kiến trúc
- `index.html` + `assets/`: giao diện web, tìm kiếm và lọc theo chủ đề.
- `data/news.json`: dữ liệu tin được bot tạo.
- `bot/news_bot.py`: lấy RSS, chuẩn hóa, chống trùng và giữ 60 tin mới.
- `.github/workflows/news-bot.yml`: chạy thủ công hoặc mỗi giờ, sau đó commit dữ liệu mới vào `main`.
- `.github/workflows/pages.yml`: tự deploy website mỗi khi `main` thay đổi.

## Chạy bot local
```bash
pip install -r bot/requirements.txt
python bot/news_bot.py
```

## Deploy
GitHub Pages dùng workflow `Deploy Pages`. Nếu repository chưa bật Pages/Actions deployment, vào **Settings → Pages → Source: GitHub Actions** một lần. Sau đó các lần push vào `main` sẽ tự deploy.

## Lưu ý
Bot chỉ lưu tiêu đề, mô tả ngắn, thời gian, nguồn và link tới bài gốc; không sao chép toàn văn bài báo.
