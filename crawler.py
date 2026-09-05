# VERIFIED_V3_20260905 - 정책현안 우선 / 부산일보 보강 / 문두잡음 제거
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
HWPX_OUTPUT = Path("output/latest_news.hwpx")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
}

POLICY_KEYWORDS = [
    "부산시", "부산광역시", "시정", "정책", "사업", "지원", "예산",
    "복지", "교통", "도시철도", "가덕도", "신공항", "북항",
    "재개발", "재건축", "정비사업", "해양", "항만", "경제", "산업",
    "일자리", "청년", "관광", "문화", "교육", "안전", "환경", "주거",
    "구청", "군청", "시의회", "부산", "시장", "국회", "정부",
    "특별법", "국정과제", "원전", "병원", "재난", "침수",
]

EXCLUDE_WORDS = [
    "사설", "오피니언", "칼럼", "기고", "독자", "만평",
    "오늘의 운세", "연예", "스포츠", "프로야구", "롯데 자이언츠",
]

# 시정 보고서에 넣기에는 가치가 낮은 단순 생활정보 기사
LOW_VALUE_TITLE_PATTERNS = [
    r"대체로\s*맑", r"낮\s*최고\s*\d", r"아침\s*최저\s*\d",
    r"오늘\s*날씨", r"내일\s*날씨", r"미세먼지.*좋음",
]

SOURCE_PAGES = {
    "부산일보": "https://www.busan.com/all/",
    "국제신문": "https://www.kookje.co.kr/mobile/news.htm?code=00&gbn=l",
}

# 담당부서는 올려주신 '일일 언론보도' 양식의 표현을 우선 반영했습니다.
DEPARTMENT_RULES = [
    ("시민안전실", ["재난", "안전", "중대재해", "싱크홀", "침수", "지진",
                   "산사태", "방사능", "원전", "고리", "소방", "붕괴"]),
    ("도시혁신균형실", ["사상-하단", "사상~하단", "도시철도", "정비사업",
                        "재개발", "재건축", "도시재생", "균형발전"]),
    ("해양농수산국", ["해양", "항만", "북극항로", "해수부", "수산", "어업",
                      "예인선", "선박", "오륙도", "해경"]),
    ("신공항추진본부", ["가덕도", "신공항"]),
    ("디지털경제실", ["AI", "인공지능", "경제", "산업", "기업", "수출",
                      "생산", "투자", "고용", "제조업", "스타트업",
                      "주유소", "석유", "혼유", "에너지"]),
    ("청년산학국", ["청년", "대학", "산학", "창업재단"]),
    ("관광마이스국", ["관광", "마이스", "MICE", "해양레저", "축제", "관광단지"]),
    ("교통혁신국", ["버스", "이륜차", "교통", "택시", "도로", "주차"]),
    ("시민건강국", ["병원", "보건", "의료", "건강", "감염병"]),
    ("사회복지국", ["복지", "장애인", "노인", "돌봄", "저소득", "응급안전안심"]),
    ("행정자치국", ["마을지기", "자치", "주민", "행정", "구청", "군청"]),
    ("문화체육국", ["문화", "공연", "예술", "체육", "아트센터"]),
    ("주택건축국", ["주택", "아파트", "전월세", "건축", "주거"]),
]

SECTION_RULES = {
    "정치": [
        "대통령", "국회", "국회의원", "정부", "정당", "특별법",
        "국정과제", "장관", "총선", "지방선거", "공약",
    ],
    "경제": [
        "경제", "산업", "기업", "수출", "생산", "투자", "고용",
        "일자리", "스타트업", "제조업", "관광", "마이스", "MICE",
        "전월세", "아파트", "부동산", "상권", "금융",
    ],
    "시청·시의회": [
        "부산시", "부산광역시", "시의회", "시장", "의장", "조례",
        "공공계약", "시정", "시청", "예산", "공무원",
    ],
}

MAJOR_ISSUE_WORDS = [
    "부산시", "시의회", "시장", "정부", "국회", "특별법", "국정과제",
    "가덕도", "신공항", "북항", "해수부", "북극항로", "원전", "고리",
    "재난", "중대재해", "싱크홀", "침수", "사고", "실종", "붕괴",
    "예산", "착공", "개통", "폐지", "확정", "발의", "투자", "수출",
]

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


