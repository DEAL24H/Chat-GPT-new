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
MAX_SOURCE_CHARS = 24000
MODEL = "gpt-oss-120b"
HEADERS = {"User-Agent": "DiemTin24H/1.2 (+GitHub Pages editorial bot)"}
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
STOPWORDS = {
    "và", "của", "với", "cho", "một", "các", "những", "được", "trong", "tháng", "năm", "tại",
    "từ", "sẽ", "là", "bị", "đã", "the", "and", "with", "phim", "bài", "người", "việt", "nam",
    "giảm", "tăng", "tiếp", "tục", "hoàn", "toàn", "gây", "nhờ", "câu", "chuyện", "dạy", "con",
}

# These are exact Commons files for people that frequently appear in Vietnamese entertainment news.
# The bot still checks the live license metadata before using any file.
PERSON_FILE_CANDIDATES = {
    "thu trang": [
        "File:THU TRANG - THE THIRD EYE.jpg",
        "File:ThuTrang1984.jpg",
        "File:THU TRANG 2020.jpg",
    ],
    "tiến luật": [
        "File:Tien Luat ATVNCG24.png",
        "File:Tien Luat.png",
    ],
}


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
    response = requests.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    paragraphs = []
    for selector in ["article.fck_detail p.Normal", ".fck_detail p.Normal", "p.Normal"]:
        paragraphs = []
        for p in soup.select(selector):
            text = clean(p.get_text(" "))
            if len(text) >= 35:
                paragraphs.append(text)
        if paragraphs:
            break

    if not paragraphs:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or script.get_text())
                objects = data if isinstance(data, list) else [data]
                for obj in objects:
                    body = obj.get("articleBody") if isinstance(obj, dict) else None
                    if body:
                        text = clean(body)
                        if len(text) >= 300:
                            paragraphs = [text]
                            break
            except Exception:
                continue
            if paragraphs:
                break
    return "\n\n".join(paragraphs)[:MAX_SOURCE_CHARS]


def _license_ok(meta):
    license_name = clean(meta.get("LicenseShortName", {}).get("value", ""))
    normalized = license_name.lower().replace("–", "-").strip()
    if normalized == "cc0" or normalized.startswith("public domain") or normalized in {"pd", "pd-us", "pd-old"}:
        return license_name
    if normalized.startswith("cc by-sa") or normalized.startswith("cc by ") or normalized == "cc by":
        if "nc" not in normalized and "nd" not in normalized:
            return license_name
    return ""


def _commons_file_lookup(titles):
    if not titles:
        return []
    params = {
        "action": "query",
        "format": "json",
        "titles": "|".join(titles),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 1200,
    }
    response = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=15)
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    results = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        license_name = _license_ok(meta)
        image_url = info.get("thumburl") or info.get("url")
        if not license_name or not image_url:
            continue
        title = clean(page.get("title", "")).replace("File:", "", 1).strip()
        results.append({
            "image": image_url,
            "image_source": "Wikimedia Commons",
            "image_license": license_name,
            "image_title": title,
            "image_page": "https://commons.wikimedia.org/wiki/" + page.get("title", "").replace(" ", "_") if page.get("title") else "",
        })
    return results


def _commons_search(query: str, wanted_tokens=None, limit=20):
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 1200,
    }
    response = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=15)
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    results = []
    wanted_tokens = set(wanted_tokens or [])
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        license_name = _license_ok(meta)
        if not license_name:
            continue
        title = clean(page.get("title", "")).replace("File:", "", 1).strip()
        haystack_words = set(x.lower() for x in _tokens(title))
        score = sum(1 for token in wanted_tokens if token.lower() in haystack_words)
        image_url = info.get("thumburl") or info.get("url")
        if image_url:
            results.append((score, {
                "image": image_url,
                "image_source": "Wikimedia Commons",
                "image_license": license_name,
                "image_title": title,
                "image_page": "https://commons.wikimedia.org/wiki/" + page.get("title", "").replace(" ", "_") if page.get("title") else "",
            }))
    results.sort(key=lambda x: x[0], reverse=True)
    return results


