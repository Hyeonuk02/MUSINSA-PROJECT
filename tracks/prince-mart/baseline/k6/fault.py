#!/usr/bin/env python3
"""실패 경로 실측: run script를 그대로 돌리면서 장애만 건다 (corpus·시스템 코드·run.py는 바꾸지 않는다).

  python3 baseline/k6/fault.py --run-id fault-f1 --fault kafka-new-disconnect
  python3 baseline/k6/fault.py --run-id fault-f2 --fault order-new-stop

run.py의 출력에서 "<runId>: k6" 줄(= 리셋 완료, k6 시작 직전)을 보면 장애를 건다. 장애는 풀지 않는다.
다음 run의 reset.sh(앱 정지 -> MySQL·Kafka 재생성 -> 앱 시작)가 S0로 되돌리는지가 확인 대상이다.

장애
  kafka-new-disconnect  new 스택 Kafka 브로커를 스택 네트워크에서 끊는다. 컨테이너는 살아 있어 수집(docker exec)은 된다.
                        payment-new의 이벤트 발행과 order-new consumer 처리가 모두 불가 -> new consume Evidence 미도착.
  order-new-stop        order-new를 멈춘다. nginx mirror(/orders)가 new에 도달하지 못한다 -> new order Evidence 미도착.
"""
import argparse
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "compose"

FAULTS = {
    "kafka-new-disconnect": ["docker", "network", "disconnect", "prince-mart_new", "prince-mart-kafka-new-1"],
    "order-new-stop": ["docker", "compose", "stop", "order-new"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--fault", required=True, choices=sorted(FAULTS))
    args = ap.parse_args()

    proc = subprocess.Popen([sys.executable, "-u", str(ROOT / "baseline" / "k6" / "run.py"), "--run-id", args.run_id],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT)
    injected = None
    for line in proc.stdout:
        print(line, end="", flush=True)
        if injected is None and line.startswith(f"[run] {args.run_id}: k6"):
            r = subprocess.run(FAULTS[args.fault], cwd=COMPOSE, capture_output=True, text=True)
            injected = time.strftime("%H:%M:%S")
            print(f"[fault] {args.fault} injected at {injected} rc={r.returncode} {r.stderr.strip()}", flush=True)
    rc = proc.wait()
    print(f"[fault] run.py exit={rc} (장애는 풀지 않음: 다음 run의 reset.sh가 S0로 되돌리는지 확인)", flush=True)
    sys.exit(rc)


if __name__ == "__main__":
    main()
