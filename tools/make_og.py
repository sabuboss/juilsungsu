"""OG 이미지 5종 생성 → static/og/*.png  (1200×630). 로컬에서 한 번 만들어 커밋한다.

사용법: python tools/make_og.py
글꼴은 Windows 맑은 고딕(C:/Windows/Fonts/malgunbd.ttf) 또는 Noto Sans KR 을 찾는다.
"""
import pathlib
import sys

import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "og"
cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
NAME = cfg["site_name"]

FONTS = ["C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/NotoSansKR-Medium.ttf",
         "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc", "/System/Library/Fonts/AppleSDGothicNeo.ttc"]


def font(size):
    for f in FONTS:
        if pathlib.Path(f).exists():
            return ImageFont.truetype(f, size)
    print("한글 글꼴을 찾지 못했습니다", file=sys.stderr)
    return ImageFont.load_default()


# key, 큰 제목, 작은 설명, 바탕색, 강조색
KINDS = [
    ("home", "대표기도문", "주일예배 · 소모임 · 상황별", "#faf7f0", "#2f6b4f"),
    ("main", "주일예배 대표기도문", "3~4분 · 복사 · 인쇄", "#faf7f0", "#2f6b4f"),
    ("group", "소모임 대표기도문", "권사회 · 남전도회 · 성가대 · 교회학교", "#faf7f0", "#5b3f8f"),
    ("anytime", "상황별 기도문", "장례 · 결혼 · 헌신예배 · 심방 · 회의", "#faf7f0", "#8a6a1a"),
    ("season", "절기 대표기도문", "추수감사 · 대림절 · 성탄 · 사순절 · 부활절", "#faf7f0", "#a63a2e"),
]


def make(key, title, sub, bg, ac):
    im = Image.new("RGB", (1200, 630), bg)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 28, 630], fill=ac)
    d.text((90, 150), NAME, font=font(40), fill=ac)
    d.text((90, 230), title, font=font(84), fill="#1d2a44")
    d.text((90, 370), sub, font=font(40), fill="#5f6b80")
    d.text((90, 520), cfg["base_url"].replace("https://", ""), font=font(30), fill="#9aa3b2")
    OUT.mkdir(parents=True, exist_ok=True)
    im.save(OUT / f"{key}.png", optimize=True)
    print("wrote", OUT / f"{key}.png")


for k in KINDS:
    make(*k)