def collect_listing_links(source: str, listing_url: str, limit: int = 80) -> list[str]:
    # 부산일보 /all/이 동적 페이지일 때를 대비해 지면보기 페이지도 함께 탐색
    listing_pages = [listing_url]
    if source == "부산일보":
        listing_pages.extend([
            "https://www.busan.com/newspaper/",
            "https://www.busan.com/all",
        ])

    found: list[str] = []

    for page_url in listing_pages:
        try:
            soup = soup_get(page_url)
        except Exception as exc:
            print(f"[WARN] listing fetch failed: {source} {page_url} -> {exc}")
            continue

        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href:
                continue

            full = urljoin(page_url, href).split("#")[0]

            if source == "부산일보":
                if "busan.com" not in full:
                    continue

                # 부산일보 실제 기사 URL 형태를 넓게 허용하되
                # 가이드/회원/생활정보 같은 비기사 페이지는 제외
                if any(x in full for x in [
                    "/guide/", "/faq/", "/member/", "/login", "/mypage/",
                    "lifeplus.busan.com", "/html/board/"
                ]):
                    continue

                if not any(token in full for token in [
                    "/view/", "/article/", "/news/", "newsController.do",
                    "code=", "idxno=", "articleNo="
                ]):
                    continue
            else:
                if "kookje.co.kr" not in full or "newsbody.asp" not in full:
                    continue

            if full not in found:
                found.append(full)

            if len(found) >= limit:
                break

        if len(found) >= limit:
            break

    print(f"[INFO] {source}: {len(found)} candidate links")
    return found



def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def parse_jsonld(soup: BeautifulSoup) -> list[dict]:
    objs: list[dict] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        objs.extend(x for x in _walk_json(data) if isinstance(x, dict))
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


def _clean_article_text(text: str) -> str:
    if not text:
        return ""

    noise_patterns = [
        r"\[[^\]]*(?:사진|포토|자료|그래픽)[^\]]*\]",
        r"\([^\)]*(?:사진|자료|제공)[^\)]*\)",
        r"[가-힣]{2,4}\s*기자\s*[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        r"무단전재[^.。!?]*",
        r"재배포[^.。!?]*",
        r"Copyright[^.。!?]*",
        r"저작권자[^.。!?]*",
        r"좋아요\s*\d*",
        r"공유하기",
        r"기사\s*스크랩",
    ]
    for pat in noise_patterns:
        text = re.sub(pat, " ", text, flags=re.I)

    return clean_text(text)


def _candidate_text(node) -> str:
    # 스크립트·스타일·광고성 요소는 제거한 복제본 대신,
    # 텍스트 블록을 개별 추출해 중복을 줄입니다.
    blocks = []
    for child in node.find_all(["p", "div"], recursive=True):
        if child.find_parent(["script", "style", "nav", "footer", "header"]):
            continue
        text = clean_text(child.get_text(" ", strip=True))
        if 25 <= len(text) <= 1800:
            blocks.append(text)

    # p/div가 거의 없는 기사도 있으므로 전체 텍스트 fallback
    if not blocks:
        whole = clean_text(node.get_text(" ", strip=True))
        if len(whole) >= 120:
            blocks = [whole]

    seen = set()
    unique = []
    for block in blocks:
        key = re.sub(r"\s+", "", block)
        if not key or key in seen:
            continue
        # 큰 부모 div가 작은 자식 문장을 통째로 포함하는 경우 중복 방지
        if any(key == old or key in old for old in seen):
            continue
        seen.add(key)
        unique.append(block)

    return _clean_article_text(" ".join(unique))


