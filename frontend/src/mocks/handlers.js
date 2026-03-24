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
  http.post(`${API}/sla/profiles`, async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json({
      id: 1,
      created_at: Date.now() / 1000,
      ...body,
    });
  }),
  http.put(`${API}/sla/profiles/:id`, async ({ request, params }) => {
    const body = await request.json();
    return HttpResponse.json({
      id: Number(params.id),
      ...body,
    });
  }),
  http.delete(`${API}/sla/profiles/:id`, ({ params }) =>
    HttpResponse.json({ deleted: true })
  ),
  http.get(`${API}/sla/evaluate/:id`, ({ params }) =>
    HttpResponse.json({
      profile: {
        id: Number(params.id),
        name: 'Test',
        benchmark_ids: [],
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
    })
  ),
];
