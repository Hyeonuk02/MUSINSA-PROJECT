#!/usr/bin/env python3
"""Phase 4.0 — Phase 3 입력 점검(스코핑 전제). 클러스터 접근 없음, 아무것도 고치지 않는다.

점검: 태그(phase3.3-base·phase3.5-v1.4·phase3-done) / 결함 브랜치 fault/F1~F9(로컬·원격, 기준선 위 커밋 1개, 서비스 코드만) /
사다리 커밋 4개 / run 디렉터리(p33·p35-base·v1.1~v1.4·p36-base·F1~F9 × 1..3)의 Evidence·k6-summary·run-meta·dbstate /
run-meta 이미지(order legacy·new, coupon 양쪽) / 판정 파일(verdict·B0·B1 전부, F5 prelabel, F8 maxselects, F1 engine-v1.1) /
corpus(p36 run-meta의 corpus 경로·sha256 = 현재 corpus-v2.1.json).

사용: .venv/bin/python scoping/check_inputs.py   → markdown 표(stdout), 종료 코드 0 = 전부 OK
"""
import hashlib
import json
import subprocess
import sys

from common import ROOT, git

RUNS = ROOT / "runs"
TAGS = {"phase3.3-base": "98c9356", "phase3.5-v1.4": "120b212", "phase3-done": None}
LADDER = {"v1.1": "fd839d6", "v1.2": "fc6e6e2", "v1.3": "c64618f", "v1.4": "120b212"}
FAULT_COMMITS = {"F1": "da92b8e", "F2": "a131294", "F3": "12482f0", "F4": "f83e211", "F5": "1597c73",
                 "F6": "84bd197", "F7": "31363ce", "F8": "60edcda", "F9": "f9f80ce"}
BASE_IMG = "order-app:phase3.3-base"
GROUPS = ([("p33", BASE_IMG), ("p35-base", BASE_IMG)] + [(f"p35-v{v}", f"order-app:phase3.5-v{v}") for v in ("1.1", "1.2", "1.3", "1.4")]
          + [("p36-base", "order-app:phase3.5-v1.4")] + [(f"p36-F{n}", f"order-app:phase3.6-F{n}") for n in range(1, 10)])
EXTRA = {"p36-F5": ["verdict-prelabel.json"], "p36-F8": ["verdict-maxselects.json"], "p36-F1": ["verdict-engine-v1.1.json"]}
BASE_FILES = ["legacy.json", "new.json", "k6-summary.json", "run-meta.json", "dbstate-legacy.json", "dbstate-new.json",
              "verdict.json", "verdict-B0.json", "verdict-B1.json"]


def rev(ref: str) -> str | None:
    try:
        return git("rev-parse", "--short=7", ref).strip()
    except subprocess.CalledProcessError:
        return None


def main() -> int:
    rows = []

    def add(item, ok, detail):
        rows.append((item, ok, detail))

    for tag, want in TAGS.items():
        got = rev(f"{tag}^{{commit}}")
        add(f"tag {tag}", got is not None and (want is None or got == want), got or "없음")
    for name, c in LADDER.items():
        got = rev(c)
        files = git("diff", "--name-only", f"{c}~1..{c}").split()
        add(f"사다리 {name} 커밋 {c}", got == c, f"{len(files)} files (deploy {sum(f.startswith('deploy/') for f in files)})")
    for f, c in FAULT_COMMITS.items():
        local, remote = rev(f"fault/{f}"), rev(f"origin/fault/{f}")
        n = int(git("rev-list", "--count", f"phase3.5-v1.4..fault/{f}").strip()) if local else -1
        files = git("diff", "--name-only", f"phase3.5-v1.4..fault/{f}").split() if local else []
        only_services = all(x.startswith("services/order/src/main/") for x in files)
        add(f"브랜치 fault/{f}", local == c and remote == c and n == 1 and only_services,
            f"local {local} remote {remote} 커밋 {n} 파일 {len(files)} 서비스 코드만 {only_services}")
    corpus_sha = hashlib.sha256((ROOT / "corpus" / "corpus-v2.1.json").read_bytes()).hexdigest()
    for base, new_img in GROUPS:
        for i in (1, 2, 3):
            d = RUNS / f"{base}-{i}"
            need = BASE_FILES + EXTRA.get(base, [])
            missing = [x for x in need if not (d / x).exists()]
            meta = json.loads((d / "run-meta.json").read_text(encoding="utf-8")) if (d / "run-meta.json").exists() else {}
            imgs = meta.get("images", {})
            o, cp = imgs.get("order", {}), imgs.get("coupon", {})
            img_ok = (o.get("legacy", {}).get("image") == BASE_IMG and o.get("new", {}).get("image") == new_img
                      and cp.get("legacy", {}).get("image") == "coupon-app:phase3.3-base"
                      and cp.get("new", {}).get("image") == "coupon-app:phase3.3-base")
            corpus_ok = True
            if base.startswith("p36"):
                c = meta.get("corpus", {})
                corpus_ok = c.get("path") == "corpus/corpus-v2.1.json" and c.get("sha256") == corpus_sha
            dirty = meta.get("git", {}).get("dirty")
            add(f"run {d.name}", not missing and img_ok and corpus_ok and dirty is False,
                f"파일 {len(need) - len(missing)}/{len(need)}{' 없음 ' + ','.join(missing) if missing else ''}, "
                f"order new {o.get('new', {}).get('image')}, 이미지 {'OK' if img_ok else '불일치'}"
                f"{', corpus v2.1 sha OK' if base.startswith('p36') and corpus_ok else ''}{', corpus 불일치' if not corpus_ok else ''}, dirty {dirty}")
    print("| 항목 | 결과 | 내용 |\n|---|---|---|")
    for item, ok, detail in rows:
        print(f"| {item} | {'OK' if ok else '**FAIL**'} | {detail} |")
    bad = sum(1 for _, ok, _ in rows if not ok)
    print(f"\n점검 {len(rows)}건, FAIL {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
