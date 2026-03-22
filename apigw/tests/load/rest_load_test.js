import http from 'k6/http';
import { check, sleep } from 'k6';

// Test configuration
export const options = {
  stages: [
    { duration: '30s', target: 50 },  // Ramp-up to 50 concurrent users over 30 seconds
    { duration: '1m', target: 50 },   // Stay at 50 users for 1 minute
    { duration: '30s', target: 0 },   // Ramp-down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(99)<50'], // 99% of requests must complete below 50ms
    http_req_failed: ['rate<0.01'],   // Error rate should be less than 1%
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';

export default function () {
  // Simple health check endpoint or a mocked upstream endpoint
  // Change '/health' to match a route configured in routes.yaml
  const res = http.get(`${BASE_URL}/health`);
  
  check(res, {
    'is status 200': (r) => r.status === 200,
    // Add more checks depending on your endpoint logic
  });
  
  sleep(1); // Wait for 1 second between iterations per VU
}
