"""기도문 JSON 검사 (SPEC 10장). 오류가 하나라도 있으면 종료코드 1.

사용법:
  python tools/validate.py            # 전부
  python tools/validate.py <id> ...   # 일부만 (중복 검사는 전체와 비교)
  python tools/validate.py --drafts-only
"""
import datetime as dt
import json
import re
import sys
from collections import Counter

import yaml

from common import PRAYERS, ROOT, load_calendar, chars_no_space, char_range

CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
LAUNCH = str(CFG.get("launch_date", ""))
TOLERANCE = 0.03  # 분량 범위를 3% 벗어난 것까지는 경고로만
DAILY_TYPES = ("오늘의 수험생 기도",)  # 날마다 전날 공개하는 시리즈 — 14일 전 공개 규칙 제외

REQUIRED = {
    "id": str, "slug": str, "status": str, "version": int, "category": str, "worship_type": str,
    "publish_date": str, "season": str, "length_class": str, "title": str, "seo_title": str,
    "seo_description": str, "tags": list, "context": str, "paragraphs": list, "tips": list,
    "customize": list, "author": str,
}
STATUSES = {"draft", "reviewed", "scheduled", "hidden"}
CATEGORIES = {"본당", "소모임", "상황별"}
SLUG_RE = re.compile(r"^[a-z0-9-]+(/[a-z0-9-]+)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# 개역개정 특유 어미 — 긴 문장에 들어 있으면 직접 인용 의심 (경고)
BIBLE_RE = re.compile(r"(하였더라|할지어다|하시니라|하였느니라|하리로다|하였나니|하시리라|하였노라|하였음이라)")
# 교회 실명 패턴: "OO교회" (띄어쓰기 없이). 허용: 우리 교회 / 한국 교회 / 지역 교회 등은 띄어 씀.
CHURCH_RE = re.compile(r"[가-힣]{2,}교회")
CHURCH_ALLOW = {"지역교회", "한국교회", "초대교회", "가정교회", "지상교회", "개척교회", "농어촌교회", "미자립교회", "작은교회", "군선교회", "협력교회", "현지교회", "선교지교회"}
PASTOR_RE = re.compile(r"(?<!담임)([가-힣]{2,4})\s*목사님")
PASTOR_ALLOW = {"담임", "부", "협동", "원로", "선교", "교육", "청년", "강사", "초청", "말씀", "설교", "그", "저희", "우리"}


def load_banned():
    words = []
    for line in (ROOT / "tools" / "banned.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.append(line)
    return words


def sentences(text):
    # 단락 경계(부르는 말의 쉼표 뒤 줄바꿈)에서도 문장을 나눈다
    return [s.strip() for s in re.split(r"(?<=[.!?,])\n|(?<=[.!?])\s+", text) if s.strip()]


_NG = {}


def ngrams_of(p):
    """기도문별 3어절 n-gram 을 한 번만 계산해 둔다 (편수가 늘면 검사가 느려지므로)."""
    key = p.get("id")
    if key not in _NG:
        _NG[key] = ngrams("\n".join(p.get("paragraphs", [])))
    return _NG[key]


def ngrams(text, n=3):
    w = re.sub(r"[^\w\s]", "", text).split()
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def check(p, cal, banned, all_prayers):
    errors, warns = [], []
    E, W = errors.append, warns.append
    pid = p.get("id", "?")

    # --- 스키마
    for k, t in REQUIRED.items():
        if k not in p:
            E(f"필드 없음: {k}")
        elif not isinstance(p[k], t):
            E(f"형식 오류: {k} ({type(p[k]).__name__}, 기대 {t.__name__})")
    if errors:
        return errors, warns
    if p["status"] not in STATUSES:
        E(f"status 값 오류: {p['status']}")
    if p["category"] not in CATEGORIES:
        E(f"category 값 오류: {p['category']}")
    if not SLUG_RE.match(p["slug"]):
        E(f"slug 형식 오류(영문 소문자·숫자·하이픈만): {p['slug']}")
    if not DATE_RE.match(p["publish_date"]):
        E(f"publish_date 형식 오류: {p['publish_date']}")
    if p.get("service_date") and not DATE_RE.match(p["service_date"]):
        E(f"service_date 형식 오류: {p['service_date']}")
    if p["category"] != "상황별" and not p.get("service_date"):
        E("service_date 없음")
    if pid not in cal:
        E("id 가 calendar.csv 에 없음")
    else:
        c = cal[pid]
        if c["category"] != p["category"]:
            E(f"category 가 캘린더와 다름: {c['category']}")
        if (c["service_date"] or None) != p.get("service_date"):
            W(f"service_date 가 캘린더와 다름: {c['service_date']}")
    if not p["paragraphs"]:
        E("paragraphs 비어 있음")
        return errors, warns
    if not p["context"].strip():
        E("context 비어 있음 (해설 2~3문장 필수)")
    if not p["seo_description"].strip():
        E("seo_description 비어 있음")
    elif not 60 <= len(p["seo_description"]) <= 160:
        W(f"seo_description 길이 {len(p['seo_description'])}자 (권장 100~140)")
    if len(p["tips"]) < 2:
        W("tips 2개 이상 권장")
    if not p["tags"]:
        W("tags 비어 있음")
    if not p.get("occasion", "").strip():
        W("occasion(이런 때에) 비어 있음 — 월례회/송년 모임, 월초/중순 등 상황을 한 줄로")

    body = "\n".join(p["paragraphs"])

    # --- 분량
    n = chars_no_space(body)
    lo, hi = char_range(p)
    if not lo <= n <= hi:
        if lo * (1 - TOLERANCE) <= n <= hi * (1 + TOLERANCE):
            W(f"분량 {n}자 — 목표 {lo}~{hi}자 (3% 이내)")
        else:
            E(f"분량 {n}자 — 목표 {lo}~{hi}자")

    # --- 발행일
    if p.get("service_date") and p.get("worship_type") not in DAILY_TYPES:
        gap = (dt.date.fromisoformat(p["service_date"]) - dt.date.fromisoformat(p["publish_date"])).days
        # 첫 공개(launch_date) 묶음은 발행일을 더 앞당길 수 없으므로 예외
        if gap < 14 and p["publish_date"] > LAUNCH:
            E(f"publish_date 가 service_date − 14일보다 늦음 (차이 {gap}일)")
        elif gap < 14:
            W(f"publish_date 가 service_date − {gap}일 (첫 공개 묶음이라 허용)")

    # --- 담임목사님
    cnt = body.count("담임목사님")
    if p["category"] == "본당" and cnt != 1:
        E(f"'담임목사님' {cnt}회 (본당은 정확히 1회)")
    elif cnt > 1:
        W(f"'담임목사님' {cnt}회")

    # --- 맺음말 / 부르는 말
    if not p["paragraphs"][-1].rstrip().endswith("아멘."):
        E("마지막 단락이 '아멘.'으로 끝나지 않음")
    if not re.search(r"예수( 그리스도| ?님)의 이름으로", p["paragraphs"][-1]):
        W("맺음말에 '예수 그리스도의 이름으로' 없음")
    if len(p["paragraphs"][0]) > 40:
        W(f"첫 단락(부르는 말)이 김: {len(p['paragraphs'][0])}자")

    # --- 금칙어
    for w in banned:
        if w in body or w in p["context"]:
            E(f"금칙어: {w}")
    for m in CHURCH_RE.finditer(body):
        if m.group() not in CHURCH_ALLOW:
            E(f"교회 실명 의심: {m.group()}")
    for m in PASTOR_RE.finditer(body):
        if m.group(1) not in PASTOR_ALLOW:
            E(f"목사 실명 의심: {m.group()}")
    if "OOO" in body or "○○○" in body:
        E("본문에 자리표시자(OOO) 있음")

    # --- 문장 길이 / 성경 직접 인용
    for s in sentences(body):
        if len(s) > 90:
            W(f"90자 초과 문장({len(s)}자): {s[:30]}…")
        if len(s) > 40 and BIBLE_RE.search(s):
            W(f"성경 직접 인용 의심: {s[:40]}…")

    # --- 중복 (3어절 n-gram)
    mine = ngrams_of(p)
    if mine:
        for q in all_prayers:
            if q["id"] == pid or not q.get("paragraphs"):
                continue
            other = ngrams_of(q)
            ratio = len(mine & other) / len(mine)
            if ratio > 0.25:
                W(f"{q['id']} 와 3어절 겹침 {ratio:.0%}")

    return errors, warns


def check_openings(all_prayers):
    """본당 주일 오전 기도문에서 같은 부르는 말이 4주 연속이면 경고."""
    warns = []
    seq = sorted((p for p in all_prayers if p.get("category") == "본당" and p.get("worship_type") == "주일 오전예배"
                  and p.get("paragraphs")), key=lambda p: p["service_date"])
    run = 1
    for a, b in zip(seq, seq[1:]):
        run = run + 1 if a["paragraphs"][0] == b["paragraphs"][0] else 1
        if run >= 4:
            warns.append((b["id"], f"부르는 말이 4주 연속 같음: {b['paragraphs'][0]}"))
    return warns


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    drafts_only = "--drafts-only" in sys.argv
    cal = load_calendar()
    banned = load_banned()
    all_prayers = []
    for f in sorted(PRAYERS.glob("*.json")):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"✗ {f.name}: JSON 파싱 오류 — {e}")
            sys.exit(1)
        p["_file"] = f.name
        all_prayers.append(p)

    targets = all_prayers
    if args:
        targets = [p for p in all_prayers if p.get("id") in args or p["_file"][:-5] in args]
    if drafts_only:
        targets = [p for p in targets if p.get("status") == "draft"]

    ne = nw = 0
    opening_warns = {}
    for pid, msg in check_openings(all_prayers):
        opening_warns.setdefault(pid, []).append(msg)
    for p in targets:
        errors, warns = check(p, cal, banned, all_prayers)
        warns += opening_warns.get(p.get("id"), [])
        ne += len(errors)
        nw += len(warns)
        mark = "✗" if errors else ("△" if warns else "✓")
        n = chars_no_space("\n".join(p.get("paragraphs", [])))
        print(f"{mark} {p['_file']:40s} {p.get('status', ''):9s} {n:5d}자")
        for e in errors:
            print(f"    오류: {e}")
        for w in warns:
            print(f"    경고: {w}")
    ids = Counter(p.get("id") for p in all_prayers)
    slugs = Counter(p.get("slug") for p in all_prayers)
    for k, c in list(ids.items()) + list(slugs.items()):
        if c > 1:
            print(f"✗ 중복 id/slug: {k}")
            ne += 1
    print(f"[validate] {len(targets)}편 검사 — 오류 {ne}, 경고 {nw}")
    sys.exit(1 if ne else 0)


if __name__ == "__main__":
    main()
