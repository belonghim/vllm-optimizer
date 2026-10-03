import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useTunerLogic } from './useTunerLogic';

const mockConfig = vi.hoisted(() => ({ endpoint: 'http://test-endpoint:8080' }));

vi.mock('../contexts/ClusterConfigContext', () => ({
  useClusterConfig: () => ({
    endpoint: mockConfig.endpoint,
    namespace: 'test-ns',
    inferenceservice: 'test-is',
  }),
}));

vi.mock('./useSSE', () => ({
  useSSE: vi.fn(),
}));

function makeDefaultFetch() {
  return vi.fn((url: string) => {
    if (url.includes('/tuner/status')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ running: false, trials_completed: 0 }),
      });
    }
    if (url.includes('/tuner/trials')) {
      return Promise.resolve({ ok: true, json: async () => [] });
    }
    if (url.includes('/tuner/importance')) {
      return Promise.resolve({ ok: true, json: async () => ({}) });
    }
    if (url.includes('/vllm-config')) {
      return Promise.resolve({ ok: true, json: async () => ({ success: true, data: {} }) });
    }
    if (url.includes('/status/interrupted')) {
      return Promise.resolve({ ok: true, json: async () => ({ interrupted_runs: [] }) });
    }
    if (url.includes('/tuner/start')) {
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    }
    return Promise.resolve({ ok: true, json: async () => ({}) });
  });
}

beforeEach(() => {
  vi.stubGlobal('fetch', makeDefaultFetch());
  mockConfig.endpoint = 'http://test-endpoint:8080';
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('useTunerLogic', () => {
  it('syncs config.vllm_endpoint from ClusterConfig endpoint on mount', async () => {
    const { result } = renderHook(() => useTunerLogic({ isActive: true }));

    await waitFor(() => {
      expect(result.current.config.vllm_endpoint).toBe('http://test-endpoint:8080');
    });
  });

  it('preserves user edits when the endpoint changes', async () => {
    const { result, rerender } = renderHook(() => useTunerLogic({ isActive: true }));

    await waitFor(() => {
      expect(result.current.config.vllm_endpoint).toBe('http://test-endpoint:8080');
    });

    act(() => {
      result.current.handleConfigChange('n_trials', 42);
    });
    expect(result.current.config.n_trials).toBe(42);

    act(() => {
      mockConfig.endpoint = 'http://new-endpoint:8080';
    });
    rerender();

    expect(result.current.config.n_trials).toBe(42);
  });

  it('start() sends POST to /tuner/start with correct payload fields', async () => {
    const { result } = renderHook(() => useTunerLogic({ isActive: true }));

    await act(async () => {
      await result.current.start();
    });

    const fetchMock = vi.mocked(fetch as ReturnType<typeof vi.fn>);
    const startCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/tuner/start'));
    expect(startCall).toBeDefined();
    const body = JSON.parse((startCall![1] as RequestInit).body as string);
    expect(body.vllm_endpoint).toBe('http://test-endpoint:8080');
    expect(body.vllm_namespace).toBe('test-ns');
    expect(body.vllm_is_name).toBe('test-is');
  });

  it('sets error when all tuner API calls fail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/status/interrupted')) {
          return Promise.resolve({ ok: true, json: async () => ({ interrupted_runs: [] }) });
        }
        if (url.includes('/vllm-config')) {
          return Promise.resolve({ ok: true, json: async () => ({ success: true, data: {} }) });
        }
        return Promise.resolve({ ok: false, json: async () => ({}) });
      })
    );

    const { result } = renderHook(() => useTunerLogic({ isActive: true }));

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });
  });
});
