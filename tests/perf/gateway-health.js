import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 8,
  duration: '30s',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
    checks: ['rate>0.99'],
  },
};

const baseUrl = __ENV.BASE_URL || 'http://localhost:8080';

export default function () {
  const response = http.get(`${baseUrl}/health`, {
    tags: { endpoint: 'gateway_health' },
  });

  check(response, {
    'status is 200': (r) => r.status === 200,
    'response has status field': (r) => r.body && r.body.includes('status'),
  });

  sleep(0.2);
}
