import hashlib
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "news.json"

# One leading item per section, then cap the whole homepage at five posts/day.
SOURCES = {
    "Việt Nam": "https://vnexpress.net/rss/tin-moi-nhat.rss",
    "Thế giới": "https://vnexpress.net/rss/the-gioi.rss",
    "Kinh doanh": "https://vnexpress.net/rss/kinh-doanh.rss",
    "Công nghệ": "https://vnexpress.net/rss/so-hoa.rss",
    "Giải trí": "https://vnexpress.net/rss/giai-tri.rss",
}
MAX_POSTS = 5
MAX_SOURCE_CHARS = 12000
OPENAI_MODEL = "gpt-4o-mini"
HEADERS = {"User-Agent": "DiemTin24H/1.0 (+GitHub Pages editorial bot)"}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(text or "", "html.parser").get_text(" ")).strip()


def date_of(entry):
    for key in ("published", "updated"):
        value = entry.get(key)
        if value:
            try:
                return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
            except Exception:
                pass
    return datetime.now(timezone.utc).isoformat()


def post_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def fetch_article(url: str):
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    paragraphs = []
    for p in soup.select("article p, .fck_detail p"):
        text = clean(p.get_text(" "))
        if len(text) >= 35:
            paragraphs.append(text)
    # The source article is used only transiently for summarisation; it is never
    # written to the repository. This avoids republishing the source article.
    text = "\n\n".join(paragraphs)
    return text[:MAX_SOURCE_CHARS]


def ai_summary(source_text: str, title: str, category: str) -> str:
    api_key = __import__("os").environ.get("OPENAI_API_KEY")
    if not api_key or not source_text:
        return ""

    prompt = (
        "Bạn là biên tập viên tin tức. Hãy tạo một bản tóm tắt nguyên bản bằng tiếng Việt "
        "cho trang tổng hợp tin. Không chép lại, không viết lại toàn văn và không mô phỏng "
        "câu chữ của bài gốc. Chỉ giữ các dữ kiện chính có trong nguồn, khoảng 120-180 từ, "
        "có thể chia 2-3 đoạn ngắn. Không bịa thông tin, không thêm nhận xét không có nguồn. "
        f"Tiêu đề: {title}\nChuyên mục: {category}\n\nNội dung nguồn:\n{source_text}"
    )
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": OPENAI_MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "Tóm tắt tin tức chính xác, nguyên bản, ngắn gọn."},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    return clean(response.json()["choices"][0]["message"]["content"])


def main():
    candidates = []
    for category, feed_url in SOURCES.items():
        feed = feedparser.parse(feed_url)
        # RSS ordering is treated as the publisher's current ordering. Only the
        # first valid item in each section is eligible for this day's shortlist.
        for entry in feed.entries:
            title = clean(entry.get("title"))
            url = entry.get("link", "")
            if title and url:
                candidates.append(
                    {
                        "id": post_id(url),
                        "title": title,
                        "url": url,
                        "summary": clean(entry.get("summary", ""))[:300],
                        "category": category,
                        "source": "VnExpress",
                        "published_at": date_of(entry),
                    }
                )
                break

    # Newest five across the selected sections; one item per category by design.
    candidates.sort(key=lambda item: item["published_at"], reverse=True)
    posts = []
    for item in candidates[:MAX_POSTS]:
        try:
            source_text = fetch_article(item["url"])
            summary = ai_summary(source_text, item["title"], item["category"])
            if summary:
                item["summary"] = summary
                item["summary_type"] = "ai"
            else:
                item["summary_type"] = "source_excerpt"
        except Exception as exc:
            print(f"Article processing failed for {item['url']}: {exc}")
            item["summary_type"] = "source_excerpt"
        posts.append(item)

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": posts,
        "policy": {
            "max_posts_per_day": MAX_POSTS,
            "full_source_text_stored": False,
            "source_attribution": True,
            "ai_mode": "summary_only",
        },
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Prepared {len(posts)} posts")


if __name__ == "__main__":
    main()
