import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    recommendations_query: {
      executor: 'ramping-arrival-rate',
      startRate: 5,
      timeUnit: '1s',
      preAllocatedVUs: 20,
      maxVUs: 200,
      stages: [
        { duration: '1m', target: 20 },
        { duration: '3m', target: 120 },
        { duration: '1m', target: 20 },
      ],
    },
    async_events_ingest: {
      executor: 'constant-arrival-rate',
      rate: 40,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 20,
      maxVUs: 120,
      exec: 'ingestAsyncEvents',
      startTime: '20s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<700', 'p(99)<1500'],
    'checks{kind:recommendations}': ['rate>0.99'],
    'checks{kind:events_async}': ['rate>0.99'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:5001';

function makePayload(i) {
  return JSON.stringify({
    user_id: `loadtest_user_${i % 5000}`,
    external_user_id: `lt-ext-${i % 5000}`,
    top_n: 5,
    sources: ['www.e15.cz', 'www.metro.cz'],
    config_id: 'balanced',
    scenario_id: 'default',
    user_reads: [`seed_${i % 20}`],
    allow_rollout: true,
  });
}

export default function () {
  const idx = __VU * 100000 + __ITER;
  const payload = makePayload(idx);
  const headers = {
    'Content-Type': 'application/json',
    'Idempotency-Key': `lt-${idx}`,
  };
  const res = http.post(`${BASE_URL}/api/recommendations/query`, payload, { headers });
  check(res, {
    'status is 200': (r) => r.status === 200,
    'has recommendations': (r) => {
      try {
        const json = r.json();
        return Array.isArray(json.recommendations);
      } catch (_e) {
        return false;
      }
    },
  }, { kind: 'recommendations' });
  sleep(0.1);
}

export function ingestAsyncEvents() {
  const idx = __VU * 100000 + __ITER;
  const runId = `lt-run-${idx}`;
  const events = [];
  for (let i = 0; i < 10; i += 1) {
    events.push({
      event_type: 'impression',
      run_id: runId,
      article_id: `lt-article-${(idx + i) % 100}`,
      user_id: `loadtest_user_${idx % 5000}`,
      external_user_id: `lt-ext-${idx % 5000}`,
      rank_position: i + 1,
      metadata: { source: i % 2 === 0 ? 'www.e15.cz' : 'www.metro.cz' },
    });
  }
  const payload = JSON.stringify({ actor_id: 'k6', events });
  const headers = { 'Content-Type': 'application/json' };
  const res = http.post(`${BASE_URL}/api/events/ingest-async`, payload, { headers });
  check(res, {
    'async ingest accepted': (r) => r.status === 202,
    'job id present': (r) => {
      try {
        return Boolean(r.json()?.job?.job_id);
      } catch (_e) {
        return false;
      }
    },
  }, { kind: 'events_async' });
  sleep(0.05);
}
