// Phase 2.5 - corpus 재생 + New 완료 폴링
//
// 요청 내용(경로·본문·키·헤더)은 전부 corpus에서 온다. 이 스크립트에는 쓰지 않는다.
// Date.now()·random을 쓰지 않는다 — 같은 corpus는 같은 요청 바이트를 만든다.
// 응답 상태코드로 run을 실패시키지 않는다(404·409도 정상 진행). 판정은 Evidence로 한다. check/threshold 없음.
// corpus의 expectMissing은 corpus/validate.py 전용이라 무시한다.
//
// 요청마다 응답을 받은 뒤 Store에 New Evidence가 도착할 때까지(exists 200) 기다리고 다음 요청을 보낸다.
// 10초 안에 오지 않으면 그 세션은 degraded — 상태가 어긋났으므로 남은 요청은 건너뛰고 다음 세션으로.
//
// env
//   RUN_ID        필수. 없으면 즉시 종료
//   VUS           기본 1. VU i(0부터)는 sessions[j] (j % VUS == i)를 순서대로 맡는다
//   BASE_URL      기본 http://localhost
//   EVIDENCE_URL  기본 http://localhost/_evidence
//
// 결과: runs/<RUN_ID>/k6-summary.json (handleSummary)
//   k6 VU는 메모리를 공유하지 않으므로, 요청 id별 커스텀 metric(sent_/newwait_/status_/skipped_/degraded_)을
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
const HELPER_PREFIXES = ['sent_', 'newwait_', 'status_', 'skipped_', 'degraded_'];

const corpus = JSON.parse(open('../corpus/corpus-v1.json'));

// 요청 id별 helper metric (VU 간 결과 수집용)
const m = {};
for (const session of corpus.sessions) {
  m[`degraded_${session.id}`] = new Counter(`degraded_${session.id}`);
  for (const req of session.requests) {
    m[`sent_${req.id}`] = new Counter(`sent_${req.id}`);
    m[`newwait_${req.id}`] = new Trend(`newwait_${req.id}`, true);
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

function waitForNew(requestId) {
  const url = `${EVIDENCE_URL}/exists?runId=${RUN_ID}&requestId=${requestId}&stack=new`;
  let waitedMs = 0;
  for (;;) {
    const res = http.get(url, { tags: { name: 'evidence_exists' } });
    waitedMs += res.timings.duration;
    if (res.status === 200) {
      return waitedMs;
    }
    if (waitedMs >= POLL_TIMEOUT_MS) {
      return null;
    }
    sleep(POLL_INTERVAL_S);
    waitedMs += POLL_INTERVAL_S * 1000;
  }
}

function runSession(session) {
  for (let i = 0; i < session.requests.length; i++) {
    const req = session.requests[i];
    const headers = Object.assign({
      'X-Replay-Request-Id': req.id,
      'X-Run-Id': RUN_ID,
      'X-Session-Id': session.id,
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
  const status = {};
  const degraded = [];
  for (const session of corpus.sessions) {
    for (const req of session.requests) {
      if (count(data, `sent_${req.id}`) > 0) {
        sent.push(req.id);
        status[req.id] = data.metrics[`status_${req.id}`].values.value;
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
    sent,
    degraded,
    newWaitMs,
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
