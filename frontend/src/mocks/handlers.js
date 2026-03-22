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
  http.get(`${API}/vllm-config`, () => HttpResponse.json({ success: true, data: null, storageUri: null })),
];
