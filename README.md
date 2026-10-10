# 대표기도문 사이트

기준 문서: [PRAYER_SITE_SPEC.md](PRAYER_SITE_SPEC.md). 기도문 1편 = `content/prayers/{id}.json` 1파일, `build.py`로 정적 생성.

## 준비

```bash
pip install -r requirements.txt
```

## 매달 하는 일 (SPEC 10장)

```bash
python tools/new_batch.py --from 2026-11-02 --to 2026-11-30 --priority P1   # 뼈대 생성 (status: draft)
#  → Claude Code 세션에서 context·paragraphs·tips·tags·seo_description 작성
python tools/validate.py                 # 오류 0 이 될 때까지 수정
python build.py --serve --drafts         # http://localhost:8000 미리보기 (draft 는 '검수 대기' 띠)
python tools/approve.py <id> ...         # 검수 끝난 글 → reviewed
git commit && git push                   # 발행일 09:00 KST 에 자동 공개
```

- `python build.py --today 2026-11-09` 로 특정 날짜의 공개 상태를 미리 볼 수 있다.
- OG 이미지는 `python tools/make_og.py` 로 다시 만든다 (`config.yaml` 의 site_name 이 바뀌면 재생성).
- 캘린더는 `python tools/make_calendar.py 2027-11-01 2028-10-31 > content/calendar.csv` 로 매년 10월에 갱신.

## 배포

`.github/workflows/publish.yml` — push·매일 08:52 KST·수동 실행 시 `validate → build → dist 브랜치`.
Cloudflare Pages 는 마음체크와 같이 `dist` 브랜치를 바라보게 연결한다 (빌드 명령 없음, 출력 디렉터리 `/`).

## 미정 (config.yaml)

- `site_name`, `base_url` — 자리표시자. 정하면 `tools/make_og.py` 다시 실행.
- `contact.md` 의 이메일.
- `adsense_client` — 비어 있으면 광고 코드가 전혀 들어가지 않는다.
