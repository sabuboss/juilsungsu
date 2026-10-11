#!/usr/bin/env python3
"""content/prayers/*.json -> dist/  (대표기도문 정적 사이트 생성)

사용법:
  python build.py                       # 오늘(KST) 기준 공개 대상만 발행
  python build.py --today 2026-11-09    # 날짜를 바꿔 미래 공개 상태 미리보기
  python build.py --drafts              # draft 도 포함 (검수 대기 띠 표시)
  python build.py --serve [--port 8000] # 빌드 후 로컬 서버

공개 규칙 (PRAYER_SITE_SPEC.md 4장):
  status ∈ {reviewed, scheduled} 이고 max(publish_date, launch_date) <= 오늘 인 글만 공개.
  예배일이 지난 글도 내리지 않는다.
"""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import shutil
import sys
from xml.sax.saxutils import escape

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = pathlib.Path(__file__).parent
DIST = ROOT / "dist"
PRAYERS = ROOT / "content" / "prayers"
PAGES = ROOT / "content" / "pages"

sys.path.insert(0, str(ROOT / "tools"))
from common import (  # noqa: E402
    GROUP_KEYS, SEASON_KEYS, SEASON_NAMES, SEASON_COLORS, CATEGORY_OG,
    chars_no_space, read_minutes, read_label, load_calendar, group_key, season_key,
)

# ---------------------------------------------------------------- 설정

cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
BASE = cfg["base_url"].rstrip("/")
LAUNCH = dt.date.fromisoformat(str(cfg["launch_date"]))
CPM = int(cfg.get("read_cpm", 270))

ap = argparse.ArgumentParser()
ap.add_argument("--today", help="YYYY-MM-DD (기본: 오늘 KST)")
ap.add_argument("--drafts", action="store_true", help="draft 도 포함해 미리보기")
ap.add_argument("--serve", action="store_true")
ap.add_argument("--port", type=int, default=8000)
args = ap.parse_args()

if args.today:
    TODAY = dt.date.fromisoformat(args.today)
else:
    # GitHub Actions 는 UTC 로 돌므로 KST 로 환산한다.
    TODAY = (dt.datetime.utcnow() + dt.timedelta(hours=9)).date()

WEEKDAY_KO = "월화수목금토일"

env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)


def asset(name):
    """/static/<name>?v=<내용 해시> — Cloudflare 캐시 때문에 내용이 바뀌면 주소도 바뀌어야 한다."""
    h = hashlib.md5((ROOT / "static" / name).read_bytes()).hexdigest()[:8]
    return f"/static/{name}?v={h}"


def fmt_date(s, with_weekday=True):
    if not s:
        return ""
    d = dt.date.fromisoformat(s)
    out = f"{d.year}.{d.month:02d}.{d.day:02d}"
    if with_weekday:
        out += f" ({'주일' if d.weekday() == 6 else WEEKDAY_KO[d.weekday()]})"
    return out


def fmt_month(ym):
    y, m = ym.split("-")
    return f"{int(y)}년 {int(m)}월"


env.globals.update(site=cfg, asset=asset, fmt_date=fmt_date, fmt_month=fmt_month,
                   today=TODAY.isoformat(), season_colors=SEASON_COLORS, season_names=SEASON_NAMES,
                   group_names={v: k for k, v in GROUP_KEYS.items()})

# 광고: adsense_client 가 비어 있으면 광고 코드를 전혀 넣지 않는다 (완료 기준).
if cfg.get("adsense_client"):
    _slot = cfg.get("adsense_slot", "")
    if _slot:
        AD = ('<ins class="adsbygoogle" style="display:block" data-ad-client="%s" data-ad-slot="%s"'
              ' data-ad-format="auto" data-full-width-responsive="true"></ins>'
              '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script>') % (cfg["adsense_client"], _slot)
    else:
        AD = ""  # 자동 광고에 맡김
elif args.drafts:
    AD = '<div class="ad">광고 영역 (AdSense)</div>'
else:
    AD = ""
env.globals["ad"] = AD


# ---------------------------------------------------------------- 데이터 읽기

def load_prayers():
    items = []
    for f in sorted(PRAYERS.glob("*.json")):
        p = json.loads(f.read_text(encoding="utf-8"))
        p["_file"] = f.name
        items.append(p)
    return items