def _extract_article_body(soup: BeautifulSoup, source: str) -> str:
    """메타 설명이 아니라 실제 기사 본문을 우선 추출합니다."""

    # 1. JSON-LD articleBody
    for obj in parse_jsonld(soup):
        body = obj.get("articleBody")
        if isinstance(body, str):
            body = _clean_article_text(body)
            if len(body) >= 180 and not body.endswith(".."):
                return _strip_leading_caption_and_wire(body)

    # 2. 부산일보/국제신문 및 일반 뉴스 사이트에서 자주 쓰는 본문 선택자
    selectors = [
        "#news_text", ".news_text", "#articleBody", "#article-body",
        "#article_body", "#articleBodyContents", "#newsBody", "#news-body",
        ".article-body", ".article_body", ".articleBody", ".article_view",
        ".article-view", ".article_content", ".article-content", ".article_txt",
        ".article-text", ".news-body", ".news_body", ".news_article",
        ".news-article", ".view_cont", ".view-content", ".view_content",
        ".view_news", ".news_view", "article",
    ]

    candidates: list[tuple[int, str]] = []
    for selector in selectors:
        for node in soup.select(selector):
            body = _candidate_text(node)
            if len(body) < 160:
                continue
            links_text = clean_text(" ".join(a.get_text(" ", strip=True) for a in node.find_all("a")))
            link_ratio = len(links_text) / max(len(body), 1)
            if link_ratio > 0.35:
                continue
            score = len(body) - int(link_ratio * 3000)
            candidates.append((score, body))

    # 3. class/id 이름에 article/content/body/news/view/text가 들어간 div를 탐색
    name_re = re.compile(r"(article|content|body|news|view|text|cont)", re.I)
    for node in soup.find_all(["div", "section"], limit=500):
        attrs = " ".join([
            str(node.get("id", "")),
            " ".join(node.get("class", []) if isinstance(node.get("class"), list) else [str(node.get("class", ""))]),
        ])
        if not name_re.search(attrs):
            continue
        body = _candidate_text(node)
        if not (180 <= len(body) <= 25000):
            continue
        links_text = clean_text(" ".join(a.get_text(" ", strip=True) for a in node.find_all("a")))
        link_ratio = len(links_text) / max(len(body), 1)
        if link_ratio <= 0.20:
            candidates.append((len(body) - int(link_ratio * 2500), body))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best = candidates[0][1]
        if len(best) >= 180:
            return _strip_leading_caption_and_wire(best)

    # 4. 마지막 fallback: 긴 p 태그들
    paras = []
    for p in soup.find_all("p"):
        text = _clean_article_text(p.get_text(" ", strip=True))
        if 35 <= len(text) <= 1500:
            paras.append(text)
    body = clean_text(" ".join(paras))
    if len(body) >= 180:
        return _strip_leading_caption_and_wire(body)

    return ""


def _strip_leading_caption_and_wire(text: str) -> str:
    """기사 맨 앞의 통신사명·사진/DB 캡션을 보고서 문장에서 제거합니다."""
    text = clean_text(text)
    if not text:
        return ""

    # '연합뉴스 부산의...', '국제신문DB 소방시설...'처럼 문장부호 없이 붙는 경우
    leading_noise = [
        r"^(?:연합뉴스|뉴시스|뉴스1)\s*",
        r"^(?:국제신문\s*DB|국제신문DB|부산일보\s*DB|부산일보DB)\s*",
        r"^(?:사진|자료사진)\s*(?:=|:)?\s*",
    ]
    changed = True
    while changed:
        before = text
        for pat in leading_noise:
            text = re.sub(pat, "", text, flags=re.I)
        text = clean_text(text)
        changed = (text != before)

    sentences = re.split(r'(?<=[.!?。！？])\s+', text)
    cleaned = []

    for i, sentence in enumerate(sentences):
        sentence = clean_text(sentence)
        if not sentence:
            continue

        # 앞 2문장 안의 전형적인 사진 캡션 제거
        caption_like = (
            "자료사진" in sentence
            or "국제신문DB" in sentence
            or "부산일보DB" in sentence
            or re.search(r"(?:해경|부산시|경찰|소방|구청)\s*제공", sentence)
            or ("사진" in sentence and any(x in sentence for x in ["촬영", "모습", "제공"]))
        )
        if i <= 1 and caption_like:
            continue

        sentence = re.sub(r"^(?:연합뉴스|뉴시스|뉴스1)\s+", "", sentence)
        sentence = re.sub(r"^(?:국제신문\s*DB|국제신문DB|부산일보\s*DB|부산일보DB)\s*", "", sentence)
        sentence = clean_text(sentence)

        if sentence:
            cleaned.append(sentence)

    return clean_text(" ".join(cleaned))



