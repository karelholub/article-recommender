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
        { duration: '3m', target: 80 },
        { duration: '1m', target: 20 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1200'],
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
  });
  sleep(0.1);
}
