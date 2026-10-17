"""네이버 블로그·티스토리에 붙여 넣을 소개 글 초안을 만든다 (사이트 유입용).

기도문 전문을 옮기면 사이트와 중복 문서가 되므로, 앞부분 일부와 쓰는 요령만 싣고
'전문·인쇄용은 사이트에서'로 연결한다. 결과는 private/blog/ 에 .txt 로 저장(커밋 안 됨).

사용법:
  python tools/blog_drafts.py --ids main-20261025-am anytime-01
  python tools/blog_drafts.py --type year-end      # /type/{key}/ 모음 페이지 소개 글
  python tools/blog_drafts.py --week               # 오늘부터 7~13일 뒤 주일 오전·오후 기도문
"""
import argparse
import datetime as dt
import json
import re
import sys

import yaml

from common import PRAYERS, ROOT

CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
BASE = CFG["base_url"].rstrip("/")
OUT = ROOT / "private" / "blog"
UTM = "utm_source=blog&utm_medium=referral&utm_campaign=blog_post"
TYPE_INFO = {  # 모음 페이지 소개 글 (build.py TYPE_PAGES 와 같은 key)
    "year-end": ("연말 총회·송년 기도문 모음", ["정기총회 기도문", "제직회 기도문", "공동의회 기도", "송년회 기도문", "임원 이취임 기도"],
                 "연말이 되면 기관마다 정기총회, 제직회와 공동의회, 송년 모임이 이어지지요. 개회 기도나 대표기도를 갑자기 맡으셨을 때 바로 쓰실 수 있는 기도문을 한곳에 모았습니다."),
    "funeral": ("장례예배 기도문 모음 (임종·입관·발인·하관)", ["장례예배 기도문", "임종예배 기도", "입관예배 기도문", "발인예배 기도", "하관예배 기도문"],
                "장례 순서마다 드리는 기도가 다르고, 갑자기 맡게 되는 경우가 많습니다. 유족을 먼저 위로하는 1분 남짓한 기도문을 순서별로 정리했습니다."),
    "dawn-prayer": ("특별새벽기도회 대표기도문 (요일별·공통)", ["특별새벽기도회 기도문", "특새 대표기도", "새벽기도 대표기도문"],
                    "특별새벽기도회 대표기도를 맡으셨나요? 첫날 개회부터 마지막 날까지, 날마다 공동기도제목을 모두 담은 약 4분 분량 기도문입니다."),
    "church-year": ("절기 대표기도문 모음 (부활절·성탄절·추수감사절 등)", ["절기 대표기도문", "부활절 대표기도", "추수감사주일 대표기도문", "성탄절 대표기도"],
                    "해마다 돌아오는 절기 예배의 대표기도문을 연도와 상관없이 쓰실 수 있게 모았습니다."),
    "committee": ("위원회·봉사부서 모임 기도문 38곳", ["부서 모임 기도문", "위원회 개회 기도", "재정위원회 기도", "새가족부 기도"],
                  "재정위원회, 새가족부, 식당봉사부, 차량부처럼 교회 곳곳의 부서 모임을 여는 기도문입니다."),
}


def load(pid):
    f = PRAYERS / f"{pid}.json"
    if not f.exists():
        sys.exit(f"없는 기도문: {pid}")
    return json.loads(f.read_text(encoding="utf-8"))


def url_of(p):
    # build.py 의 상세 주소 규칙: /p/{slug}/
    return f"{BASE}/p/{p['slug']}/"


def chars(text):
    return len(re.sub(r"\s", "", text))


def excerpt(p, limit=260):
    """부르는 말 + 본문 앞부분(약 260자)까지만. 문장 단위로 자른다."""
    out, n = [p["paragraphs"][0]], 0
    for para in p["paragraphs"][1:-1]:
        sents = re.split(r"(?<=[.])\s+", para)
        keep = []
        for s in sents:
            if n + chars(s) > limit:
                break
            keep.append(s)
            n += chars(s)
        if keep:
            out.append(" ".join(keep))
        if n >= limit * 0.8:
            break
    return out


def hashtags(words):
    return " ".join("#" + re.sub(r"\s", "", w) for w in words)


