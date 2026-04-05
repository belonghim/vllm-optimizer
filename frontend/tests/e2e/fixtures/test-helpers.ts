import { type Page } from '@playwright/test';

export interface VllmConfigMock {
  model_name: string;
  max_num_seqs: string;
  gpu_memory_utilization: string;
  max_model_len: string;
  max_num_batched_tokens: string;
  block_size: string;
  swap_space: string;
}

export interface ClusterTarget {
  namespace: string;
  inferenceService: string;
  crType: string;
  isDefault?: boolean;
}

export interface ComprehensiveMockOptions {
  targets?: ClusterTarget[];
  config?: Record<string, unknown>;
  defaultTargets?: Record<string, unknown>;
  metricsData?: Record<string, unknown>;
  tunerStatus?: Record<string, unknown>;
  vllmConfig?: VllmConfigMock;
  slaProfiles?: unknown[];
  interruptedRuns?: unknown[];
}

const DEFAULT_TARGETS: ClusterTarget[] = [
  { namespace: 'vllm-lab-dev', inferenceService: 'llm-ov', crType: 'inferenceservice', isDefault: true },
];

const DEFAULT_VLLM_CONFIG: VllmConfigMock = {
  model_name: 'test-model',
  max_num_seqs: '128',
  gpu_memory_utilization: '0.85',
  max_model_len: '4096',
  max_num_batched_tokens: '1024',
  block_size: '16',
  swap_space: '2',
};

const DEFAULT_METRICS_DATA = {
  tps: 100,
  rps: 10,
  kv_cache: 50,
  running: 5,
  waiting: 2,
  gpu_util: 60,
  pods: 1,
  pods_ready: 1,
};

const DEFAULT_TUNER_STATUS = {
  running: false,
  trials_completed: 0,
  best: null,
  status: 'idle',
  best_score_history: [],
  pareto_front_size: null,
  last_rollback_trial: null,
};

export async function setupComprehensiveMock(page: Page, options: ComprehensiveMockOptions = {}) {
  const targets = options.targets ?? DEFAULT_TARGETS;
  const defaultTarget = targets.find(t => t.isDefault) ?? targets[0];
  const vllmConfig = options.vllmConfig ?? DEFAULT_VLLM_CONFIG;

  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const { pathname, searchParams } = new URL(req.url());
    const method = req.method();
    const json = (body: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (pathname === '/api/config' && method === 'GET') {
      return json(options.config ?? {
        vllm_endpoint: `http://${defaultTarget.inferenceService}-predictor.${defaultTarget.namespace}.svc.cluster.local:8080`,
        vllm_namespace: defaultTarget.namespace,
        vllm_is_name: defaultTarget.inferenceService,
        cr_type: defaultTarget.crType,
        resolved_model_name: vllmConfig.model_name,
      });
    }

    if (pathname === '/api/config' && method === 'PATCH') {
      return json({ success: true, cr_type: defaultTarget.crType });
    }

    if (pathname === '/api/config/default-targets' && method === 'GET') {
      return json(options.defaultTargets ?? {
        isvc: { name: defaultTarget.inferenceService, namespace: defaultTarget.namespace },
        llmisvc: { name: '', namespace: '' },
        configmap_updated: false,
      });
    }

    if (pathname === '/api/config/default-targets' && method === 'PATCH') {
      return json({ success: true });
    }

    if (pathname === '/api/metrics/latest' && method === 'GET') {
      return json({
        status: 'ready',
        data: { ...DEFAULT_METRICS_DATA, ...options.metricsData },
        hasMonitoringLabel: true,
      });
    }

    if (pathname === '/api/metrics/batch' && method === 'POST') {
      const results: Record<string, unknown> = {};
      for (const target of targets) {
        const crType = target.crType || 'inferenceservice';
        const key = `${target.namespace}/${target.inferenceService}/${crType}`;
        results[key] = {
          status: 'ready',
          data: { ...DEFAULT_METRICS_DATA, ...options.metricsData },
          hasMonitoringLabel: true,
          history: [],
        };
      }
      return json({ results });
    }

    if (pathname === '/api/sla/profiles' && method === 'GET') {
      return json(options.slaProfiles ?? []);
    }

    if (pathname === '/api/tuner/all' && method === 'GET') {
      return json({ status: options.tunerStatus ?? DEFAULT_TUNER_STATUS, trials: [], importance: {} });
    }

    if (pathname === '/api/tuner/status' && method === 'GET') {
      return json({ running: false, trials_completed: 0 });
    }

    if (pathname === '/api/tuner/trials' && method === 'GET') {
      return json([]);
    }

    if (pathname === '/api/tuner/importance' && method === 'GET') {
      return json({});
    }

    if (pathname === '/api/vllm-config' && method === 'GET') {
      return json({ success: true, data: vllmConfig });
    }

    if (pathname === '/api/status/interrupted' && method === 'GET') {
      return json({ interrupted_runs: options.interruptedRuns ?? [] });
    }

    return json({});
  });
}

export async function setupVllmConfigMock(page: Page, configs: VllmConfigMock) {
  await page.route(/\/api\/vllm-config(\?.*)?$/, async (route) => {
    const req = route.request();
    const { pathname } = new URL(req.url());
    const method = req.method();
    const json = (body: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (pathname === '/api/vllm-config' && method === 'GET') {
      return json({ success: true, data: configs });
    }
  });
}

export async function setupVllmConfigMockWithQueryParams(
  page: Page,
  configs: Record<string, VllmConfigMock>
) {
  await page.route(/\/api\/vllm-config(\?.*)?$/, async (route) => {
    const req = route.request();
    const { pathname, searchParams } = new URL(req.url());
    const method = req.method();
    const json = (body: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (pathname === '/api/vllm-config' && method === 'GET') {
      const isName = searchParams.get('is_name') || '';
      const crType = searchParams.get('cr_type') || '';

      if (configs[isName]) {
        return json({ success: true, data: configs[isName] });
      }

      const compoundKey = `${isName}-${crType}`;
      if (configs[compoundKey]) {
        return json({ success: true, data: configs[compoundKey] });
      }

      if (configs['default']) {
        return json({ success: true, data: configs['default'] });
      }

      return json({
        success: true,
        data: {
          model_name: 'default-model',
          max_num_seqs: '64',
          gpu_memory_utilization: '0.80',
          max_model_len: '2048',
          max_num_batched_tokens: '512',
          block_size: '8',
          swap_space: '1',
        },
      });
    }
  });
}

export async function setupV1ModelsMock(page: Page, models: { id: string }[]) {
  await page.route('**/v1/models', async (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        object: 'list',
        data: models.map(m => ({ id: m.id, object: 'model' })),
      }),
    });
  });
}