def _tokens(text):
    return [
        x for x in re.findall(r"[\wÀ-ỹà-ỹ]+", text or "", flags=re.UNICODE)
        if len(x) >= 3 and x.lower() not in STOPWORDS and not x.isdigit()
    ]


def find_openly_licensed_images(title: str, summary: str, category: str):
    """Use only clearly relevant Commons images with explicit reusable licenses.

    Important: one accidental substring match is never enough. If no relevant licensed
    image is found, return no image rather than filling the card with a random picture.
    """
    selected = []
    context = f"{title} {summary}".lower()

    # 1) Exact, known people first. This prevents fuzzy search from choosing an unrelated file.
    people = []
    if "thu trang" in context:
        people.append("thu trang")
    if "tiến luật" in context or "tien luat" in context:
        people.append("tiến luật")

    for person in people:
        try:
            results = _commons_file_lookup(PERSON_FILE_CANDIDATES[person])
            if results:
                selected.append(results[0])
        except Exception as exc:
            print(f"Commons exact person lookup failed for {person!r}: {exc}")

    # 2) Topic-specific query. Require real word matches in the file title.
    if not selected:
        tokens = _tokens(title)
        if "2g" in context:
            tokens.extend(["2g", "mobile", "phone"])
        if "iran" in context:
            tokens.extend(["iran", "flag"])
        if "peru" in context:
            tokens.extend(["peru", "flag"])
        if "mixue" in context:
            tokens.extend(["mixue", "ice", "cream"])
        # preserve order and remove duplicates
        tokens = list(dict.fromkeys(tokens))
        query = " ".join(tokens[:8]) or category
        try:
            results = _commons_search(query, tokens[:8])
            if results:
                best_score, best_image = results[0]
                # A unique brand/person token may be enough; generic 3-4 letter words are not.
                strong_single = any(len(token) >= 5 and token.lower() in _tokens(best_image["image_title"]) for token in tokens)
                if best_score >= 2 or strong_single:
                    selected.append(best_image)
        except Exception as exc:
            print(f"Commons topical image search failed for {title!r}: {exc}")

    dedup = []
    seen = set()
    for image in selected:
        if image["image"] not in seen:
            seen.add(image["image"])
            dedup.append(image)
    return dedup[:2]


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+[\wÀ-ỹà-ỹ'-]*\b", text or "", flags=re.UNICODE))


def _parse_ai_json(raw: str, fallback_title: str):
    raw = (raw or "").strip()
    try:
        data = json.loads(raw)
        return clean(data.get("title", fallback_title)) or fallback_title, str(data.get("content", "")).strip()
    except Exception:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                return clean(data.get("title", fallback_title)) or fallback_title, str(data.get("content", "")).strip()
            except Exception:
                pass
        return fallback_title, raw


def ai_article(source_text: str, title: str, category: str) -> tuple[str, str]:
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key or len(source_text) < 500:
        return "", title

    client = OpenAI(base_url="https://api.cerebras.ai/v1", api_key=api_key)
    prompt = (
        "Bạn là biên tập viên của ĐIỂM TIN 24H. Dựa trên các dữ kiện trong tài liệu nguồn, "
        "hãy viết một bài báo tiếng Việt DÀI, NGUYÊN BẢN và có chiều sâu. Mục tiêu 900-1200 từ, "
        "tối thiểu 750 từ. Không được biến thành một đoạn tóm tắt ngắn. Khai thác đầy đủ diễn biến, "
        "nhân vật, số liệu, bối cảnh, nguyên nhân, hệ quả hoặc tác động khi tài liệu thực sự cung cấp. "
        "Chia bài thành nhiều đoạn, có mở bài, phần triển khai và kết bài tự nhiên. Không bịa thêm dữ kiện, "
        "phát ngôn, con số hoặc sự kiện. Không chép nguyên câu, không tái tạo cấu trúc hay cách diễn đạt của "
        "bài nguồn. Đây là bài biên tập độc lập dựa trên các sự kiện. Trả về JSON với title và content; "
        "content là văn bản thuần, các đoạn cách nhau bằng một dòng trống.\n\n"
        f"Chuyên mục: {category}\nTiêu đề tham khảo: {title}\n\n"
        f"Tài liệu dữ kiện nguồn:\n{source_text}"
    )
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.3,
        max_completion_tokens=5000,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "Tạo bài báo nguyên bản, dài, chính xác theo dữ kiện; không sao chép văn bản nguồn."},
            {"role": "user", "content": prompt},
        ],
    )
    new_title, content = _parse_ai_json(response.choices[0].message.content or "", title)

    if word_count(content) < 750:
        expand_prompt = (
            "Mở rộng bản thảo dưới đây thành bài báo tiếng Việt khoảng 900-1200 từ. Giữ nguyên mọi dữ kiện đã có; "
            "phát triển bối cảnh, giải thích và mạch kể chỉ khi chúng đã được hỗ trợ bởi bản thảo; không bịa thêm, "
            "không lặp ý và không sao chép nguồn. Trả về văn bản thuần với nhiều đoạn.\n\n"
            f"Bản thảo cần mở rộng:\n{content}"
        )
        expanded = client.chat.completions.create(
            model=MODEL,
            temperature=0.3,
            max_completion_tokens=5000,
            messages=[
                {"role": "system", "content": "Mở rộng bài báo nguyên bản, không thêm dữ kiện không được hỗ trợ."},
                {"role": "user", "content": expand_prompt},
            ],
        )
        expanded_text = (expanded.choices[0].message.content or "").strip()
        if word_count(expanded_text) > word_count(content):
            content = expanded_text

    print(f"AI article: {title!r} -> {word_count(content)} words")
    return content, new_title


