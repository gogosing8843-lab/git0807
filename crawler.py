from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
OUTPUT = Path("output/latest_news.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
}

# 부산시정/정책 기사 선별용 키워드.
# 필요하면 아래 목록만 수정하면 됩니다.
POLICY_KEYWORDS = [
    "부산시", "부산광역시", "시정", "정책", "사업", "지원", "예산",
    "복지", "교통", "도시철도", "가덕도", "신공항", "북항",
    "재개발", "재건축", "해양", "항만", "경제", "산업", "일자리",
    "청년", "관광", "문화", "교육", "안전", "환경", "주거",
    "구청", "군청", "시의회", "부산", "전재수",
]

EXCLUDE_WORDS = [
    "사설", "오피니언", "칼럼", "기고", "독자", "만평",
    "오늘의 운세", "연예", "스포츠", "프로야구", "롯데 자이언츠",
]

SOURCE_PAGES = {
    "부산일보": "https://www.busan.com/all/",
    "국제신문": "https://www.kookje.co.kr/mobile/news.htm?code=00&gbn=l",
}

session = requests.Session()
session.headers.update(HEADERS)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def soup_get(url: str) -> BeautifulSoup:
    r = session.get(url, timeout=25)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    return BeautifulSoup(r.text, "html.parser")


def collect_listing_links(source: str, listing_url: str, limit: int = 60) -> list[str]:
    soup = soup_get(listing_url)
    found: list[str] = []

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue
        full = urljoin(listing_url, href)

        if source == "부산일보":
            if "busan.com/view/" not in full or "code=" not in full:
                continue
        else:
            if "kookje.co.kr" not in full:
                continue
            if "newsbody.asp" not in full:
                continue

        full = full.split("#")[0]
        if full not in found:
            found.append(full)
        if len(found) >= limit:
            break

    return found


def parse_jsonld(soup: BeautifulSoup) -> list[dict]:
    objs = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, dict):
            objs.append(data)
        elif isinstance(data, list):
            objs.extend(x for x in data if isinstance(x, dict))
    return objs


def extract_published_at(soup: BeautifulSoup, url: str) -> datetime | None:
    candidates = []

    for attrs in (
        {"property": "article:published_time"},
        {"name": "article:published_time"},
        {"name": "date"},
        {"itemprop": "datePublished"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            candidates.append(tag["content"])

    for obj in parse_jsonld(soup):
        for key in ("datePublished", "dateCreated", "uploadDate"):
            if obj.get(key):
                candidates.append(str(obj[key]))

    # URL fallback: Busan code=YYYYMMDD..., Kookje key=YYYYMMDD...
    m = re.search(r"(?:code|key)=(20\d{6})", url)
    if m:
        candidates.append(m.group(1))

    for value in candidates:
        try:
            if re.fullmatch(r"20\d{6}", value):
                dt = datetime.strptime(value, "%Y%m%d").replace(tzinfo=KST)
            else:
                dt = dtparser.parse(value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=KST)
                else:
                    dt = dt.astimezone(KST)
            return dt
        except Exception:
            pass
    return None


def extract_title(soup: BeautifulSoup) -> str:
    for selector in (
        'meta[property="og:title"]',
        'meta[name="twitter:title"]',
    ):
        tag = soup.select_one(selector)
        if tag and tag.get("content"):
            return clean_text(tag["content"])

    if soup.title:
        return clean_text(soup.title.get_text())
    return ""


def extract_summary(soup: BeautifulSoup) -> str:
    for selector in (
        'meta[property="og:description"]',
        'meta[name="description"]',
        'meta[name="twitter:description"]',
    ):
        tag = soup.select_one(selector)
        if tag and tag.get("content"):
            summary = clean_text(tag["content"])
            if summary:
                return summary[:650]

    # Fallback: 기사 본문에서 긴 문단 몇 개 결합
    paragraphs = []
    for p in soup.find_all("p"):
        txt = clean_text(p.get_text(" ", strip=True))
        if len(txt) >= 40:
            paragraphs.append(txt)
        if sum(map(len, paragraphs)) > 500:
            break
    return clean_text(" ".join(paragraphs))[:650]


def choose_keyword(title: str, summary: str) -> str:
    text = f"{title} {summary}"
    for kw in POLICY_KEYWORDS:
        if kw in text:
            return "부산시" if kw in ("부산광역시", "부산시") else kw
    return "부산"


def relevant_policy_article(title: str, summary: str) -> bool:
    text = f"{title} {summary}"
    if any(word in text for word in EXCLUDE_WORDS):
        return False
    return any(word in text for word in POLICY_KEYWORDS)


def fetch_article(source: str, url: str) -> dict | None:
    try:
        soup = soup_get(url)
        title = extract_title(soup)
        summary = extract_summary(soup)
        published = extract_published_at(soup, url)

        if not title or not published:
            return None
        if not relevant_policy_article(title, summary):
            return None

        return {
            "title": title,
            "url": url,
            "summary": summary,
            "keyword": choose_keyword(title, summary),
            "source": source,
            "published_at": published.strftime("%Y-%m-%d %H:%M:%S"),
            "_published": published,
        }
    except Exception as exc:
        print(f"[WARN] {source} article failed: {url} :: {exc}")
        return None


def dedupe(items: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for item in items:
        key = item["url"]
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def main():
    now = datetime.now(KST)
    collected: list[dict] = []

    for source, listing_url in SOURCE_PAGES.items():
        print(f"[INFO] collecting {source}: {listing_url}")
        try:
            links = collect_listing_links(source, listing_url)
        except Exception as exc:
            print(f"[ERROR] listing failed for {source}: {exc}")
            continue

        print(f"[INFO] {source}: {len(links)} candidate links")
        for idx, url in enumerate(links, 1):
            item = fetch_article(source, url)
            if item:
                collected.append(item)
            # 사이트에 무리가 가지 않도록 아주 짧게 간격을 둡니다.
            time.sleep(0.15)

    collected = dedupe(collected)

    if not collected:
        raise SystemExit(
            "수집된 정책 기사가 없습니다. 언론사 HTML 구조 변경 여부를 확인하세요."
        )

    # '최신 날짜 기사' 요구: 수집 결과 중 가장 최근 발행일(날짜)의 기사만 저장.
    latest_date = max(item["_published"].date() for item in collected)
    latest = [
        item for item in collected
        if item["_published"].date() == latest_date
    ]
    latest.sort(key=lambda x: x["_published"], reverse=True)

    # 내부 비교용 필드는 JSON에서 제거
    for item in latest:
        item.pop("_published", None)

    payload = {
        "articles": latest,
        "article_date": latest_date.isoformat(),
        "last_updated": now.strftime("%Y-%m-%d %H:%M:%S KST"),
        "sources": ["부산일보", "국제신문"],
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[DONE] {len(latest)} articles saved for {latest_date} -> {OUTPUT}")


if __name__ == "__main__":
    main()
