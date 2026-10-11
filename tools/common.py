"""build.py 와 tools/*.py 가 함께 쓰는 상수·함수."""
import csv
import math
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CALENDAR = ROOT / "content" / "calendar.csv"
PRAYERS = ROOT / "content" / "prayers"

# 부서 이름 -> URL key (SPEC 3.2)
GROUP_KEYS = {
    "권사회": "gwonsa", "남전도회": "namjeondo", "장립집사회": "anripjipsa", "성가대": "choir",
    "청년부": "youngadult", "중고등부": "youth", "초등부": "elementary", "유치부": "kinder",
    "영아부": "infant", "여전도회": "yeojeondo", "교회학교 교사회": "teachers", "구역(속회)예배": "cell",
    "교회학교 연합": "church-school",
}

# 부서별 분량 목표 (공백 제외, SPEC 3.2)
GROUP_CHARS = {
    "gwonsa": (400, 520), "namjeondo": (400, 520), "anripjipsa": (400, 520), "choir": (350, 480),
    "youngadult": (400, 520), "youth": (350, 450), "elementary": (300, 400), "kinder": (300, 380),
    "infant": (300, 380), "yeojeondo": (400, 520), "teachers": (400, 520), "cell": (400, 520),
    "church-school": (300, 450),
}

# 월초(한 달을 여는) 기도: 정기 월례회보다 짧게, 약 1분~1분 30초
MONTH_START_CHARS = (230, 420)

# length_class -> 글자수 범위 (SPEC 7장)
LENGTH_CHARS = {"3~4분": (850, 1080), "2~3분": (540, 810), "2분 이내": (270, 520), "1~2분": (270, 520)}

# 절기 허브 (SPEC 9.1). 캘린더의 season 태그를 이 key 로 묶는다.
SEASON_NAMES = {
    "thanksgiving": "추수감사", "advent": "대림절", "christmas": "성탄", "yearend": "송구영신",
    "newyear": "신년", "lent": "사순절", "easter": "부활절", "family": "가정의 달",
    "pentecost": "성령강림", "harvest": "맥추감사", "nation": "나라사랑", "holiday": "명절",
    "reformation": "종교개혁",
}
SEASON_KEYS = list(SEASON_NAMES)
_SEASON_MAP = {
    "추수감사": "thanksgiving", "대림절": "advent", "대림과 성탄": "advent", "성탄": "christmas",
    "송년": "yearend", "송구영신": "yearend", "신년": "newyear", "새해 결단": "newyear",
    "사순절": "lent", "사순절 준비": "lent", "고난주간": "lent", "고난과 부활": "lent",
    "부활절": "easter", "부활의 소망": "easter", "가정의 달": "family", "가정의달": "family",
    "성령강림": "pentecost", "여름 사역·맥추": "harvest", "맥추감사": "harvest", "여름사역": "harvest",
    "나라와 민족": "nation", "나라사랑": "nation", "광복과 쉼": "nation",
    "명절": "holiday", "추석·결실": "holiday", "종교개혁·말씀": "reformation", "종교개혁": "reformation",
}
# 칩 색 (SPEC 9.3): 대림·사순=보라, 성탄·부활=금, 성령강림=빨강, 평상=초록
SEASON_COLORS = {"advent": "purple", "lent": "purple", "christmas": "gold", "easter": "gold",
                 "pentecost": "red"}

CATEGORY_OG = {"본당": "/static/og/main.png", "소모임": "/static/og/group.png", "상황별": "/static/og/anytime.png"}


def season_key(name):
    return _SEASON_MAP.get(name or "")


def group_key(name):
    return GROUP_KEYS.get(name or "")


def chars_no_space(text):
    return len(re.sub(r"\s", "", text))


def read_minutes(n, cpm=270):
    return round(n / cpm, 1)


def read_label(n, cpm=270):
    """'약 3분 20초' — 10초 단위로 반올림."""
    sec = int(round(n / cpm * 60 / 10.0)) * 10
    m, s = divmod(sec, 60)
    return f"약 {m}분" + (f" {s}초" if s else "")


def load_calendar():
    with open(CALENDAR, encoding="utf-8-sig", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def char_range(p):
    """기도문 한 편의 글자수 허용 범위 (부서 목표가 있으면 그것을 우선)."""
    if p.get("worship_type") == "월초 기도":
        return MONTH_START_CHARS
    gk = group_key(p.get("group"))
    if p.get("category") == "소모임" and gk in GROUP_CHARS:
        return GROUP_CHARS[gk]
    return LENGTH_CHARS.get(p.get("length_class", ""), (270, 1080))