def effective_publish(p):
    d = dt.date.fromisoformat(p["publish_date"])
    return max(d, LAUNCH)


def is_public(p):
    if p.get("status") in ("reviewed", "scheduled"):
        return effective_publish(p) <= TODAY
    return False


# 날짜가 교회마다 다른 행사(성경학교·수련회·칸타타·발표회·총회·송년·교사 헌신·수험생): 달력 날짜 칸에 넣지 않는다
UNFIXED_TYPES = ("절기 특별", "정기총회", "송년 모임")


def is_unfixed(p):
    return p.get("category") == "소모임" and p.get("worship_type") in UNFIXED_TYPES


def enrich(p):
    """빌드용 파생 필드. stats 는 매번 재계산한다 (7장)."""
    body = "\n\n".join(p["paragraphs"])
    n = chars_no_space(body)
    p["stats"] = {
        "chars_no_space": n,
        "chars_with_space": len(body.replace("\n", "")),
        "read_minutes": read_minutes(n, CPM),
    }
    p["read_label"] = read_label(n, CPM)
    p["url"] = f"/p/{p['slug']}/"
    p["abs_url"] = BASE + p["url"]
    p["print_url"] = f"/p/{p['slug']}/print/"
    p["is_draft"] = p.get("status") == "draft"
    p["eff_publish"] = effective_publish(p).isoformat()
    p["month"] = p["service_date"][:7] if p.get("service_date") else None
    p["season_key"] = season_key(p.get("season"))
    p["group_key"] = group_key(p.get("group"))
    p["color"] = SEASON_COLORS.get(p["season_key"], "green")
    p["og_image"] = BASE + CATEGORY_OG.get(p["category"], "/static/og/home.png")
    # 홈·목록 카드용 짧은 날짜 라벨
    if p.get("service_date"):
        p["date_label"] = fmt_date(p["service_date"])
        if p["worship_type"] in ("월례 모임", "수요예배", "금요기도회"):
            p["date_label"] = fmt_month(p["month"]) + " 내내"
        elif p["worship_type"] == "월초 기도":
            p["date_label"] = fmt_month(p["month"]) + " 첫 주"
        elif is_unfixed(p):
            p["date_label"] = fmt_month(p["month"]) + " 중 · 날짜는 교회 일정대로"
    else:
        p["date_label"] = "날짜 없음 · 상시"
    return p


# ---------------------------------------------------------------- 달력 /calendar/{yyyy-mm}/
MONTHLY_TYPES = ("월례 모임", "월초 기도", "수요예배", "금요기도회")


def cal_label(p):
    """달력 칸에 들어갈 짧은 이름."""
    g, wt = p.get("group") or "", p["worship_type"]
    if wt == "월초 기도":
        return f"{g} 월초"
    if wt == "월례 모임":
        if "월례회" in p["title"]:
            return f"{g} 월례회"
        return f"{g} {'연습' if g == '성가대' else '예배'}"
    if wt in ("수요예배", "금요기도회"):
        return wt
    if wt == "주일 오후·저녁예배":
        return "오후·저녁예배"
    if wt == "정기총회":
        return f"{g} 총회"
    if wt == "송년 모임":
        return f"{g} 송년"
    if wt == "절기 특별":
        t = re.sub(r"^\d{4}년 ", "", p["title"])
        t = re.sub(r"\s*기도(문)?$", "", t).replace("교회학교 연합 ", "교회학교 ").replace(" 축하 ", " ")
        return t.replace("을 위한", "").replace("수험생 ", "수험생")
    if p["category"] == "본당" and p["id"].endswith("-sp"):
        t = re.sub(r"^\d{4}년 ", "", p["title"])
        return re.sub(r"\s*(예배)?\s*대표기도문$", "", t)
    t = re.sub(r"^\d{4}년 ", "", p["title"])
    t = re.sub(r"\s*(대표기도문|기도문)$", "", t)
    if p["category"] == "본당" and p["worship_type"] == "주일 오전예배":
        t = re.sub(r"\(.*?\)", "", t).replace(" 오전예배", "").strip()
        if re.match(r"^\d+월 .+째 주일$", t):
            t = "주일 오전예배"
    return t


