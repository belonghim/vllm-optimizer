import { render, screen, waitFor } from '@testing-library/react';
import { server } from '../../mocks/server';
import { http, HttpResponse } from 'msw';
import { MockDataProvider } from '../../contexts/MockDataContext';
import { ClusterConfigProvider } from '../../contexts/ClusterConfigContext';
import TunerPage from '../../pages/TunerPage';
import BenchmarkPage from '../../pages/BenchmarkPage';

function TestProviders({ children }) {
  return (
    <MockDataProvider>
      <ClusterConfigProvider>
        {children}
      </ClusterConfigProvider>
    </MockDataProvider>
  );
}

beforeEach(() => {
  localStorage.setItem('vllm-opt-mock-enabled', 'false');
  localStorage.removeItem('vllm-opt-cluster-config');
});

afterEach(() => {
  localStorage.clear();
});

describe('API Integration Tests (MSW)', () => {
  test('TunerPage renders and fetches status/trials/importance via MSW', async () => {
    server.use(
      http.get('/api/tuner/status', () => HttpResponse.json({
        running: false,
        trials_completed: 5,
        best: null,
      })),
      http.get('/api/tuner/trials', () => HttpResponse.json([
        { number: 1, value: 0.8, params: { max_num_seqs: 128 }, state: 'COMPLETE' },
        { number: 2, value: 0.9, params: { max_num_seqs: 256 }, state: 'COMPLETE' },
      ])),
      http.get('/api/tuner/importance', () => HttpResponse.json({
        max_num_seqs: 0.75,
        gpu_memory_utilization: 0.25,
      })),
    );

    render(
      <TestProviders>
        <TunerPage isActive={true} />
      </TestProviders>
    );

    await waitFor(() => {
      expect(screen.getByText(/Start Tuning/i)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getAllByText('max_num_seqs')[0]).toBeInTheDocument();
      expect(screen.getAllByText('gpu_memory_utilization')[0]).toBeInTheDocument();
    });
  });

  test('BenchmarkPage renders empty state when MSW returns empty list', async () => {
    render(
      <TestProviders>
        <BenchmarkPage isActive={true} />
      </TestProviders>
    );

    await waitFor(() => {
       expect(screen.getByText(/Saved load test results will appear here./)).toBeInTheDocument();
    });
  });

  test('MSW handler can be overridden per-test with server.use()', async () => {
    server.use(
      http.get('/api/benchmark/list', () => HttpResponse.json([
        {
          id: 'bench-1',
          name: 'Override Test Benchmark',
          timestamp: Date.now() / 1000,
          config: { model: 'test-model' },
          result: {
            tps: { mean: 42.5 },
            ttft: { mean: 0.1 },
            latency: { p99: 0.5 },
            rps_actual: 10,
          },
        },
      ])),
    );

    render(
      <TestProviders>
        <BenchmarkPage isActive={true} />
      </TestProviders>
    );

    await waitFor(() => {
      expect(screen.getByText('Override Test Benchmark')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText('test-model')).toBeInTheDocument();
    });
  });
});
