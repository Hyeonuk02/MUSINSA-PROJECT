#!/usr/bin/env python3
"""Phase 4.8 — 선택 미러 VirtualService 렌더링. 레포의 VS는 그대로 두고 stdout으로 낸다(kubectl apply -f -).

/api 라우트마다 `x-impact-scope: 1` 매치 라우트를 앞에 두고 mirror는 그쪽에만 남긴다. 원래 라우트는 legacy로만 보낸다.
선택은 헤더 match로 한다 — mirrorPercentage로 표본을 고르지 않는다(100 그대로). 어느 세션에 헤더를 붙일지는 k6가 impact.json에서 정한다.
사용: .venv/bin/python scoping/render_vs.py | kubectl apply -f -
"""
import copy
import sys
from pathlib import Path

import yaml

from common import ROOT

SOURCE = ROOT / "deploy" / "k8s" / "istio" / "virtualservice-shadow.yaml"
HEADER = "x-impact-scope"


def render(vs: dict) -> dict:
    out = copy.deepcopy(vs)
    routes = []
    for route in out["spec"]["http"]:
        if "mirror" not in route:
            routes.append(route)
            continue
        scoped = copy.deepcopy(route)
        scoped["name"] = f"{route['name']}-scoped"
        for match in scoped["match"]:
            match["headers"] = {HEADER: {"exact": "1"}}
        plain = {k: v for k, v in route.items() if k not in ("mirror", "mirrorPercentage")}
        routes += [scoped, plain]
    out["spec"]["http"] = routes
    return out


def main() -> int:
    print(yaml.safe_dump(render(yaml.safe_load(Path(SOURCE).read_text(encoding="utf-8"))), allow_unicode=True, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