def prayer_post(p):
    when = ""
    if p.get("service_date"):
        d = dt.date.fromisoformat(p["service_date"])
        when = f" ({d.year}.{d.month}.{d.day})"
    title = f"{p['title']}{when} | 전문·인쇄용"
    body = excerpt(p)
    total = chars("\n".join(p["paragraphs"]))
    minutes = round(total / CFG.get("read_cpm", 430))
    lines = [
        f"[제목] {title}", "",
        f"{p.get('occasion', '').split(' · ')[0]} 대표기도를 맡으셨나요?",
        f"{p['context'].split('. ')[0].rstrip('.')}.", "",
        "▶ 기도문 앞부분", "",
        *[f"{x}\n" for x in body],
        "… (이어지는 전문은 아래 링크에서 보실 수 있습니다)", "",
        f"▶ 전문 보기·복사·강단용 큰 글씨 인쇄 (약 {minutes}분 분량)",
        f"{url_of(p)}?{UTM}", "",
        "▶ 쓰실 때 참고하세요",
        *[f"· {t}" for t in p.get("tips", [])],
        "· '담임목사님', '우리 교회'는 섬기는 교회의 호칭으로 바꿔 읽으세요.", "",
        "주일성수(juilsungsu.com)에는 주일·수요·금요예배, 권사회·남전도회 등 부서 모임, 장례·결혼·헌신예배 기도문이 예배 3주 전에 미리 올라옵니다.", "",
        hashtags(["대표기도문", "대표기도", *p.get("tags", [])[:6]]),
    ]
    return title, "\n".join(lines)


def type_post(key):
    sys.path.insert(0, str(ROOT))
    name, kws, lead = TYPE_INFO[key]
    title = f"{name} | 바로 쓰는 대표기도문"
    lines = [f"[제목] {title}", "", lead, "",
             f"▶ 전체 목록 보기", f"{BASE}/type/{key}/?{UTM}", "",
             "▶ 이런 기도문이 있습니다"]
    items = []
    for f in sorted(PRAYERS.glob("*.json")):
        p = json.loads(f.read_text(encoding="utf-8"))
        if p.get("status") not in ("reviewed", "scheduled") or p.get("publish_date", "9999") > dt.date.today().isoformat():
            continue
        if key == "year-end" and (p["worship_type"] in ("연말 총회·송년", "정기총회", "송년 모임") or p["id"] in ("anytime-21", "anytime-22", "anytime-23")):
            items.append(p)
        elif key == "funeral" and p["worship_type"] == "장례":
            items.append(p)
        elif key == "dawn-prayer" and p["worship_type"] == "특별새벽기도회":
            items.append(p)
        elif key == "church-year" and p["worship_type"] == "절기 예배":
            items.append(p)
        elif key == "committee" and p["worship_type"] == "위원회·부서 모임":
            items.append(p)
    for p in items:
        lines.append(f"· {p['title']}")
    lines += ["", "모든 기도문은 복사와 강단용 큰 글씨 인쇄가 됩니다. 교회 이름과 호칭만 바꿔 읽으시면 됩니다.", "",
              hashtags(["대표기도문", "대표기도", *kws])]
    return title, "\n".join(lines)


def save(name, title, text):
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{dt.date.today().isoformat()}_{name}.txt"
    f.write_text(text + "\n", encoding="utf-8")
    print(f"  + {f.relative_to(ROOT)}  —  {title}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=[])
    ap.add_argument("--type", dest="types", nargs="*", default=[])
    ap.add_argument("--week", action="store_true")
    a = ap.parse_args()
    ids = list(a.ids)
    if a.week:
        today = dt.date.today()
        for f in sorted(PRAYERS.glob("main-*.json")):
            p = json.loads(f.read_text(encoding="utf-8"))
            sd = p.get("service_date")
            if sd and 7 <= (dt.date.fromisoformat(sd) - today).days <= 13 and p["id"].endswith(("-am", "-pm")):
                ids.append(p["id"])
    for pid in ids:
        title, text = prayer_post(load(pid))
        save(pid, title, text)
    for key in a.types:
        title, text = type_post(key)
        save(f"type-{key}", title, text)


if __name__ == "__main__":
    main()
