// Phase 2.5 - corpus 재생 + New 완료 폴링
//
// 요청 내용(경로·본문·키·헤더)은 전부 corpus에서 온다. 이 스크립트에는 쓰지 않는다.
// 요청 본문·헤더에 실행 시점 값(Date.now()·random)을 넣지 않는다 — 같은 corpus는 같은 요청 바이트를 만든다.
// (대기 시간 측정에는 벽시계를 쓴다. 금지 규칙은 요청에 들어가는 값에 대한 것이다.)
// 응답 상태코드로 run을 실패시키지 않는다(404·409도 정상 진행). 판정은 Evidence로 한다. check/threshold 없음.
// 4xx는 corpus의 의도된 경로(없는 키 404, PAID 후 cancel 409)와 exists 폴링의 404라 http_req_failed에서 뺀다(200~499 정상).
// corpus의 expectMissing은 corpus/validate.py 전용이라 무시한다.
//
// 요청마다 응답을 받은 뒤 Store에 New Evidence가 도착할 때까지(exists 200) 기다리고 다음 요청을 보낸다.
// v2(Phase 3.2): corpus의 settle 홉(서비스 간 호출로 생기는 내부 Evidence)도 legacy·new 양쪽에서 도착을 기다린다 —
// Legacy 쪽 내부 Evidence도 비동기라 New만 보면 export 전에 빠질 수 있다(D19).
// 10초 안에 오지 않으면 그 세션은 degraded — 상태가 어긋났으므로 남은 요청은 건너뛰고 다음 세션으로.
//
// env
//   RUN_ID        필수. 없으면 즉시 종료
//   CORPUS        기본 corpus-v2.json (corpus/ 아래 파일명)
//   VUS           기본 1. VU i(0부터)는 sessions[j] (j % VUS == i)를 순서대로 맡는다
//   BASE_URL      기본 http://localhost
//   EVIDENCE_URL  기본 http://localhost/_evidence
//
// 결과: runs/<RUN_ID>/k6-summary.json (handleSummary)
//   k6 VU는 메모리를 공유하지 않으므로, 요청 id별 커스텀 metric(sent_/newwait_/settlewait_/status_/skipped_/degraded_)을
//   init 단계에서 corpus로 만들어 두고 handleSummary에서 모아 sent·degraded·newWaitMs로 재구성한다.
import http from 'k6/http';
import exec from 'k6/execution';
import { sleep } from 'k6';
import { Counter, Gauge, Trend } from 'k6/metrics';

const RUN_ID = __ENV.RUN_ID;
if (!RUN_ID || !/^[A-Za-z0-9._-]{1,128}$/.test(RUN_ID)) {
  throw new Error('RUN_ID env가 필요하다 ([A-Za-z0-9._-]{1,128})');
}
const VUS = parseInt(__ENV.VUS || '1', 10);
const BASE_URL = (__ENV.BASE_URL || 'http://localhost').replace(/\/+$/, '');
const EVIDENCE_URL = (__ENV.EVIDENCE_URL || 'http://localhost/_evidence').replace(/\/+$/, '');

const POLL_INTERVAL_S = 0.1;
const POLL_TIMEOUT_MS = 10000;
const HELPER_PREFIXES = ['sent_', 'newwait_', 'settlewait_', 'status_', 'skipped_', 'degraded_'];

const CORPUS = __ENV.CORPUS || 'corpus-v2.json';
if (!/^corpus-v[0-9]+\.json$/.test(CORPUS)) {
  throw new Error('CORPUS는 corpus/ 아래 corpus-v<N>.json');
}
const corpus = JSON.parse(open(`../corpus/${CORPUS}`));

http.setResponseCallback(http.expectedStatuses({ min: 200, max: 499 }));