def _split_korean_sentences(text: str) -> list[str]:
    text = _clean_article_text(text)
    if not text:
        return []

    # 마침표 뒤 공백이 없는 모바일 기사도 처리
    text = re.sub(r"([.!?。！？])(?=[가-힣A-Za-z0-9“\"'])", r"\1 ", text)
    parts = re.split(r'(?<=[.!?。！？])\s+', text)

    sentences = []
    seen = set()
    for sentence in parts:
        sentence = clean_text(sentence).strip(" -·•")
        if len(sentence) < 18:
            continue
        # '기사 더보기', 메뉴 등 제거
        if any(x in sentence for x in ["기자명", "입력 :", "수정 :", "관련기사", "추천기사"]):
            continue
        key = re.sub(r"\s+", "", sentence)
        if key in seen:
            continue
        seen.add(key)
        sentences.append(sentence)
    return sentences


def _score_sentence(sentence: str, index: int, title: str) -> float:
    score = max(0.0, 5.0 - index * 0.35)
    title_terms = re.findall(r"[가-힣A-Za-z0-9]{2,}", title)
    score += sum(1.2 for term in title_terms if term in sentence)
    score += sum(0.35 for kw in POLICY_KEYWORDS if kw in sentence)
    if re.search(r"\d", sentence):
        score += 0.6
    if any(word in sentence for word in ["계획", "예정", "추진", "확정", "발표", "지원", "투입", "발의"]):
        score += 0.8
    if 45 <= len(sentence) <= 190:
        score += 0.8
    if len(sentence) > 300:
        score -= 1.0
    return score


def make_summary(body: str, title: str, max_sentences: int = 2, max_chars: int = 360) -> str:
    """홈페이지/일반 목록용 1~2문장 요약."""
    sentences = _split_korean_sentences(body)
    if not sentences:
        return ""

    scored = [(_score_sentence(s, i, title), i, s) for i, s in enumerate(sentences[:20])]
    selected = sorted(scored, reverse=True)[:max_sentences + 2]
    selected = sorted(selected, key=lambda x: x[1])

    result = []
    total = 0
    for _, _, sentence in selected:
        if len(result) >= max_sentences:
            break
        if total + len(sentence) > max_chars and result:
            continue
        if sentence[-1] not in ".!?。！？":
            sentence += "."
        result.append(sentence)
        total += len(sentence) + 1

    return " ".join(result) if result else sentences[0]


def make_report_summary(body: str, title: str) -> str:
    """첫 장 주요현안용: 핵심 진행상황·수치·향후계획을 3~4문장으로."""
    sentences = _split_korean_sentences(body)
    if not sentences:
        return ""

    scored = [(_score_sentence(s, i, title), i, s) for i, s in enumerate(sentences[:24])]

    # 첫 문장은 기사 리드를 우선 확보
    chosen_indices = set()
    if sentences:
        chosen_indices.add(0)

    # 수치/현재 상황/향후 계획 문장을 우선 보강
    for _, i, s in sorted(scored, reverse=True):
        if len(chosen_indices) >= 4:
            break
        if i in chosen_indices:
            continue
        chosen_indices.add(i)

    chosen = [sentences[i] for i in sorted(chosen_indices)][:4]

    # 지나치게 긴 문서는 3~4문장, 500자 안팎에서 완결
    result = []
    total = 0
    for sentence in chosen:
        if sentence[-1] not in ".!?。！？":
            sentence += "."
        if total + len(sentence) > 560 and len(result) >= 3:
            break
        result.append(sentence)
        total += len(sentence) + 1

    return " ".join(result)


