// Phase 4.9 - Evidence 수집 오버헤드 측정 전용(참고값, 판정 없음). 전체 재생 run.js와 달리 Store를 폴링하지 않는다 —
// Evidence를 끈 쪽에서는 폴링할 것이 없고, 폴링이 응답 지연 측정에 섞이지 않게 한다. 요청 사이 간격은 양쪽 같다(0.1초).
//
// env: RUN_ID 필수, BASE_URL 기본 http://localhost, PACE_S 기본 0.1
// 결과: runs/<RUN_ID>/k6-summary.json — api_latency(게이트웨이 응답 지연, ms)
import http from 'k6/http';
import { sleep } from 'k6';
import { Trend } from 'k6/metrics';

const RUN_ID = __ENV.RUN_ID;
if (!RUN_ID || !/^[A-Za-z0-9._-]{1,128}$/.test(RUN_ID)) {
  throw new Error('RUN_ID env가 필요하다');
}
const BASE_URL = (__ENV.BASE_URL || 'http://localhost').replace(/\/+$/, '');
const PACE_S = parseFloat(__ENV.PACE_S || '0.1');
const corpus = JSON.parse(open('../corpus/corpus-v2.1.json'));
const latency = new Trend('api_latency', true);

http.setResponseCallback(http.expectedStatuses({ min: 200, max: 499 }));

export const options = {
  summaryTrendStats: ['min', 'med', 'avg', 'p(95)', 'max', 'count'],
  scenarios: { replay: { executor: 'per-vu-iterations', vus: 1, iterations: 1, maxDuration: '10m' } },
};

export default function () {
  for (const session of corpus.sessions) {
    for (const req of session.requests) {
      const headers = Object.assign({
        'X-Replay-Request-Id': req.id, 'X-Run-Id': RUN_ID, 'X-Session-Id': session.id, 'X-Replay-Hop-Path': '0',
      }, req.headers || {});
      let body = null;
      if (req.body !== undefined) {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify(req.body);
      }
      const res = http.request(req.method, `${BASE_URL}${req.path}`, body, { headers, tags: { name: `${req.method} ${req.path}` } });
      latency.add(res.timings.duration);
      sleep(PACE_S);
    }
  }
}

export function handleSummary(data) {
  return { [`runs/${RUN_ID}/k6-summary.json`]: JSON.stringify({ runId: RUN_ID, api_latency: data.metrics.api_latency.values }, null, 2) };
}
