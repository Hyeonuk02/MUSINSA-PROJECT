// Prince Mart 베이스라인 k6 스크립트 (Step 7-2, 7-3)
//
// corpus의 세션을 VU 안에서 순서대로 실행한다. 세션 안은 한 번에 요청 하나.
// 요청마다 legacy·new 두 스택이 각자 "끝났다"고 볼 수 있을 때까지 기다린 뒤 다음 요청을 보낸다(legacy-decision-log L17).
//   스택별 완료 = 진입 Evidence(X-Replay-Request-Id를 받은 http)가 있고, 도착한 Evidence가 선언한 하위 처리
//   (응답을 받은 내부 서비스 Feign 호출 수, 발행한 이벤트 수)만큼 하위 Evidence가 서비스별로 도착함.
//   결함 버전처럼 new가 하위 호출·이벤트를 덜 하면 그만큼 덜 기다린다(고정 건수로 기다리면 결함이 '전달 실패'로 보인다).
//   legacy는 corpus의 expect.evidence와도 대조해 결과에 남긴다(legacyCountOk).
// 타임아웃이면 그 세션을 degraded로 표시하고 남은 요청을 건너뛴다. 형식·정책은 hyeonuk-dev Phase 2 계획(2.5)과 맞췄다.
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

const INTERNAL = { 'ORDER-SERVICE': 'order', 'COUPON-SERVICE': 'coupon', 'PAYMENT-SERVICE': 'payment' };

function evidenceOf(requestId, stack) {
  const res = http.get(`${STORE_URL}/export?runId=${encodeURIComponent(RUN_ID)}&requestId=${requestId}&stack=${stack}`,
    { tags: { name: 'store-export' } });
  return res.status === 200 ? res.json() : [];
}

// 스택 하나의 완료 여부(run.py의 closure()와 같은 규칙).
function closure(evs, requestId) {
  const app = evs.filter((e) => e.kind === 'http' || e.kind === 'consume');
  const isEntry = (e) => e.kind === 'http' && (e.request.headers || {})['x-replay-request-id'] === requestId;
  const declared = { order: 0, coupon: 0, payment: 0, consume: 0 };
  const present = { order: 0, coupon: 0, payment: 0, consume: 0 };
  for (const e of app) {
    for (const o of e.outbound || []) {
      const svc = INTERNAL[(o.url || '').split('/')[2]];
      if (svc && o.status !== null && o.status !== undefined) declared[svc]++;   // 응답을 받은 호출만
    }
    declared.consume += (e.events || []).length;
    if (e.kind === 'consume') present.consume++;
    else if (!isEntry(e)) present[e.service]++;
  }
  const entry = app.some(isEntry);
  const settled = entry && Object.keys(declared).every((k) => present[k] >= declared[k]);
  return { settled, count: app.length };
}

// 두 스택 모두 완료될 때까지 기다린다. 반환: {ok, waitedMs, counts}
function waitSettled(requestId) {
  const start = Date.now();
  let counts = {};
  while (true) {
    counts = {};
    let all = true;
    for (const st of STACKS) {
      const c = closure(evidenceOf(requestId, st), requestId);
      counts[st] = c.count;
      all = all && c.settled;
    }
    if (all) return { ok: true, waitedMs: Date.now() - start, counts };
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
      const settled = waitSettled(req.id);
      console.log(JSON.stringify({
        type: 'result', runId: RUN_ID, sessionId: session.id, requestId: req.id, method: req.method, path,
        status: res.status, expectedStatus: req.expect.status, statusOk,
        expectedEvidence: req.expect.evidence, evidence: settled.counts, settled: settled.ok, waitedMs: settled.waitedMs,
        legacyCountOk: settled.counts.legacy === req.expect.evidence,
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
