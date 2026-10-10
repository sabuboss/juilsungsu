"""calendar.csv 에서 JSON 뼈대를 만든다 (status: draft, paragraphs: []).

사용법:
  python tools/new_batch.py --from 2026-10-19 --to 2026-10-31 [--priority P1] [--ids id1 id2] [--force]
  --from/--to 는 publish_date 기준. 이미 있는 파일은 건너뛴다 (--force 면 덮어씀).
"""
import argparse
import json
import re
import sys

from common import PRAYERS, load_calendar, GROUP_KEYS

# 제목 키워드 -> slug 조각 (영문 소문자·숫자·하이픈만, SPEC 8장)
WORDS = [
    ("추수감사", "thanksgiving-sunday"), ("대림절 첫째", "advent-1"), ("대림절 둘째", "advent-2"),
    ("대림절 셋째", "advent-3"), ("대림절 넷째", "advent-4"), ("성탄 전야", "christmas-eve"), ("성탄절", "christmas"),
    ("송년", "year-end-sunday"), ("송구영신", "new-years-eve"), ("신년", "new-year-sunday"), ("설 명절", "lunar-new-year"),
    ("사순절 첫째", "lent-1"), ("사순절 둘째", "lent-2"), ("사순절 셋째", "lent-3"), ("사순절 넷째", "lent-4"),
    ("사순절 다섯째", "lent-5"), ("종려", "palm-sunday"), ("성금요일", "good-friday"), ("부활", "easter"),
    ("어린이주일", "childrens-sunday"), ("어버이", "parents-sunday"), ("성령강림", "pentecost"), ("스승", "pentecost"),
    ("현충일", "memorial-day"), ("6·25", "korean-war-sunday"), ("맥추", "harvest-sunday"), ("광복", "liberation-sunday"),
    ("추석", "chuseok-sunday"), ("종교개혁", "reformation-sunday"), ("삼일절", "march-1st"),
    # 소모임 절기 특별
    ("수험생", "exam"), ("칸타타", "cantata"), ("발표회", "christmas-festival"), ("교사 헌신", "dedication"),
    ("성경학교", "vbs"), ("수련회", "retreat"),
    # 상황별
    ("임종", "funeral-imjong"), ("입관", "funeral-ipgwan"), ("발인", "funeral-barin"), ("하관", "funeral-hagwan"),
    ("결혼", "wedding"), ("남전도회 헌신", "dedication-namjeondo"), ("여전도회 헌신", "dedication-yeojeondo"),
    ("권사회 헌신", "dedication-gwonsa"), ("안수집사회 헌신", "dedication-anripjipsa"), ("청년부 헌신", "dedication-youngadult"),
    ("교회학교 헌신", "dedication-church-school"), ("창립", "anniversary"), ("임직", "ordination"), ("새가족", "newcomer"),
    ("개업", "business-opening"), ("이사", "housewarming"), ("환우", "sick-visit"), ("돌잔치", "first-birthday"),
    ("추도", "memorial-service"), ("생일", "birthday"), ("제직회", "meeting-jejik"), ("공동의회", "meeting-congregation"),
    ("당회", "meeting-session"), ("파송", "missionary-sending"), ("단기선교", "short-term-mission"), ("세례", "baptism"),
]


def slug_for(r):
    pid, title = r["id"], r["title"]
    kind = pid.split("-")[0]
    word = next((w for k, w in WORDS if k in title), None)
    if kind == "anytime":
        return "anytime/" + (word or pid)
    d = r["service_date"]
    if kind == "main":
        tail = pid.rsplit("-", 1)[1]
        if tail == "wed":
            return f"{d[:7]}-wednesday"
        if tail == "fri":
            return f"{d[:7]}-friday"
        if tail == "pm":
            return f"{d}-" + ((word + "-evening") if word else "sunday-evening")
        return f"{d}-" + (word or "sunday-morning")
    gk = GROUP_KEYS.get(r["group"], re.sub(r"[^a-z0-9-]", "", r["group"].lower()) or "group")
    if pid.endswith("-sp"):
        return f"{d}-{gk}-{word or 'special'}"
    return f"{d[:7]}-group-{gk}"


def length_class(r):
    # 상황별 중 헌신예배·결혼·임직·창립은 본당 구조 3~4분 (SPEC 6.3)
    if r["category"] == "상황별" and (r["worship_type"] in ("헌신예배", "결혼")
                                     or any(k in r["title"] for k in ("임직", "창립"))):
        return "3~4분"
    if r["category"] == "상황별":
        return "1~2분"
    return r["length"]


def skeleton(r):
    return {
        "id": r["id"], "slug": slug_for(r), "status": "draft", "version": 1,
        "category": r["category"], "worship_type": r["worship_type"], "group": r["group"] or None,
        "service_date": r["service_date"] or None, "publish_date": r["publish_date"], "season": r["season"],
        "length_class": length_class(r), "title": r["title"], "seo_title": r["seo_title"],
        "seo_description": "", "tags": [], "context": "", "paragraphs": [], "tips": [],
        "customize": ["'담임목사님' → 교회에서 부르는 호칭(예: OOO 목사님)", "'우리 교회' → 교회 이름"],
        "stats": {"chars_no_space": 0, "chars_with_space": 0, "read_minutes": 0},
        "author": "sabuboss", "note": r["note"] or None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--priority", choices=["P1", "P2"])
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    cal = load_calendar()
    rows = list(cal.values())
    if a.ids:
        rows = [cal[i] for i in a.ids if i in cal]
        missing = set(a.ids) - set(cal)
        if missing:
            print("캘린더에 없는 id:", ", ".join(missing), file=sys.stderr)
    else:
        if not (a.start and a.end):
            ap.error("--from/--to 또는 --ids 가 필요합니다")
        rows = [r for r in rows if a.start <= r["publish_date"] <= a.end]
        if a.priority:
            rows = [r for r in rows if r["priority"] == a.priority]
    made = skipped = 0
    for r in sorted(rows, key=lambda r: (r["publish_date"], r["id"])):
        f = PRAYERS / f"{r['id']}.json"
        if f.exists() and not a.force:
            skipped += 1
            continue
        f.write_text(json.dumps(skeleton(r), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        made += 1
        print(f"  + {r['id']:36s} {r['publish_date']}  {r['title']}")
    print(f"[new_batch] 생성 {made}편, 건너뜀 {skipped}편 (이미 있음)")


if __name__ == "__main__":
    main()
