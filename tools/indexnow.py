"""IndexNow 로 새로 공개된 페이지를 검색엔진에 바로 알린다 (빙·네이버·얀덱스 등 참여 엔진).

GitHub Actions 배포 뒤에 실행한다. dist/sitemap.xml 에서 lastmod 가 최근 N일 안인
기도문 주소와 홈을 모아 보낸다. 실패해도 배포에는 영향이 없도록 종료코드 0.

사용법: python tools/indexnow.py [--since 1] [--all]
"""
import argparse
import datetime as dt
import json
import re
import urllib.request

import yaml

from common import ROOT

CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
ENDPOINTS = ["https://api.indexnow.org/indexnow", "https://searchadvisor.naver.com/indexnow"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=1, help="최근 며칠 안에 공개된 글")
    ap.add_argument("--all", action="store_true", help="사이트맵 전체")
    a = ap.parse_args()
    key = CFG.get("indexnow_key")
    base = CFG["base_url"].rstrip("/")
    if not key:
        print("[indexnow] 키 없음 — 건너뜀")
        return
    sm = (ROOT / "dist" / "sitemap.xml").read_text(encoding="utf-8")
    pairs = re.findall(r"<loc>([^<]+)</loc><lastmod>([^<]+)</lastmod>", sm)
    today = dt.date.today()
    cut = (today - dt.timedelta(days=a.since)).isoformat()
    if a.all:
        urls = [u for u, _ in pairs]
    else:
        urls = [u for u, lm in pairs if "/p/" in u and lm >= cut]
        if urls:
            urls.insert(0, base + "/")
    if not urls:
        print("[indexnow] 새로 알릴 주소 없음")
        return
    body = json.dumps({"host": base.split("//")[1], "key": key, "keyLocation": f"{base}/{key}.txt",
                       "urlList": urls[:10000]}).encode()
    for ep in ENDPOINTS:
        req = urllib.request.Request(ep, data=body, headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                print(f"[indexnow] {ep} → {r.status} ({len(urls)}개)")
        except Exception as e:  # 202/200 외 응답이나 네트워크 오류도 배포를 막지 않는다
            print(f"[indexnow] {ep} → {getattr(e, 'code', e)}")


if __name__ == "__main__":
    main()
