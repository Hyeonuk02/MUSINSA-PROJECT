#!/usr/bin/env python3
"""Jaeger(v2, /api/v3)에서 최근 trace를 가져와 replayRequestId별로 요약한다 (Step 6-3/6-4 확인용).

  python3 deploy/compose/tools/traces.py [--minutes 5]

trace마다 스택, 참여 서비스, span 이름, 서버 span에 기록된 요청 헤더(X-Replay-Request-Id, baggage, Host)를 출력한다.
"""
import argparse
import datetime as dt
import json
import urllib.parse
import urllib.request

JAEGER = "http://localhost:16686"


def fetch(service, minutes):
    now = dt.datetime.now(dt.timezone.utc)
    q = urllib.parse.urlencode({
        "query.service_name": service,
        "query.start_time_min": (now - dt.timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z"),
        "query.start_time_max": now.isoformat().replace("+00:00", "Z"),
        "query.search_depth": 100,
    })
    try:
        with urllib.request.urlopen(f"{JAEGER}/api/v3/traces?{q}") as r:
            return json.load(r)["result"]["resourceSpans"]
    except urllib.error.HTTPError:
        return []


def attrs(xs):
    out = {}
    for a in xs or []:
        v = a["value"]
        out[a["key"]] = v.get("stringValue") or v.get("intValue") or (v.get("arrayValue", {}).get("values") and
                         ",".join(x.get("stringValue", "") for x in v["arrayValue"]["values"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=5)
    args = ap.parse_args()
    traces = {}
    for st in ["legacy", "new"]:
        for svc in ["order", "coupon", "payment"]:
            for rs in fetch(f"{svc}-{st}", args.minutes):
                service = attrs(rs["resource"]["attributes"]).get("service.name")
                for ss in rs["scopeSpans"]:
                    for sp in ss["spans"]:
                        t = traces.setdefault(sp["traceId"], {})
                        t[sp["spanId"]] = {"service": service, "name": sp["name"], "kind": sp.get("kind"),
                                           "start": int(sp["startTimeUnixNano"]), "attrs": attrs(sp.get("attributes"))}
    rows = []
    for tid, spans in traces.items():
        ss = sorted(spans.values(), key=lambda x: x["start"])
        servers = [x for x in ss if x["kind"] == 2]  # SPAN_KIND_SERVER
        replay = next((x["attrs"].get("http.request.header.x-replay-request-id") for x in servers
                       if x["attrs"].get("http.request.header.x-replay-request-id")), None)
        rows.append((ss[0]["start"], tid, replay, ss, servers))
    for _, tid, replay, ss, servers in sorted(rows):
        svcs = sorted({x["service"] for x in ss})
        print(f"trace {tid[:12]}  replay={replay}  spans={len(ss)}  services={svcs}")
        for x in servers:
            a = x["attrs"]
            print(f"   server {x['service']:<15} {x['name']:<32} replay-hdr={a.get('http.request.header.x-replay-request-id')} "
                  f"baggage={a.get('http.request.header.baggage')} host={a.get('http.request.header.host')}")
        kafka = [x for x in ss if "payment-events" in x["name"]]
        for x in kafka:
            print(f"   kafka  {x['service']:<15} {x['name']:<32} kind={x['kind']}")


if __name__ == "__main__":
    main()