def planned_rows(known_ids):
    """calendar.csv 에는 있지만 아직 기도문(JSON)이 없는 예배 — 달력에 '준비 중'으로 보여 준다."""
    out = []
    for r in load_calendar().values():
        if r["id"] in known_ids or not r["service_date"]:
            continue
        out.append({"id": r["id"], "title": r["title"], "category": r["category"], "worship_type": r["worship_type"],
                    "group": r["group"] or None, "service_date": r["service_date"], "season": r["season"],
                    "color": SEASON_COLORS.get(season_key(r["season"]), "green"), "eff_publish": r["publish_date"],
                    "url": None, "planned": True})
    return out


def build_calendar(shown, upcoming_all, planned=()):
    """공개 글 + 공개 예정(reviewed/scheduled) 글 + 캘린더상 준비 중 예배로 달력 페이지를 만든다."""
    import calendar as _cal
    items = {p["id"]: p for p in planned}
    items.update({p["id"]: p for p in upcoming_all})
    items.update({p["id"]: p for p in shown})
    dated = [p for p in items.values() if p.get("service_date")]
    if not dated:
        return []
    months = sorted({p["service_date"][:7] for p in dated})
    first, last = months[0], months[-1]
    ym_list = []
    y, m = map(int, first.split("-"))
    while f"{y}-{m:02d}" <= last:
        ym_list.append(f"{y}-{m:02d}"); m += 1
        if m == 13:
            y, m = y + 1, 1
    shown_ids = {p["id"] for p in shown}

    def entry(p):
        return {"label": cal_label(p), "title": p["title"], "url": p["url"] if p["id"] in shown_ids else None,
                "pub": ("준비 중" if p.get("planned") else fmt_date(p["eff_publish"], False)[5:].replace(".", "/") + " 공개")
                       if p["id"] not in shown_ids else "",
                "color": p["color"], "cat": p["category"], "group": p.get("group") or ""}

    out = []
    for i, ym in enumerate(ym_list):
        y, m = map(int, ym.split("-"))
        monthly = sorted((p for p in dated if p["service_date"][:7] == ym and (p["worship_type"] in MONTHLY_TYPES or is_unfixed(p))),
                         key=lambda p: (is_unfixed(p), p["worship_type"], p.get("group") or ""))
        by_day = {}
        for p in dated:
            if p["service_date"][:7] == ym and p["worship_type"] not in MONTHLY_TYPES and not is_unfixed(p):
                by_day.setdefault(p["service_date"], []).append(p)
        weeks = []
        for wk in _cal.Calendar(firstweekday=6).monthdatescalendar(y, m):
            weeks.append([{"d": d.day, "iso": d.isoformat(), "in": d.month == m, "today": d == TODAY,
                           "sun": d.weekday() == 6,
                           "items": [entry(p) for p in sorted(by_day.get(d.isoformat(), []),
                                                               key=lambda p: (p["category"] != "본당", p["id"]))]}
                          for d in wk])
        agenda = [(fmt_date(d), [entry(p) for p in sorted(by_day[d], key=lambda p: (p["category"] != "본당", p["id"]))])
                  for d in sorted(by_day)]
        out.append({"ym": ym, "y": y, "m": m, "weeks": weeks, "agenda": agenda,
                    "monthly": [entry(p) for p in monthly],
                    "prev": ym_list[i - 1] if i else None, "next": ym_list[i + 1] if i + 1 < len(ym_list) else None})
    return out


