"""검수 완료 처리: status 를 reviewed 로 바꾸고 stats 를 재계산한다.

사용법:
  python tools/approve.py main-20261108-am group-202611-gwonsa ...
  python tools/approve.py --all-drafts          # draft 전부
  python tools/approve.py --status hidden <id>  # 다른 상태로
검사(validate.py)에서 오류가 있는 글은 승인하지 않는다.
"""
import argparse
import json
import subprocess
import sys

from common import PRAYERS, ROOT, chars_no_space, read_minutes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--all-drafts", action="store_true")
    ap.add_argument("--status", default="reviewed", choices=["draft", "reviewed", "scheduled", "hidden"])
    ap.add_argument("--skip-validate", action="store_true")
    a = ap.parse_args()

    files = []
    if a.all_drafts:
        for f in sorted(PRAYERS.glob("*.json")):
            if json.loads(f.read_text(encoding="utf-8")).get("status") == "draft":
                files.append(f)
    files += [PRAYERS / f"{i}.json" for i in a.ids]
    if not files:
        ap.error("id 를 주거나 --all-drafts 를 쓰세요")

    if not a.skip_validate and a.status in ("reviewed", "scheduled"):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "validate.py"), *[f.stem for f in files]])
        if r.returncode != 0:
            print("[approve] 검사 오류가 있어 승인하지 않았습니다. 수정 후 다시 실행하세요.")
            sys.exit(1)

    for f in files:
        if not f.exists():
            print("  ! 없음:", f.name)
            continue
        p = json.loads(f.read_text(encoding="utf-8"))
        body = "\n\n".join(p["paragraphs"])
        n = chars_no_space(body)
        p["stats"] = {"chars_no_space": n, "chars_with_space": len(body.replace("\n", "")), "read_minutes": read_minutes(n)}
        p["status"] = a.status
        f.write_text(json.dumps(p, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  ✓ {p['id']:36s} -> {a.status}  ({n}자)")


if __name__ == "__main__":
    main()