def extract_body_and_summaries(soup: BeautifulSoup, source: str, title: str) -> tuple[str, str, str]:
    body = _extract_article_body(soup, source)

    if body:
        summary = make_summary(body, title)
        report_summary = make_report_summary(body, title)
        return body, summary, report_summary

    # 실제 본문을 못 찾았을 때만 meta description을 사용
    for selector in (
        'meta[property="og:description"]',
        'meta[name="description"]',
        'meta[name="twitter:description"]',
    ):
        tag = soup.select_one(selector)
        if not tag or not tag.get("content"):
            continue
        raw = _strip_leading_caption_and_wire(_clean_article_text(tag["content"]))
        # '...' 또는 '..'로 잘린 설명은 그대로 보고서에 넣지 않습니다.
        if len(raw) < 80 or raw.endswith("..") or raw.endswith("..."):
            continue
        sentences = _split_korean_sentences(raw)
        summary = " ".join(sentences[:2]) if sentences else raw
        report_summary = " ".join(sentences[:4]) if sentences else raw
        return raw, summary, report_summary

    return "", "", ""


def choose_keyword(title: str, summary: str) -> str:
    text = f"{title} {summary}"

    issue_rules = [
        ("예인선 침몰", ["예인선", "침몰"]),
        ("예인선 전복", ["예인선", "전복"]),
        ("혼유 사고", ["혼유"]),
        ("가덕도신공항", ["가덕도", "신공항"]),
        ("북극항로", ["북극항로"]),
        ("해양수도 특별법", ["해양수도", "특별법"]),
        ("고리 1호기", ["고리 1호기"]),
        ("중대재해", ["중대재해"]),
        ("사상-하단선", ["사상", "하단"]),
        ("싱크홀", ["싱크홀"]),
        ("도시안전 통합시스템", ["도시안전", "통합시스템"]),
        ("정비사업", ["정비사업"]),
        ("청년창업재단", ["청년창업재단"]),
        ("침례병원", ["침례병원"]),
        ("마을지기사무소", ["마을지기사무소"]),
        ("해양레저위크", ["해양레저"]),
        ("낙동아트센터", ["낙동아트센터"]),
        ("전월세", ["전월세"]),
        ("스타트업", ["스타트업"]),
    ]

    for label, words in issue_rules:
        if all(word in text for word in words):
            return label

    title_terms = re.findall(r"[가-힣A-Za-z0-9·~-]{2,}", title)
    stop = {"부산", "부산시", "국제신문", "부산일보", "오늘", "관련", "대한", "정부"}
    for term in title_terms:
        if term not in stop and not re.fullmatch(r"\d+", term):
            return term[:18]

    return "부산시"

def choose_department(title: str, summary: str) -> str:
    text = f"{title} {summary}"
    for department, words in DEPARTMENT_RULES:
        if any(word in text for word in words):
            return department
    return "관련부서"


def choose_section(title: str, summary: str) -> str:
    text = f"{title} {summary}"

    social_priority = [
        "사고", "침몰", "전복", "실종", "수색", "싱크홀", "붕괴",
        "화재", "혼유", "교통사고", "범죄", "경찰", "해경",
    ]
    if any(word in text for word in social_priority):
        return "사회 일반"

    if any(word in text for word in SECTION_RULES["정치"]):
        return "정치"

    if any(word in text for word in SECTION_RULES["시청·시의회"]):
        return "시청·시의회"

    if any(word in text for word in SECTION_RULES["경제"]):
        return "경제"

    return "사회 일반"

def importance_score(item: dict) -> int:
    text = f"{item.get('title', '')} {item.get('summary', '')} {item.get('report_summary', '')}"
    title = item.get("title", "")
    score = 0

    # 부산시정과 직접 연결된 현안
    if "부산시" in text or "부산광역시" in text:
        score += 14
    if any(x in text for x in ["시의회", "시장", "시청", "조례", "예산"]):
        score += 9
    if any(x in text for x in ["정부", "국회", "특별법", "국정과제"]):
        score += 8

    # 대형 정책·개발·교통·산업 현안
    if any(x in text for x in [
        "가덕도", "신공항", "북항", "해수부", "북극항로",
        "도시철도", "사상-하단", "재개발", "재건축", "정비사업",
        "산업", "기업", "투자", "수출", "일자리", "주거", "복지",
    ]):
        score += 8

    # 시민 안전상 파급이 큰 사건은 주요 현안으로 인정
    if any(x in text for x in [
        "대형사고", "침몰", "전복", "실종", "재난",
        "중대재해", "싱크홀", "붕괴", "침수",
    ]):
        score += 7

    if re.search(r"\d+\s*(억|조|명|건|%|km|m|대|척|가구)", text):
        score += 3
    if any(x in text for x in [
        "확정", "발의", "착공", "개통", "추진", "투입",
        "지원", "협약", "유치", "선정", "계획",
    ]):
        score += 4

    # 일반적인 법원·형사 단신은 첫 장 TOP3에서 후순위
    if any(x in title for x in [
        "벌금형", "징역", "기소", "재판", "자격증 빌려",
        "음주운전", "절도", "폭행",
    ]):
        score -= 14

    # 단순 날씨/생활정보는 크게 감점
    if any(re.search(pat, title) for pat in LOW_VALUE_TITLE_PATTERNS):
        score -= 25

    return score