# 예배·상황 종류별 모음 페이지 /type/{key}/ — 상단 빠른 찾기에서 바로 들어간다
TYPE_PAGES = [
    ("sunday", "주일예배", lambda p: p["category"] == "본당" and p["worship_type"].startswith("주일")),
    ("dawn-prayer", "특별새벽기도회", lambda p: p["worship_type"] == "특별새벽기도회"),
    ("church-year", "절기 대표기도", lambda p: p["worship_type"] == "절기 예배"),
    ("special-worship", "절기 특별예배", lambda p: p["category"] == "본당" and p["id"].endswith("-sp")),
    ("wednesday", "수요예배", lambda p: p["worship_type"] == "수요예배"),
    ("friday", "금요기도회", lambda p: p["worship_type"] == "금요기도회"),
    ("funeral", "장례", lambda p: p["worship_type"] == "장례"),
    ("wedding", "결혼", lambda p: p["worship_type"] == "결혼"),
    ("dedication", "헌신예배", lambda p: p["worship_type"] == "헌신예배"),
    ("church-event", "임직·창립", lambda p: p["worship_type"] == "교회행사"),
    ("visit", "심방", lambda p: p["worship_type"] == "심방"),
    ("home-worship", "가정예배", lambda p: p["worship_type"] == "가정예배"),
    ("meeting", "회의", lambda p: p["worship_type"] == "회의"),
    ("committee", "위원회·봉사부서", lambda p: p["worship_type"] == "위원회·부서 모임"),
]
WORSHIP_TYPES = ["sunday", "church-year", "dawn-prayer", "special-worship", "wednesday", "friday"]
SITUATION_TYPES = ["committee", "funeral", "wedding", "dedication", "church-event", "visit", "home-worship", "meeting"]
TYPE_LEADS = {
    "sunday": "주일 오전·오후(저녁)예배 대표기도문입니다. 실제 낭독 약 4분 분량입니다.",
    "dawn-prayer": "특별새벽기도회 요일별(월~토) 대표기도문과 요일 무관 공통 기도문입니다. 날마다 공동기도제목을 모두 담았습니다.",
    "church-year": "사순절·종려주일·성금요일·부활절·어린이주일·어버이주일·성령강림·맥추감사·삼일절·현충일·광복절·설·추석·신년·추수감사·성탄·송구영신 등 해마다 돌아오는 절기에 연도와 상관없이 그대로 쓸 수 있는 대표기도문입니다. 약 4분 분량입니다.",
    "special-worship": "성탄 전야·성탄절·송구영신·성금요일처럼 주일 외에 드리는 절기 특별예배 대표기도문입니다.",
    "funeral": "임종·입관·발인·하관 예배에서 쓰는 1~2분 기도문입니다. 위로를 먼저 담았습니다.",
    "wedding": "결혼예배 대표기도문입니다.",
    "dedication": "남전도회·여전도회·권사회·안수집사회·청년부·교회학교 헌신예배 대표기도문입니다.",
    "church-event": "임직예배, 교회 창립기념주일 등 교회 행사 대표기도문입니다.",
    "committee": "재정위원회·새가족부·헌금계수부·선교위원회·차량부·식당봉사부·의료선교부·교회카페 등 위원회와 봉사부서 38곳의 모임을 시작할 때 드리는 개회 기도문입니다.",
}


def breadcrumbs(p):
    crumbs = [("홈", "/")]
    if p["category"] == "상황별":
        crumbs.append(("상황별 기도문", "/anytime/"))
    elif p["category"] == "소모임" and p["group_key"]:
        crumbs.append((p["group"], f"/group/{p['group_key']}/"))
    elif p["month"]:
        crumbs.append((fmt_month(p["month"]), f"/month/{p['month']}/"))
    crumbs.append((p["title"], p["url"]))
    return crumbs


def jsonld(p, crumbs):
    article = {
        "@context": "https://schema.org", "@type": "Article",
        "headline": p["seo_title"], "description": p["seo_description"],
        "datePublished": p["eff_publish"], "dateModified": p["eff_publish"],
        "author": {"@type": "Person", "name": cfg.get("author", "")},
        "publisher": {"@type": "Organization", "name": cfg["site_name"]},
        "mainEntityOfPage": p["abs_url"], "inLanguage": "ko", "image": p["og_image"],
        "keywords": ", ".join(p.get("tags", [])),
    }
    bl = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": BASE + u} for i, (n, u) in enumerate(crumbs)]}
    return json.dumps([article, bl], ensure_ascii=False)


