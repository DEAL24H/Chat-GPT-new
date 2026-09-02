import hashlib
import json
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "news.json"
SOURCES = {
    "Việt Nam": "https://vnexpress.net/rss/tin-moi-nhat.rss",
    "Thế giới": "https://vnexpress.net/rss/the-gioi.rss",
    "Kinh doanh": "https://vnexpress.net/rss/kinh-doanh.rss",
    "Công nghệ": "https://vnexpress.net/rss/so-hoa.rss",
    "Giải trí": "https://vnexpress.net/rss/giai-tri.rss",
}
MAX_POSTS = 5
MAX_SOURCE_CHARS = 12000
MODEL = "llama3.1-8b"
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


def fetch_article_text(url: str) -> str:
    # Source text is fetched transiently for factual summarisation and is never
    # written to the repository or republished as a rewritten full article.
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    paragraphs = []
    for p in soup.select("p.Normal"):
        text = clean(p.get_text(" "))
        if len(text) >= 35:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)[:MAX_SOURCE_CHARS]


def ai_summary(source_text: str, title: str, category: str) -> str:
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key or not source_text:
        return ""
    # Cerebras' OpenAI-compatible inference endpoint is /v1, not the public
    # cerebras.ai website. This keeps the OpenAI SDK interface while routing to Cerebras.
    client = OpenAI(
        base_url="https://api.cerebras.ai/v1",
        api_key=api_key,
    )
    prompt = (
        "Bạn là biên tập viên của một trang tổng hợp tin tức. Hãy tạo một bản tóm tắt "
        "nguyên bản bằng tiếng Việt, không chép lại và không viết lại toàn văn bài nguồn. "
        "Giữ các dữ kiện chính, không bịa, không thêm nhận xét. Dài khoảng 120-180 từ, "
        "chia thành 2-3 đoạn ngắn.\n\n"
        f"Tiêu đề: {title}\nChuyên mục: {category}\n\nNội dung nguồn:\n{source_text}"
    )
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": "Tóm tắt tin tức chính xác, nguyên bản, ngắn gọn."},
            {"role": "user", "content": prompt},
        ],
    )
    return clean(response.choices[0].message.content or "")


def main():
    candidates = []
    for category, feed_url in SOURCES.items():
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            title = clean(entry.get("title"))
            url = entry.get("link", "")
            if title and url:
                candidates.append({
                    "id": post_id(url),
                    "title": title,
                    "url": url,
                    "summary": clean(entry.get("summary", ""))[:300],
                    "category": category,
                    "source": "VnExpress",
                    "published_at": date_of(entry),
                })
                break

    candidates.sort(key=lambda item: item["published_at"], reverse=True)
    posts = []
    for item in candidates[:MAX_POSTS]:
        try:
            source_text = fetch_article_text(item["url"])
            summary = ai_summary(source_text, item["title"], item["category"])
            if summary:
                item["summary"] = summary
                item["summary_type"] = "cerebras_ai"
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
            "source_images_stored": False,
            "source_attribution": True,
            "ai_mode": "factual_summary_only",
            "ai_provider": "Cerebras",
            "ai_model": MODEL,
        },
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Prepared {len(posts)} posts")


if __name__ == "__main__":
    main()