def main():
    # Keep one item per URL even when the same newest story appears in multiple RSS feeds.
    by_url = {}
    for category, feed_url in SOURCES.items():
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            title = clean(entry.get("title"))
            url = entry.get("link", "")
            if title and url and url not in by_url:
                by_url[url] = {
                    "id": post_id(url),
                    "title": title,
                    "url": url,
                    "summary": clean(entry.get("summary", ""))[:500],
                    "category": category,
                    "source": "VnExpress",
                    "published_at": date_of(entry),
                }

    candidates = list(by_url.values())
    candidates.sort(key=lambda item: item["published_at"], reverse=True)
    posts = []
    for item in candidates[:MAX_POSTS]:
        try:
            source_text = fetch_article_text(item["url"])
            print(f"Source length for {item['title']!r}: {len(source_text)} chars")
            if len(source_text) < 500:
                # Do not ask the AI to invent a 750-word article from a tiny RSS summary.
                item["content"] = ""
                item["summary_type"] = "source_excerpt"
            else:
                content, new_title = ai_article(source_text, item["title"], item["category"])
                if content:
                    item["title"] = new_title
                    item["content"] = content
                    item["summary"] = content.split("\n\n", 1)[0][:360]
                    item["summary_type"] = "cerebras_ai_original_article"
                else:
                    item["content"] = ""
                    item["summary_type"] = "source_excerpt"
            images = find_openly_licensed_images(item["title"], item["summary"], item["category"])
            item["images"] = images
            item.update(images[0] if images else {"image": "", "image_source": "", "image_license": "", "image_title": "", "image_page": ""})
        except Exception as exc:
            print(f"Article processing failed for {item['url']}: {exc}")
            item["content"] = ""
            item["summary_type"] = "source_excerpt"
            images = find_openly_licensed_images(item["title"], item["summary"], item["category"])
            item["images"] = images
            item.update(images[0] if images else {"image": "", "image_source": "", "image_license": "", "image_title": "", "image_page": ""})
        posts.append(item)

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": posts,
        "policy": {
            "max_posts_per_run": MAX_POSTS,
            "full_source_text_stored": False,
            "source_images_stored": False,
            "source_attribution": True,
            "ai_mode": "original_detailed_article",
            "target_article_words": "900-1200",
            "minimum_article_words": 750,
            "ai_provider": "Cerebras",
            "ai_model": MODEL,
            "image_provider": "Wikimedia Commons",
            "image_policy": "only clearly relevant CC BY/CC BY-SA/CC0/public-domain files; no random fallback image",
        },
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Prepared {len(posts)} posts")


if __name__ == "__main__":
    main()