// 요청 id별 helper metric (VU 간 결과 수집용)
const m = {};
for (const session of corpus.sessions) {
  m[`degraded_${session.id}`] = new Counter(`degraded_${session.id}`);
  for (const req of session.requests) {
    m[`sent_${req.id}`] = new Counter(`sent_${req.id}`);
    m[`newwait_${req.id}`] = new Trend(`newwait_${req.id}`, true);
    m[`settlewait_${req.id}`] = new Trend(`settlewait_${req.id}`, true);
    m[`status_${req.id}`] = new Gauge(`status_${req.id}`);
    m[`skipped_${req.id}`] = new Counter(`skipped_${req.id}`);
  }
}

export const options = {
  // Trend 요약에 count를 넣어 newwait_<id>에 표본이 있었는지 판단한다(k6 기본 요약에는 count가 없다)
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'count'],
  scenarios: {
    replay: { executor: 'per-vu-iterations', vus: VUS, iterations: 1, maxDuration: '10m' },
  },
};

// 응답 수신 직후부터 Store에서 New Evidence가 보일 때까지의 벽시계 시간(ms). 타임아웃이면 null.
// k6 관점의 대기이며 폴링 해상도 100ms. 미러 지연 자체는 2.7에서 Evidence timing
// (new.completedAt − legacy.completedAt)으로 계산한다.
function waitForNew(requestId) {
  return waitFor(requestId, 'new', '0', Date.now());
}

// (stack, hopPath) Evidence가 Store에 보일 때까지. started 기준 벽시계 ms, 타임아웃이면 null.
function waitFor(requestId, stack, hopPath, started) {
  const url = `${EVIDENCE_URL}/exists?runId=${RUN_ID}&requestId=${requestId}&stack=${stack}&hopPath=${hopPath}`;
  for (;;) {
    const res = http.get(url, { tags: { name: 'evidence_exists' } });
    const waitedMs = Date.now() - started;
    if (res.status === 200) {
      return waitedMs;
    }
    if (waitedMs >= POLL_TIMEOUT_MS) {
      return null;
    }
    sleep(POLL_INTERVAL_S);
  }
}

function runSession(session) {
  for (let i = 0; i < session.requests.length; i++) {
    const req = session.requests[i];
    const headers = Object.assign({
      'X-Replay-Request-Id': req.id,
      'X-Run-Id': RUN_ID,
      'X-Session-Id': session.id,
      'X-Replay-Hop-Path': '0',  // 진입 홉. 서비스가 나가는 호출의 자식 hopPath를 계산한다(D15)
    }, req.headers || {});
    let body = null;
    if (req.body !== undefined) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(req.body);
    }
    const res = http.request(req.method, `${BASE_URL}${req.path}`, body, {
      headers,
      tags: { name: `${req.method} ${req.path}` },
    });
    m[`sent_${req.id}`].add(1);
    m[`status_${req.id}`].add(res.status);

    const waited = waitForNew(req.id);
    if (waited === null) {
      console.warn(`DEGRADED session=${session.id} request=${req.id}: new Evidence가 ${POLL_TIMEOUT_MS}ms 안에 오지 않음`);
      m[`degraded_${session.id}`].add(1);
      for (const skipped of session.requests.slice(i + 1)) {
        m[`skipped_${skipped.id}`].add(1);
      }
      return;
    }
    m[`newwait_${req.id}`].add(waited);

    // settle: 선언된 내부 홉을 양쪽 스택에서. 시작 시각은 응답 수신 직후(진입 폴링과 같은 기준)
    if (req.settle) {
      const started = Date.now() - waited;
      let settleMax = 0;
      for (const s of req.settle) {
        for (const stack of ['legacy', 'new']) {
          const w = waitFor(req.id, stack, s.hop, started);
          if (w === null) {
            console.warn(`DEGRADED session=${session.id} request=${req.id}: settle ${stack}/${s.hop}(${s.service}) Evidence가 ${POLL_TIMEOUT_MS}ms 안에 오지 않음`);
            m[`degraded_${session.id}`].add(1);
            for (const skipped of session.requests.slice(i + 1)) {
              m[`skipped_${skipped.id}`].add(1);
            }
            return;
          }
          settleMax = Math.max(settleMax, w);
        }
      }
      m[`settlewait_${req.id}`].add(settleMax);
    }
  }
}