def related(p, pub):
    """같은 주일 다른 예배 / 같은 달 소모임 / 다음 주일 오전."""
    out = []
    seen = {p["id"]}

    def add(q, label):
        if q and q["id"] not in seen:
            seen.add(q["id"])
            out.append((label, q))

    if p.get("service_date"):
        if p["category"] == "소모임" and p.get("group"):
            # 같은 부서·같은 달의 월례회 / 정기총회 / 송년 모임을 먼저 보여 줘 상황에 맞게 고르게 한다
            for q in pub:
                if q.get("group") == p["group"] and q["month"] == p["month"]:
                    add(q, f"같은 달 {p['group']} · {q['worship_type']}")
        for q in pub:
            if q["service_date"] == p["service_date"] and q["category"] == "본당":
                add(q, "같은 날 다른 예배")
        if p["category"] == "본당":
            for q in sorted((q for q in pub if q["category"] == "소모임" and q["month"] == p["month"]),
                            key=lambda q: q["title"])[:4]:
                add(q, "같은 달 소모임")
        else:
            for q in pub:
                if q["category"] == "본당" and q["month"] == p["month"] and q["worship_type"] == "주일 오전예배":
                    add(q, "같은 달 주일 오전예배")
        nxt = [q for q in pub if q["category"] == "본당" and q["worship_type"] == "주일 오전예배"
               and q["service_date"] > p["service_date"]]
        if nxt:
            add(min(nxt, key=lambda q: q["service_date"]), "다음 주일")
    else:
        # 같은 묶음(예: 특별새벽기도회 다른 요일, 장례 다른 순서)을 먼저
        same = [q for q in pub if q["category"] == "상황별" and q["worship_type"] == p["worship_type"]]
        for q in sorted(same, key=lambda q: q["id"]):
            add(q, f"같은 {p['worship_type']}")
        for q in [q for q in pub if q["category"] == "상황별"][:4]:
            add(q, "다른 상황별 기도문")
    return out[:6]


# ---------------------------------------------------------------- 쓰기

def write(path, html):
    out = DIST / path.lstrip("/")
    if path.endswith("/") or not out.suffix:
        out = out / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")


def render(tpl, path, **ctx):
    ctx.setdefault("canonical", BASE + path)
    write(path, env.get_template(tpl).render(**ctx))


def md_page(path):
    """pages/*.md: 앞머리(title/description/updated) + HTML 본문. 마크다운 변환기 없이 그대로 쓴다."""
    raw = path.read_text(encoding="utf-8")
    head, body = raw.split("\n---\n", 1)
    meta = yaml.safe_load(head)
    body = body.replace("{{site_name}}", cfg["site_name"]).replace("{{base_url}}", BASE)
    return meta, body


def rfc822(d):
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    mons = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return "%s, %02d %s %d 09:00:00 +0900" % (days[d.weekday()], d.day, mons[d.month - 1], d.year)


