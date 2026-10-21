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


# 대표 이미지 프롬프트 (AI 이미지 도구용). 모든 글이 한 시리즈로 보이도록 같은 화풍을 쓰고 장면만 바꾼다.
# 얼굴이 보이지 않게, 그림 안에 글자를 넣지 않게 한다(한글이 깨지기 쉬움 → 글자는 블로그 편집기에서 얹는다).
STYLE = ("soft watercolor illustration, warm early-morning light, calm and hopeful mood, "
         "muted cream, soft blue and warm beige palette, gentle paper texture, minimal and uncluttered, "
         "no text, no letters, no numbers, no visible faces, square 1:1 composition")
SCENES = {
    "D-29": "a desk calendar on a study desk, a steaming cup of tea, morning sunlight through a window",
    "D-28": "a neatly made bed with a soft bedside lamp, a glass of water, textbooks closed and stacked on the nightstand, starry night window",
    "D-27": "a student's hands resting calmly on an open notebook, a small green sprout in a pot beside them, light breaking through clouds outside",
    "D-26": "a single path through a meadow of different wildflowers, each blooming in its own way",
    "D-25": "a quiet small church interior with morning light on empty wooden pews, a school backpack resting on a pew",
    "D-24": "a parent's hands folded in prayer at a kitchen table, a softly blurred hourglass in the background",
    "D-23": "a warm home-cooked Korean breakfast tray with rice, soup and side dishes on a table by a window",
    "D-22": "a smartphone placed face-down inside a desk drawer, an open textbook and a glowing desk lamp",
    "D-21": "a folded test paper beside a warm mug, a small encouraging note card, autumn leaves outside the window",
    "D-20": "two school backpacks side by side on a bench under a golden ginkgo tree in autumn",
    "D-19": "a study desk at dusk with a soft blanket draped over the chair and a small warm lamp",
    "D-18": "an early-morning bus stop with a lone backpack on the bench and the sun rising over a long road",
    "D-17": "a sharpened pencil and an eraser on a clean desk, a single beam of light on an open page",
    "D-16": "a family dining table with three cups of tea and chairs pulled close together, warm lamp light",
    "D-15": "a paper crane on a windowsill with a soft sunrise behind it",
    "D-14": "a tear-off desk calendar with only a few pages left, morning light on the desk",
    "D-13": "a winding path toward a hilltop under gentle dawn light",
    "D-12": "an analog alarm clock beside a window with a pale blue dawn sky, curtains slightly open",
    "D-11": "a small church bell tower against a clear late-autumn sky, a few ginkgo leaves falling",
    "D-10": "an analog wristwatch with hands next to neatly arranged colored sticky notes on a desk",
    "D-9": "a warm knitted scarf, a thermos of ginger tea and a folded face mask on a wooden table",
    "D-8": "a calm lake reflecting a single tree in soft morning mist",
    "D-7": "seven stepping stones across a quiet stream leading toward the light",
    "D-6": "a student's hands folded in prayer over a closed textbook, soft window light",
    "D-5": "a cozy room on a quiet weekend afternoon, a warm drink and a potted plant by the window",
    "D-4": "a small note card tucked into a lunch box with a warm thermos beside it",
    "D-3": "a student seen from behind standing at a window watching the sunrise",
    "D-2": "neatly laid-out exam items: an analog watch, pencils, an eraser and a clear pencil case on a desk",
    "D-1": "a school gate in late-afternoon autumn light, an empty schoolyard with long soft shadows",
    "D-day": "an early winter morning street, a parent's hand gently on a student's shoulder seen from behind, a school building in the soft distance, breath visible in cold air",
    "D+1": "a warm blanket and a cup of cocoa on a sofa, textbooks stacked and tied with a ribbon, soft evening light",
    "D+2": "a young plant in a clear glass pot showing strong healthy roots, morning light",
    "D+3": "an empty bright interview room with a single chair facing a window, a folder resting on the chair, calm confident mood",
}


def image_block(e):
    scene = SCENES.get(e["dday"], "a quiet study desk by a window at dawn")
    label = "수능 당일" if e["dday"] == "D-day" else (f"수능 {e['dday']}")
    return ["[대표 이미지 프롬프트 — ChatGPT·Gemini·Copilot 등 이미지 생성에 그대로 붙여 넣기]",
            f"{scene}, {STYLE}",
            f"[이미지 위에 블로그 편집기로 얹을 글자] {label} · 오늘의 수험생 기도 — {e['theme'].split('(')[0]}", ""]


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
    lines = [f"[제목] {e['title']}", "", *image_block(e), e["intro"], "", "▶ 오늘의 기도", "", e["prayer"], "",
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
