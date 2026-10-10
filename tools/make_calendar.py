"""대표기도문 연간 발행 캘린더 생성기.

사용법:  python tools/make_calendar.py 2026-11-01 2027-10-31 > content/calendar.csv
- 본당(3~4분) / 소모임(2분 이내) / 상황별(상시) 기도문 제목을 만들고
- 예배일 기준 20일 전(=3주 전 월요일)을 발행일로 잡는다.
- 이동 절기(부활절·설·추석)는 연도별로 자동 계산한다.
"""
import csv
import sys
from datetime import date, timedelta

from dateutil.easter import easter
from korean_lunar_calendar import KoreanLunarCalendar

ORD = ["첫째", "둘째", "셋째", "넷째", "다섯째"]
WD = "월화수목금토일"
LEAD_DAYS = 20  # 주일 기준 3주 전 월요일

MAIN_LEN, MAIN_CHARS = "3~4분", "850~1080"
GROUP_LEN, GROUP_CHARS = "2분 이내", "300~520"

# key, 이름, 우선순위(P1 핵심 / P2 확장)
GROUPS = [
    ("gwonsa", "권사회", "P1"),
    ("namjeondo", "남전도회", "P1"),
    ("anripjipsa", "장립집사회", "P1"),
    ("choir", "성가대", "P1"),
    ("youngadult", "청년부", "P1"),
    ("youth", "중고등부", "P1"),
    ("elementary", "초등부", "P1"),
    ("kinder", "유치부", "P1"),
    ("infant", "영아부", "P1"),
    ("yeojeondo", "여전도회", "P2"),
    ("teachers", "교회학교 교사회", "P2"),
    ("cell", "구역(속회)예배", "P2"),
]

MONTH_THEME = {
    1: "새해 결단", 2: "사순절 준비", 3: "고난과 부활", 4: "부활의 소망",
    5: "가정의 달", 6: "나라와 민족", 7: "여름 사역·맥추", 8: "광복과 쉼",
    9: "추석·결실", 10: "종교개혁·말씀", 11: "추수감사", 12: "대림과 성탄",
}


def lunar_to_solar(y, m, d):
    c = KoreanLunarCalendar()
    c.setLunarDate(y, m, d, False)
    return date.fromisoformat(c.SolarIsoFormat())