export default function () {
  const vuIndex = exec.vu.idInTest - 1;
  corpus.sessions.forEach((session, j) => {
    if (j % VUS === vuIndex) {
      runSession(session);
    }
  });
}

function count(data, name) {
  const metric = data.metrics[name];
  return metric ? metric.values.count : 0;
}

export function handleSummary(data) {
  const sent = [];
  const newWaitMs = {};
  const settleWaitMs = {};
  const status = {};
  const degraded = [];
  for (const session of corpus.sessions) {
    for (const req of session.requests) {
      if (count(data, `sent_${req.id}`) > 0) {
        sent.push(req.id);
        status[req.id] = data.metrics[`status_${req.id}`].values.value;
      }
      const sw = data.metrics[`settlewait_${req.id}`];
      if (sw && sw.values.count > 0) {
        settleWaitMs[req.id] = Math.round(sw.values.max * 10) / 10;
      }
      const wait = data.metrics[`newwait_${req.id}`];
      if (wait && wait.values.count > 0) {
        newWaitMs[req.id] = Math.round(wait.values.max * 10) / 10;
      }
    }
    if (count(data, `degraded_${session.id}`) > 0) {
      degraded.push({
        session: session.id,
        skipped: session.requests.filter((r) => count(data, `skipped_${r.id}`) > 0).map((r) => r.id),
      });
    }
  }
  const metrics = {};
  for (const [name, metric] of Object.entries(data.metrics)) {
    if (!HELPER_PREFIXES.some((p) => name.startsWith(p))) {
      metrics[name] = metric;
    }
  }
  const waits = Object.values(newWaitMs).sort((a, b) => a - b);
  const summary = {
    runId: RUN_ID,
    corpusVersion: corpus.version,
    vus: VUS,
    baseUrl: BASE_URL,
    evidenceUrl: EVIDENCE_URL,
    // sent: 보낸 요청 id. 세션 안은 보낸 순서, 세션 사이는 corpus 순서(VUS>1이면 세션들이 병렬로 진행된다)
    // newWaitMs: 응답 수신 직후부터 Store exists(stack=new) 200까지의 벽시계 대기. k6 관점의 대기이며 폴링 해상도 100ms.
    //   미러 지연 자체는 2.7에서 Evidence timing(new.completedAt − legacy.completedAt)으로 계산한다
    newWaitMsNote: 'k6 관점의 대기(응답 수신 → exists 200, 벽시계), 폴링 해상도 100ms. 미러 지연 자체는 2.7에서 Evidence timing(new.completedAt − legacy.completedAt)으로 계산',
    sent,
    degraded,
    newWaitMs,
    settleWaitMs,
    settleWaitMsNote: '응답 수신 → 선언된 settle 홉 Evidence가 legacy·new 모두 보일 때까지(벽시계, 최대값)',
    status,
    metrics,
    state: data.state,
  };
  const line = (label, v) => `  ${label.padEnd(18)} ${v}\n`;
  const text = '\n' +
    line('runId', RUN_ID) + line('corpus', corpus.version) + line('vus', VUS) +
    line('sent', `${sent.length} (${sent.join(' ')})`) +
    line('degraded', degraded.length === 0 ? 0 : JSON.stringify(degraded)) +
    line('newWaitMs', waits.length ? `min=${waits[0]} median=${waits[Math.floor((waits.length - 1) / 2)]} max=${waits[waits.length - 1]}` : '-') +
    line('iteration_duration', JSON.stringify(data.metrics.iteration_duration ? data.metrics.iteration_duration.values : {})) +
    line('summary', `runs/${RUN_ID}/k6-summary.json`);
  return {
    stdout: text,
    [`runs/${RUN_ID}/k6-summary.json`]: JSON.stringify(summary, null, 2),
  };
}
