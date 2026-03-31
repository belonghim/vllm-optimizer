import { http, HttpResponse } from 'msw';

const API = '/api';

export const handlers = [
  http.get(`${API}/config`, () => HttpResponse.json({
    vllm_endpoint: 'http://mock-endpoint:8080',
    vllm_namespace: 'test-ns',
    vllm_is_name: 'test-model',
  })),
  http.get(`${API}/metrics/latest`, () => HttpResponse.json({ tps: 10, kv_cache: 50 })),
  http.post(`${API}/metrics/batch`, () => HttpResponse.json({ results: {} })),
  http.get(`${API}/tuner/status`, () => HttpResponse.json({ running: false, trials_completed: 0 })),
  http.get(`${API}/tuner/trials`, () => HttpResponse.json([])),
  http.get(`${API}/tuner/importance`, () => HttpResponse.json({})),
  http.get(`${API}/benchmark/list`, () => HttpResponse.json([])),
  http.delete(`${API}/benchmark/:id`, ({ params }) =>
    HttpResponse.json({ status: 'deleted', benchmark_id: params.id })
  ),
  http.get(`${API}/vllm-config`, () => HttpResponse.json({
    success: true,
    data: null,
    storageUri: null,
    resources: {
      requests: { cpu: "4", memory: "8Gi" },
      limits: { cpu: "8", memory: "16Gi" },
    },
  })),
  http.get(`${API}/sla/profiles`, () => HttpResponse.json([])),
  http.post(`${API}/tuner/start`, () =>
    HttpResponse.json({ status: 'started' })
  ),
  http.post(`${API}/load_test/run`, () =>
    HttpResponse.json({ status: 'running' })
  ),
  http.post(`${API}/benchmark/save`, () =>
    HttpResponse.json({ success: true })
  ),
  http.post(`${API}/sla/profiles`, async ({ request }) => {
    const body = await request.json() as Record<string, unknown>;
    return HttpResponse.json({
      id: 1,
      name: 'Default SLA',
      thresholds: {
        availability_min: 99.9,
        p95_latency_max_ms: 500,
        error_rate_max_pct: 1.0,
        min_tps: null,
      },
      created_at: Date.now() / 1000,
      ...body,
    }, { status: 201 });
  }),
  http.put(`${API}/sla/profiles/:id`, async ({ request, params }) => {
    const body = await request.json() as Record<string, unknown>;
    return HttpResponse.json({
      id: Number(params.id),
      ...body,
    });
  }),
  http.delete(`${API}/sla/profiles/:id`, () =>
    new HttpResponse(null, { status: 204 })
  ),
  http.post(`${API}/sla/evaluate`, async ({ request }) => {
    const body = await request.json() as { profile_id: number };
    return HttpResponse.json({
      profile: {
        id: body.profile_id,
        name: 'Test',
        thresholds: {
          availability_min: 99,
          p95_latency_max_ms: null,
          error_rate_max_pct: null,
          min_tps: null,
        },
        created_at: 0,
      },
      results: [],
      warnings: [],
    });
  }),
];

export const errorHandlers = [
  http.get(`${API}/config`, () =>
    HttpResponse.json({ detail: 'Internal Server Error' }, { status: 500 })
  ),
  http.post(`${API}/tuner/start`, () =>
    HttpResponse.json({ detail: 'Bad Request' }, { status: 400 })
  ),
];
