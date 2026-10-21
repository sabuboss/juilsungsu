"""수능 D-day 매일 블로그 기도 초안을 만든다.

private/blog/suneung-daily/part*.json (날짜별 짧은 기도, 블로그 전용 원고)를 읽어
날짜별 .txt 초안을 만든다. 각 글 끝에 그 시기에 맞는 주일성수 기도문과
면접각(같은 운영자) 페이지를 연결한다. 결과는 private/ 아래라 커밋되지 않는다.

사용법: python tools/blog_daily.py
"""
import json
import re

from common import ROOT

DIR = ROOT / "private" / "blog" / "suneung-daily"
SITE = "https://juilsungsu.com"
UTM = "utm_source=blog&utm_medium=referral&utm_campaign=suneung_daily"
EXAM_HUB = f"{SITE}/type/exam/?{UTM}"
PRAYER = {  # 시기별로 이어 줄 사이트 기도문
    "before": (f"{SITE}/p/anytime/exam-sunday/?{UTM}", "수능 앞둔 주일, 수험생을 위한 대표기도"),
    "eve": (f"{SITE}/p/anytime/exam-parents-eve/?{UTM}", "수능 전날 밤, 자녀를 위한 부모의 기도"),
    "day": (f"{SITE}/p/anytime/exam-day-intercession/?{UTM}", "수능 당일 중보기도회 기도"),
    "after": (f"{SITE}/p/anytime/exam-after/?{UTM}", "수능을 마친 수험생을 위한 기도"),
    "interview": (f"{SITE}/p/anytime/exam-interview/?{UTM}", "수시 면접·논술을 앞둔 수험생을 위한 기도"),
}
MJGAK_BEFORE = ("https://mjgak.com/suneung/", "수능 시간표·준비물·가채점·성적 발표일 한눈에 보기 (면접각)")
MJGAK_AFTER = [("https://mjgak.com/schedule/", "수능 뒤 대학별 면접 일정 (면접각)"),
               ("https://mjgak.com/practice/", "모의 면접 연습 — 무작위 질문·60초 타이머 (면접각)")]


def stage(dday):
    if dday == "D-day":
        return "day"
    if dday.startswith("D+"):
        return "interview" if int(dday[2:]) >= 3 else "after"
    return "eve" if int(dday[2:]) <= 1 else "before"


def render(e):
    st = stage(e["dday"])
    url, label = PRAYER[st]
    tag_d = re.sub(r"[^0-9A-Za-z+-]", "", e["dday"]).replace("-", "")
    lines = [f"[제목] {e['title']}", "", e["intro"], "", "▶ 오늘의 기도", "", e["prayer"], "",
             e["closing_line"], "", "▶ 함께 드리면 좋은 기도",
             f"· {label}", f"  {url}",
             f"· 수험생·시험 기도문 전체 모음", f"  {EXAM_HUB}", ""]
    if st in ("before", "eve"):
        lines += ["▶ 수능 준비에 도움이 되는 정보", f"· {MJGAK_BEFORE[1]}", f"  {MJGAK_BEFORE[0]}", ""]
    else:
        lines += ["▶ 수능 뒤 면접을 준비한다면"] + [f"· {t}\n  {u}" for u, t in MJGAK_AFTER] + [""]
    lines.append(" ".join(["#수능기도", "#수험생기도", "#수험생을위한기도", "#수능기도문",
                           f"#수능{tag_d}" if e["dday"] != "D-day" else "#수능당일기도",
                           "#수험생부모", "#오늘의기도"]))
    return "\n".join(lines) + "\n"


def main():
    entries = []
    for f in sorted(DIR.glob("part*.json")):
        entries += json.loads(f.read_text(encoding="utf-8"))
    entries.sort(key=lambda e: e["date"])
    for e in entries:
        out = DIR / f"{e['date']}_{e['dday']}.txt"
        out.write_text(render(e), encoding="utf-8")
    print(f"[blog_daily] {len(entries)}편 → {DIR.relative_to(ROOT)}")
    if entries:
        print(f"  {entries[0]['date']} {entries[0]['dday']} ~ {entries[-1]['date']} {entries[-1]['dday']}")


if __name__ == "__main__":
    main()