def main():
    all_prayers = [enrich(p) for p in load_prayers()]
    pub = [p for p in all_prayers if is_public(p)]
    shown = pub + ([p for p in all_prayers if p["is_draft"]] if args.drafts else [])
    shown.sort(key=lambda p: (p.get("service_date") or "9999", p["id"]))
    pub_ids = {p["id"] for p in pub}

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    shutil.copytree(ROOT / "static", DIST / "static")

    # ---- 상단 빠른 찾기 (공개 글이 있는 묶음만 칩으로 보여 준다)
    seasons_present = []
    for k in SEASON_KEYS:
        n = sum(1 for p in shown if p["season_key"] == k)
        if n:
            seasons_present.append((k, SEASON_NAMES[k], n))
    types_present = [(k, name, [p for p in shown if fn(p)]) for k, name, fn in TYPE_PAGES]
    types_present = [(k, name, items) for k, name, items in types_present if items]
    groups_present = [(name, k) for name, k in GROUP_KEYS.items() if any(p["group_key"] == k for p in shown)]
    tnames = {k: name for k, name, _ in types_present}
    env.globals["quicknav"] = [
        ("예배", [(tnames[k], f"/type/{k}/") for k in WORSHIP_TYPES if k in tnames]),
        ("절기", [(name, f"/season/{k}/") for k, name, _ in seasons_present]),
        ("부서", [(name, f"/group/{k}/") for name, k in groups_present]),
        ("상황", [(tnames[k], f"/type/{k}/") for k in SITUATION_TYPES if k in tnames]),
    ]

    # ---- 상세 + 인쇄
    for p in shown:
        crumbs = breadcrumbs(p)
        render("prayer.html", p["url"], p=p, crumbs=crumbs, related=related(p, shown),
               jsonld=jsonld(p, crumbs), canonical=p["abs_url"])
        render("print.html", p["print_url"], p=p)

    # ---- 홈
    def next_sundays(n=2):
        d = TODAY + dt.timedelta(days=(6 - TODAY.weekday()) % 7)
        return [(d + dt.timedelta(weeks=i)).isoformat() for i in range(n)]

    this_sun, next_sun = next_sundays()
    by_date = {}
    for p in shown:
        if p["category"] == "본당" and p["worship_type"] == "주일 오전예배":
            by_date[p["service_date"]] = p
    hero = [(lbl, by_date.get(d), d) for lbl, d in (("이번 주일", this_sun), ("다음 주일", next_sun))]
    upcoming = [p for p in shown if p["category"] == "본당" and p["worship_type"] not in ("수요예배", "금요기도회")
                and p["service_date"] >= TODAY.isoformat() and p["id"] not in (q["id"] for _, q, _ in hero if q)][:6]
    this_month = TODAY.strftime("%Y-%m")
    month_groups = [p for p in shown if p["category"] == "소모임" and p["month"] in (this_month, next_sun[:7])]
    anytime = [p for p in shown if p["category"] == "상황별"]
    months =sorted({p["month"] for p in shown if p["month"]})
    render("home.html", "/", hero=hero, upcoming=upcoming, month_groups=month_groups[:12], anytime=anytime[:8],
           seasons=seasons_present, months=months, total=len(pub))

    # ---- 월별 / 절기 / 부서 / 상황별 허브
    for ym in months:
        items = [p for p in shown if p["month"] == ym]
        render("list.html", f"/month/{ym}/", kind="month", key=ym, title=f"{fmt_month(ym)} 대표기도문 모음",
               lead=f"{fmt_month(ym)} 주일예배·수요·금요·소모임 대표기도문을 한곳에 모았습니다.", items=items,
               groups=[(k, sum(1 for p in items if p["category"] == k)) for k in ("본당", "소모임")])
    for k, name, _ in seasons_present:
        items = [p for p in shown if p["season_key"] == k]
        render("list.html", f"/season/{k}/", kind="season", key=k, title=f"{name} 대표기도문 모음",
               lead=f"{name} 절기에 드리는 대표기도문입니다.", items=items)
    for name, k in GROUP_KEYS.items():
        items = [p for p in shown if p["group_key"] == k]
        if not items:
            continue
        render("list.html", f"/group/{k}/", kind="group", key=k, title=f"{name} 대표기도문 모음",
               lead=f"{name} 월례 모임과 절기 행사에 쓰는 2분 이내의 대표기도문입니다.", items=items)
    render("list.html", "/anytime/", kind="anytime", key="anytime", title="상황별 기도문",
           lead="장례·결혼·헌신예배·심방·회의 등 날짜와 상관없이 쓰는 기도문입니다.", items=anytime)
    for k, name, items in types_present:
        render("list.html", f"/type/{k}/", kind="type", key=k, title=f"{name} 기도문 모음",
               lead=TYPE_LEADS.get(k, f"{name} 기도문을 한곳에 모았습니다."), items=items)

    # ---- 달력
    scheduled = [p for p in all_prayers if p.get("status") in ("reviewed", "scheduled") and p["id"] not in pub_ids]
    cal_months = build_calendar(shown, scheduled, planned_rows({p["id"] for p in all_prayers}))
    cur = TODAY.strftime("%Y-%m")
    for cm in cal_months:
        render("calendar.html", f"/calendar/{cm['ym']}/", cm=cm)
    if cal_months:
        pick = next((cm for cm in cal_months if cm["ym"] == cur), cal_months[0])
        render("calendar.html", "/calendar/", cm=pick, canonical=f"{BASE}/calendar/{pick['ym']}/")

    # ---- 고정 페이지
    for md in sorted(PAGES.glob("*.md")):
        meta, body = md_page(md)
        render("page.html", f"/{md.stem}/", meta=meta, body=body)
    render("search.html", "/search/")
    write("/404.html", env.get_template("404.html").render(canonical=BASE + "/404.html"))

    # ---- 검색 인덱스 (공개 글만)
    idx = [{"id": p["id"], "t": p["title"], "u": p["url"], "d": p.get("service_date") or "", "c": p["category"],
            "g": p.get("group") or "", "s": p.get("season") or "", "w": p["worship_type"],
            "tags": p.get("tags", []), "o": p.get("occasion", ""), "x": p["context"][:80]} for p in shown if p["id"] in pub_ids]
    (DIST / "search-index.json").write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")

    # ---- sitemap / rss / robots / ads.txt / _headers  (공개 글만)
    urls = [("/", TODAY.isoformat(), "daily")]
    urls += [(p["url"], p["eff_publish"], "monthly") for p in pub]
    urls += [(f"/month/{m}/", TODAY.isoformat(), "weekly") for m in months]
    urls += [(f"/season/{k}/", TODAY.isoformat(), "weekly") for k, _, _ in seasons_present]
    urls += [(f"/type/{k}/", TODAY.isoformat(), "weekly") for k, _, items in types_present
             if any(p["id"] in pub_ids for p in items)]
    urls += [(f"/group/{k}/", TODAY.isoformat(), "weekly") for k in GROUP_KEYS.values()
             if any(p["group_key"] == k for p in pub)]
    urls += [(f"/calendar/{cm['ym']}/", TODAY.isoformat(), "weekly") for cm in cal_months]
    urls += [("/anytime/", TODAY.isoformat(), "weekly"), ("/about/", LAUNCH.isoformat(), "yearly"), ("/guide/", TODAY.isoformat(), "monthly"),
             ("/privacy/", LAUNCH.isoformat(), "yearly"), ("/contact/", LAUNCH.isoformat(), "yearly")]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, lm, cf in urls:
        sm.append(f"  <url><loc>{BASE}{u}</loc><lastmod>{lm}</lastmod><changefreq>{cf}</changefreq></url>")
    sm.append("</urlset>")
    (DIST / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")

    recent = sorted(pub, key=lambda p: (p["eff_publish"], p["id"]), reverse=True)[:50]
    rss = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>',
           f"<title>{escape(cfg['site_name'])}</title><link>{BASE}/</link>",
           "<description>주일예배·소모임·상황별 대표기도문</description><language>ko</language>",
           f"<lastBuildDate>{rfc822(TODAY)}</lastBuildDate>",
           f'<atom:link href="{BASE}/rss.xml" rel="self" type="application/rss+xml"/>']
    for p in recent:
        rss.append(f"<item><title>{escape(p['seo_title'])}</title><link>{p['abs_url']}</link>"
                   f'<guid isPermaLink="true">{p["abs_url"]}</guid>'
                   f"<description>{escape(p['seo_description'])}</description>"
                   f"<category>{escape(p['category'])}</category>"
                   f"<pubDate>{rfc822(dt.date.fromisoformat(p['eff_publish']))}</pubDate></item>")
    rss.append("</channel></rss>")
    (DIST / "rss.xml").write_text("\n".join(rss), encoding="utf-8")

    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /search/\nSitemap: {BASE}/sitemap.xml\n",
                                     encoding="utf-8")
    if cfg.get("adsense_client"):
        pub_id = cfg["adsense_client"].replace("ca-", "")
        (DIST / "ads.txt").write_text(f"google.com, {pub_id}, DIRECT, f08c47fec0942fa0\n", encoding="utf-8")
    (DIST / "_headers").write_text(
        "/*\n  X-Content-Type-Options: nosniff\n  X-Frame-Options: SAMEORIGIN\n"
        "  Referrer-Policy: strict-origin-when-cross-origin\n"
        "  Permissions-Policy: camera=(), microphone=(), geolocation=()\n"
        "/static/*\n  Cache-Control: public, max-age=31536000, immutable\n", encoding="utf-8")

    n_draft = len(shown) - len(pub)
    print(f"[build] today={TODAY} public={len(pub)}" + (f" +drafts={n_draft}" if args.drafts else "")
          + f" total_json={len(all_prayers)} -> {DIST}")
    for p in pub:
        print(f"  - {p['eff_publish']}  {p['id']:36s} {p['title']}")


if __name__ == "__main__":
    main()
    if args.serve:
        import functools
        import http.server
        H = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DIST))
        print(f"http://localhost:{args.port}/  (Ctrl+C 로 중지)")
        http.server.ThreadingHTTPServer(("", args.port), H).serve_forever()