def relevant_policy_article(title: str, summary: str) -> bool:
    text = f"{title} {summary}"
    if any(word in text for word in EXCLUDE_WORDS):
        return False

    # 단순 기상 기사는 제거하되, 부산시 재난대응·폭염대책 등 정책기사는 유지
    if any(re.search(pat, title) for pat in LOW_VALUE_TITLE_PATTERNS):
        if "부산시" not in text and "대책" not in text and "재난" not in text:
            return False

    return any(word in text for word in POLICY_KEYWORDS)


def fetch_article(source: str, url: str) -> dict | None:
    try:
        soup = soup_get(url)
        title = extract_title(soup)
        published = extract_published_at(soup, url)

        if not title or not published:
            return None

        body, summary, report_summary = extract_body_and_summaries(soup, source, title)

        # 본문이 비었더라도 제목 자체가 시정 기사인지 확인할 수 있으나,
        # 보고서 품질을 위해 요약을 만들 수 없는 기사는 제외합니다.
        if not summary:
            print(f"[WARN] body/summary missing: {source} :: {title}")
            return None

        if not relevant_policy_article(title, summary):
            return None

        item = {
            "title": title,
            "url": url,
            "summary": summary,
            "report_summary": report_summary or summary,
            "keyword": choose_keyword(title, summary),
            "department": choose_department(title, summary),
            "section": choose_section(title, summary),
            "source": source,
            "published_at": published.strftime("%Y-%m-%d %H:%M:%S"),
            "_published": published,
        }
        item["importance"] = importance_score(item)
        return item

    except Exception as exc:
        print(f"[WARN] {source} article failed: {url} :: {exc}")
        return None


def dedupe(items: list[dict]) -> list[dict]:
    seen_urls = set()
    seen_titles = set()
    result = []

    for item in items:
        title_key = re.sub(r"[^가-힣A-Za-z0-9]", "", item["title"])
        if item["url"] in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(item["url"])
        seen_titles.add(title_key)
        result.append(item)

    return result


def source_short(source: str) -> str:
    return "부산" if source == "부산일보" else "국제" if source == "국제신문" else source


def _add_para(doc, text: str = "", **kwargs):
    """python-hwpx 버전 차이를 고려한 안전한 문단 추가."""
    try:
        return doc.add_paragraph(text, **kwargs)
    except TypeError:
        return doc.add_paragraph(text)


