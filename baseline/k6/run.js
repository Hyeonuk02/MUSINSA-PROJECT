// Prince Mart 베이스라인 k6 스크립트 (Step 7-2, 7-3)
//
// corpus의 세션을 VU 안에서 순서대로 실행한다. 세션 안은 한 번에 요청 하나.
// 요청마다 legacy·new 두 스택의 Evidence가 expect.evidence 건수에 도달할 때까지 기다린 뒤 다음 요청을 보낸다
// (Kafka consumer 처리까지 포함한 완료 대기, legacy-decision-log L11). 타임아웃이면 그 세션을 degraded로 표시하고
// 남은 요청을 건너뛴다(상태가 어긋나므로). 형식·정책은 hyeonuk-dev Phase 2 계획(2.5)과 맞췄다.
//
// env: RUN_ID(필수), CORPUS(/corpus/corpus-v1.json), BASE_URL(http://nginx), STORE_URL(http://evidence-store:8080),
//      VUS(1), WAIT_TIMEOUT_MS(10000), POLL_MS(50)
// 결과: 요청마다 `{"type":"result",...}` 한 줄(--log-format raw), 세션 끝마다 `{"type":"session",...}`.
import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';

const RUN_ID = __ENV.RUN_ID;
const CORPUS = JSON.parse(open(__ENV.CORPUS || '/corpus/corpus-v1.json'));
const BASE_URL = __ENV.BASE_URL || 'http://nginx';
const STORE_URL = __ENV.STORE_URL || 'http://evidence-store:8080';
const VUS = parseInt(__ENV.VUS || '1', 10);
const WAIT_TIMEOUT_MS = parseInt(__ENV.WAIT_TIMEOUT_MS || '10000', 10);
const POLL_MS = parseInt(__ENV.POLL_MS || '50', 10);
const STACKS = ['legacy', 'new'];

export const options = {
  scenarios: { corpus: { executor: 'per-vu-iterations', vus: VUS, iterations: 1, maxDuration: '30m' } },
  // 본문·헤더에 실행 시점 값을 넣지 않는다. 연결 재사용 설정은 기본값.
};

function substitute(text, vars) {
  return text.replace(/\$\{([A-Za-z_][A-Za-z0-9_]*)\}/g, (_, name) => {
    if (!(name in vars)) throw new Error(`unbound variable ${name}`);
    return String(vars[name]);
  });
}

function evidenceCount(requestId, stack) {
  const res = http.get(`${STORE_URL}/count?runId=${encodeURIComponent(RUN_ID)}&requestId=${requestId}&stack=${stack}`,
    { tags: { name: 'store-count' } });
  return res.status === 200 ? res.json('count') : -1;
}

// 두 스택 모두 기대 건수에 도달할 때까지 기다린다. 반환: {ok, waitedMs, counts}
function waitSettled(requestId, expected) {
  const start = Date.now();
  let counts = {};
  while (true) {
    counts = {};
    for (const st of STACKS) counts[st] = evidenceCount(requestId, st);
    if (STACKS.every((st) => counts[st] >= expected)) return { ok: true, waitedMs: Date.now() - start, counts };
    if (Date.now() - start > WAIT_TIMEOUT_MS) return { ok: false, waitedMs: Date.now() - start, counts };
    sleep(POLL_MS / 1000);
  }
}

export default function () {
  if (!RUN_ID) throw new Error('RUN_ID required');
  const vu = exec.vu.idInTest - 1;
  const mine = CORPUS.sessions.filter((_, i) => i % VUS === vu);

  for (const session of mine) {
    const vars = {};
    let degraded = false;
    let sent = 0;
    for (const req of session.requests) {
      const path = substitute(req.path, vars);
      const body = req.body === undefined ? null : substitute(JSON.stringify(req.body), vars);
      const headers = Object.assign({
        'Content-Type': 'application/json',
        'X-User-Id': String(session.userId),
        'X-Replay-Request-Id': req.id,
        'X-Run-Id': RUN_ID,
        'X-Session-Id': session.id,
        'baggage': `replayRequestId=${req.id},runId=${RUN_ID},sessionId=${session.id}`,
      }, req.headers || {});

      const res = http.request(req.method, `${BASE_URL}${path}`, body, { headers, tags: { name: req.id } });
      sent++;
      const statusOk = check(res, { 'status as expected': (r) => r.status === req.expect.status });
      if (req.capture) {
        const json = res.json();
        for (const [name, field] of Object.entries(req.capture)) vars[name] = json[field];
      }
      const settled = waitSettled(req.id, req.expect.evidence);
      console.log(JSON.stringify({
        type: 'result', runId: RUN_ID, sessionId: session.id, requestId: req.id, method: req.method, path,
        status: res.status, expectedStatus: req.expect.status, statusOk,
        expectedEvidence: req.expect.evidence, evidence: settled.counts, settled: settled.ok, waitedMs: settled.waitedMs,
      }));
      if (!settled.ok) { degraded = true; break; }
    }
    console.log(JSON.stringify({
      type: 'session', runId: RUN_ID, sessionId: session.id, sent, total: session.requests.length, degraded,
    }));
  }
}

export function handleSummary(data) {
  return { '/out/k6-summary.json': JSON.stringify(data, null, 1) };
}
