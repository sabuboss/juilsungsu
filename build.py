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
    else:
        p["date_label"] = "날짜 없음 · 상시"
    return p


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
        for q in [q for q in pub if q["category"] == "상황별" and q["id"] != p["id"]][:4]:
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
    seasons_present = []
    for k in SEASON_KEYS:
        n = sum(1 for p in shown if p["season_key"] == k)
        if n:
            seasons_present.append((k, SEASON_NAMES[k], n))
    months = sorted({p["month"] for p in shown if p["month"]})
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
    urls += [(f"/group/{k}/", TODAY.isoformat(), "weekly") for k in GROUP_KEYS.values()
             if any(p["group_key"] == k for p in pub)]
    urls += [("/anytime/", TODAY.isoformat(), "weekly"), ("/about/", LAUNCH.isoformat(), "yearly"),
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