def create_hwpx(articles: list[dict], article_date, updated_at: datetime) -> None:
    from hwpx import HwpxDocument

    HWPX_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = HwpxDocument.new()

    try:
        # ─────────────────────────────────────────────
        # 첫째 장: 중요도 상위 3건
        # ─────────────────────────────────────────────
        _add_para(doc, "일일 언론 보도사항")
        _add_para(doc, f"{article_date.isoformat()}  |  수집 {updated_at.strftime('%H:%M')} KST")
        _add_para(doc, "")

        ranked = sorted(
            articles,
            key=lambda x: (x.get("importance", 0), x.get("published_at", "")),
            reverse=True,
        )

        # 기본은 중요도 순. 부산일보·국제신문이 모두 있으면 한 신문에만
        # 치우치지 않도록 상위권에서 출처 다양성을 확보합니다.
        top_issues = []
        for item in ranked:
            if len(top_issues) >= 3:
                break
            if item not in top_issues:
                top_issues.append(item)

        if len({x.get("source") for x in top_issues}) == 1:
            other = next(
                (x for x in ranked[3:] if x.get("source") != top_issues[0].get("source")),
                None,
            )
            if other and other.get("importance", 0) >= top_issues[-1].get("importance", 0) - 3:
                top_issues[-1] = other

        top_urls = {item["url"] for item in top_issues}

        for item in top_issues:
            dept = item.get("department", "관련부서")
            keyword = item.get("keyword", "부산시")
            _add_para(doc, f"ㅇ ({keyword} ‣{dept}) {item.get('report_summary', item.get('summary', ''))}")
            _add_para(
                doc,
                f"   - <{source_short(item.get('source', ''))}> "
                f"{item.get('title', '')}  [▸기사] {item.get('url', '')}",
            )
            _add_para(doc, "")

        # 둘째 장부터 '1 주요 현안' 시작.
        # python-hwpx는 pageBreak 속성을 지원하며, 구버전 대비 fallback도 둡니다.
        try:
            doc.add_paragraph("", pageBreak="1", inherit_style=False)
        except TypeError:
            # pageBreak 옵션이 없는 환경에서는 새 섹션으로 다음 내용을 분리
            try:
                new_section = doc.add_section()
                new_section.add_paragraph("1  주요 현안")
                wrote_main_heading = True
            except Exception:
                _add_para(doc, "")
                wrote_main_heading = False
        else:
            wrote_main_heading = False

        if not wrote_main_heading:
            _add_para(doc, "1  주요 현안")

        section_order = ["시청·시의회", "정치", "경제", "사회 일반"]

        for section_name in section_order:
            section_items = [x for x in articles if x.get("section") == section_name]
            if not section_items:
                continue

            _add_para(doc, "")
            _add_para(doc, f" {section_name}")

            for item in section_items:
                dept = item.get("department", "관련부서")
                keyword = item.get("keyword", "부산시")

                # 첫째 장에 나온 3건도 본문 분류에서 다시 확인할 수 있게 유지합니다.
                # 원문 샘플처럼 전체 현안 목록 안에 포함되는 구조입니다.
                _add_para(doc, f" ㅇ ({keyword} ‣{dept}) {item.get('title', '')}")
                _add_para(
                    doc,
                    f"    - <{source_short(item.get('source', ''))}> {item.get('summary', '')}"
                )
                _add_para(doc, f"      [▸기사] {item.get('url', '')}")

        doc.save_to_path(str(HWPX_OUTPUT))
        print(f"[DONE] HWPX saved -> {HWPX_OUTPUT}")
        print(
            "[INFO] top issues: "
            + " / ".join(item.get("title", "") for item in top_issues)
        )

    finally:
        try:
            doc.close()
        except Exception:
            pass


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
        for url in links:
            item = fetch_article(source, url)
            if item:
                collected.append(item)
            time.sleep(0.15)

    collected = dedupe(collected)

    if not collected:
        raise SystemExit(
            "수집된 정책 기사가 없습니다. 언론사 HTML 구조 변경 여부를 확인하세요."
        )

    latest_date = max(item["_published"].date() for item in collected)
    latest = [
        item for item in collected
        if item["_published"].date() == latest_date
    ]

    # 중요도 높은 기사부터 홈페이지에도 보이도록 정렬
    latest.sort(
        key=lambda x: (x.get("importance", 0), x["_published"]),
        reverse=True,
    )

    for idx, item in enumerate(latest):
        item["is_top_issue"] = idx < 3
        item.pop("_published", None)

    payload = {
        "articles": latest,
        "article_date": latest_date.isoformat(),
        "last_updated": now.strftime("%Y-%m-%d %H:%M:%S KST"),
        "sources": ["부산일보", "국제신문"],
        "top_issue_count": min(3, len(latest)),
        "sections": ["시청·시의회", "정치", "경제", "사회 일반"],
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[DONE] {len(latest)} articles saved for {latest_date} -> {OUTPUT}")
    create_hwpx(latest, latest_date, now)


if __name__ == "__main__":
    main()