def nth_sunday(y, m, n):
    d = date(y, m, 1)
    d += timedelta(days=(6 - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def last_sunday(y, m):
    d = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def sunday_before(d):
    return d - timedelta(days=(d.weekday() + 1) % 7 or 7)


class MergeDict(dict):
    """같은 주일에 절기가 겹치면 '·'로 합친다 (예: 사순절 셋째 주일·삼일절 기념주일)."""

    def __setitem__(self, k, v):
        if k in self:
            t0, s0, n0 = self[k]
            v = (f"{t0}·{v[0]}", s0, "; ".join(x for x in (n0, v[2]) if x))
        super().__setitem__(k, v)


def special_sundays(y):
    """연도 y의 특별 주일 {날짜: (제목, 절기태그, 비고)}"""
    sp = MergeDict()
    ez = easter(y)
    xmas = date(y, 12, 25)
    advent1 = sunday_before(xmas) - timedelta(weeks=3)
    lent = ez - timedelta(days=46)  # 재의 수요일
    lent_sundays = [lent + timedelta(days=4 + 7 * i) for i in range(6)]
    for i, d in enumerate(lent_sundays[:5]):
        sp[d] = (f"사순절 {ORD[i]} 주일", "사순절", "")
    sp[ez - timedelta(days=7)] = ("종려주일", "고난주간", "고난주간을 여는 주일")
    sp[ez] = ("부활주일", "부활절", "")
    sp[ez + timedelta(days=49)] = ("성령강림주일", "성령강림", "")
    for i in range(4):
        sp[advent1 + timedelta(weeks=i)] = (f"대림절 {ORD[i]} 주일", "대림절", "")
    sp[nth_sunday(y, 11, 3)] = ("추수감사주일", "추수감사", "11월 셋째 주일 기준(교회별 상이)")
    sp[last_sunday(y, 10)] = ("종교개혁주일", "종교개혁", "")
    sp[nth_sunday(y, 7, 1)] = ("맥추감사주일", "맥추감사", "7월 첫째 주일 기준")
    sp[nth_sunday(y, 5, 1)] = ("어린이주일", "가정의달", "")
    sp[nth_sunday(y, 5, 2)] = ("어버이주일", "가정의달", "")
    sp[nth_sunday(y, 5, 3)] = ("스승의 주일", "가정의달", "")
    sp[sunday_before(date(y, 6, 25) + timedelta(days=1))] = (
        f"6·25 전쟁 {y - 1950}주년 기념주일", "나라사랑", "")
    sp[sunday_before(date(y, 8, 15) + timedelta(days=1))] = (
        f"광복 {y - 1945}주년 기념주일", "나라사랑", "")
    sp[sunday_before(date(y, 3, 1) + timedelta(days=1))] = (
        "삼일절 기념주일", "나라사랑", "")
    sp[sunday_before(date(y, 6, 6) + timedelta(days=1))] = (
        "현충일 기념주일", "나라사랑", "호국보훈의 달")
    seol = lunar_to_solar(y, 1, 1)
    sp[sunday_before(seol + timedelta(days=1))] = ("설 명절 주일", "명절", f"설날 {seol}")
    chuseok = lunar_to_solar(y, 8, 15)
    sp[sunday_before(chuseok)] = ("추석 감사주일", "명절", f"추석 {chuseok}")
    sp[date(y, 1, 1) + timedelta(days=(6 - date(y, 1, 1).weekday()) % 7)] = (
        "신년주일", "신년", "")
    sp[last_sunday(y, 12)] = ("송년주일", "송년", "")
    return sp


def build(start, end):
    rows = []
    years = range(start.year, end.year + 1)
    specials = {}
    for y in years:
        for d, v in special_sundays(y).items():
            if d in specials and specials[d][0] != v[0]:
                t0, s0, n0 = specials[d]
                specials[d] = (f"{t0}·{v[0]}", s0, "; ".join(x for x in (n0, v[2]) if x))
            else:
                specials[d] = v

    def add(**kw):
        rows.append(kw)

    d = start + timedelta(days=(6 - start.weekday()) % 7)
    while d <= end:
        nth = (d.day - 1) // 7
        base = f"{d.month}월 {ORD[nth]} 주일"
        title, season, note = specials.get(d, (None, MONTH_THEME[d.month], ""))
        head = f"{title}({base})" if title else base
        add(id=f"main-{d:%Y%m%d}-am", category="본당", worship_type="주일 오전예배",
            group="", service_date=d, title=f"{head} 오전예배 대표기도문",
            seo_title=f"{d.year}년 {title or base} 대표기도문 | 주일 오전예배",
            season=season, length=MAIN_LEN, chars=MAIN_CHARS,
            priority="P1", note=note)
        add(id=f"main-{d:%Y%m%d}-pm", category="본당", worship_type="주일 오후·저녁예배",
            group="", service_date=d, title=f"{head} 오후·저녁예배 대표기도문",
            seo_title=f"{d.year}년 {title or base} 오후예배 대표기도문",
            season=season, length=MAIN_LEN, chars=MAIN_CHARS,
            priority="P2", note=note)
        d += timedelta(weeks=1)

    # 주일 외 본당 특별예배
    for y in years:
        ez = easter(y)
        weekday_specials = [
            (ez - timedelta(days=2), "고난주간 성금요일 예배", "고난주간"),
            (date(y, 12, 24), "성탄 전야 예배", "성탄"),
            (date(y, 12, 25), "성탄절 예배", "성탄"),
            (date(y, 12, 31), "송구영신예배", "송년"),
        ]
        for dd, t, s in weekday_specials:
            if start <= dd <= end:
                add(id=f"main-{dd:%Y%m%d}-sp", category="본당", worship_type=t,
                    group="", service_date=dd, title=f"{dd.year}년 {t} 대표기도문",
                    seo_title=f"{dd.year}년 {t} 대표기도문",
                    season=s, length=MAIN_LEN, chars=MAIN_CHARS, priority="P1", note="")

    # 월별: 수요예배·금요기도회(본당), 소모임
    m = date(start.year, start.month, 1)
    while m <= end:
        first_sun = nth_sunday(m.year, m.month, 1)
        theme = MONTH_THEME[m.month]
        for key, wt in (("wed", "수요예배"), ("fri", "금요기도회")):
            add(id=f"main-{m:%Y%m}-{key}", category="본당", worship_type=wt, group="",
                service_date=first_sun, title=f"{m.year}년 {m.month}월 {wt} 대표기도문",
                seo_title=f"{m.month}월 {wt} 대표기도문 ({m.year})",
                season=theme, length=MAIN_LEN, chars=MAIN_CHARS, priority="P2",
                note="한 달 동안 매주 쓸 수 있게 작성")
        for gi, (key, name, pri) in enumerate(GROUPS):
            add(id=f"group-{m:%Y%m}-{key}", category="소모임", worship_type="월례 모임",
                group=name, service_date=first_sun,
                title=f"{m.year}년 {m.month}월 {name} 대표기도문",
                seo_title=f"{m.month}월 {name} 대표기도문 ({m.year})",
                season=theme, length=GROUP_LEN, chars=GROUP_CHARS, priority=pri,
                note="", spread=gi)
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)

    # 소모임 절기 특별 기도
    for y in years:
        ez = easter(y)
        extra = [
            (ez - timedelta(days=7), "성가대", "choir", "부활절 칸타타 준비 기도", "부활절"),
            (nth_sunday(y, 12, 3), "성가대", "choir", "성탄 칸타타 기도", "성탄"),
            (date(y, 12, 24), "교회학교 연합", "church-school", "성탄 축하 발표회 기도", "성탄"),
            (nth_sunday(y, 7, 3), "교회학교 연합", "church-school", "여름성경학교 개회 기도", "여름사역"),
            (nth_sunday(y, 7, 4), "중고등부", "youth", "여름수련회 출발 기도", "여름사역"),
            (nth_sunday(y, 7, 4), "청년부", "youngadult", "여름수련회 출발 기도", "여름사역"),
            (nth_sunday(y, 11, 2), "중고등부", "youth", "수험생을 위한 기도", "추수감사"),
            (nth_sunday(y, 1, 2), "교회학교 교사회", "teachers", "새해 교사 헌신 기도", "신년"),
        ]
        for dd, gname, key, t, s in extra:
            if start <= dd <= end:
                add(id=f"group-{dd:%Y%m%d}-{key}-sp", category="소모임", worship_type="절기 특별",
                    group=gname, service_date=dd, title=f"{dd.year}년 {gname} {t}",
                    seo_title=f"{gname} {t} ({dd.year})", season=s,
                    length=GROUP_LEN, chars=GROUP_CHARS, priority="P1", note="")

    # 상황별(상시) — 날짜 없음, 매주 목요일 1편씩 순차 발행
    evergreen = [
        ("임종예배 기도", "장례", "P1"), ("입관예배 기도", "장례", "P1"),
        ("발인예배 기도", "장례", "P1"), ("하관예배 기도", "장례", "P1"),
        ("결혼예배 대표기도", "결혼", "P1"), ("남전도회 헌신예배 대표기도", "헌신예배", "P1"),
        ("여전도회 헌신예배 대표기도", "헌신예배", "P1"), ("권사회 헌신예배 대표기도", "헌신예배", "P1"),
        ("안수집사회 헌신예배 대표기도", "헌신예배", "P1"), ("청년부 헌신예배 대표기도", "헌신예배", "P1"),
        ("교회학교 헌신예배 대표기도", "헌신예배", "P1"), ("교회 창립기념주일 대표기도", "교회행사", "P1"),
        ("임직예배 대표기도", "교회행사", "P1"), ("새가족 환영 기도", "교회행사", "P2"),
        ("개업예배 기도", "심방", "P2"), ("이사(입주)예배 기도", "심방", "P2"),
        ("환우 심방 기도", "심방", "P2"), ("돌잔치 감사예배 기도", "심방", "P2"),
        ("추도(기일)예배 기도", "가정예배", "P2"), ("생일 감사 기도", "가정예배", "P2"),
        ("제직회 개회 기도", "회의", "P2"), ("공동의회 개회 기도", "회의", "P2"),
        ("당회 개회 기도", "회의", "P2"), ("선교사 파송예배 기도", "교회행사", "P2"),
        ("단기선교 출발 기도", "교회행사", "P2"), ("세례식·입교식 기도", "교회행사", "P2"),
    ]
    for i, (t, s, pri) in enumerate(evergreen):
        is_main = "헌신예배" in t or "주일" in t or "임직" in t or "결혼" in t
        rows.append(dict(
            id=f"anytime-{i + 1:02d}", category="상황별", worship_type=s, group="",
            service_date="", title=t, seo_title=f"{t} 예문",
            season="상시", length=MAIN_LEN if is_main else GROUP_LEN,
            chars=MAIN_CHARS if is_main else GROUP_CHARS, priority=pri, note="",
            publish_override=start - timedelta(days=17) + timedelta(weeks=i)))

    for r in rows:
        if r.get("publish_override"):
            pub = r["publish_override"]
        else:
            pub = r["service_date"] - timedelta(days=LEAD_DAYS) + timedelta(days=r.get("spread", 0) % 6)
        r["publish_date"] = pub
        r["weekday"] = WD[r["service_date"].weekday()] if r["service_date"] else ""
    rows.sort(key=lambda r: (r["publish_date"], r["service_date"] or date.max, r["id"]))
    return rows


FIELDS = ["id", "category", "worship_type", "group", "service_date", "weekday",
          "publish_date", "season", "title", "seo_title", "length", "chars",
          "priority", "note"]

if __name__ == "__main__":
    s, e = (date.fromisoformat(a) for a in sys.argv[1:3])
    sys.stdout.reconfigure(encoding="utf-8-sig", newline="")  # 엑셀에서 한글 깨짐 방지
    w = csv.DictWriter(sys.stdout, FIELDS, extrasaction="ignore")
    w.writeheader()
    for r in build(s, e):
        w.writerow(r)
