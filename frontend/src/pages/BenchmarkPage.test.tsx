import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import BenchmarkPage from './BenchmarkPage';
import { server } from '../mocks/server';
import { API } from '../constants';

const BENCHMARKS = [
  {
    id: 1,
    name: 'Baseline (default)',
    timestamp: 1_700_000_000,
    config: {
      model: 'Qwen3.5-2B',
      endpoint: 'http://llm-ov',
      total_requests: 200,
      concurrency: 20,
    },
    result: {
      tps: { mean: 180 },
      latency: { p99: 0.52 },
      rps_actual: 12,
      ttft: { mean: 0.095 },
      gpu_utilization_avg: 45,
    },
    metadata: { model_identifier: 'qwen3.5-2b', hardware_type: 'CPU', runtime: 'OpenVINO' },
  },
  {
    id: 2,
    name: 'max_num_seqs=256',
    timestamp: 1_700_003_600,
    config: { model: 'Llama-3.1-8B', endpoint: 'http://llm', total_requests: 200, concurrency: 20 },
    result: {
      tps: { mean: 247 },
      latency: { p99: 0.41 },
      rps_actual: 18,
      ttft: { mean: 0.078 },
      gpu_utilization_avg: 62,
    },
    metadata: { model_identifier: 'llama-3.1-8b-instruct', hardware_type: 'GPU' },
  },
];

function serveBenchmarks() {
  let items = [...BENCHMARKS];
  server.use(
    http.get(`${API}/benchmark/list`, () => HttpResponse.json(items)),
    http.delete(`${API}/benchmark/:id`, ({ params }) => {
      items = items.filter((b) => String(b.id) !== params.id);
      return HttpResponse.json({ status: 'deleted', benchmark_id: params.id });
    })
  );
}

beforeEach(() => {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('BenchmarkPage', () => {
  describe('with saved benchmarks', () => {
    beforeEach(serveBenchmarks);

    it('renders Model ID column header', async () => {
      render(<BenchmarkPage isActive={true} />);
      expect(await screen.findByText('Model ID')).toBeInTheDocument();
    });

    it('renders GPU Eff. column header', async () => {
      render(<BenchmarkPage isActive={true} />);
      expect(await screen.findByText('GPU Eff.')).toBeInTheDocument();
    });

    it('renders benchmark rows from the API', async () => {
      render(<BenchmarkPage isActive={true} />);
      expect(await screen.findByText('Baseline (default)')).toBeInTheDocument();
      expect(screen.getAllByRole('row').length).toBeGreaterThan(1);
    });
  });

  describe('real API mode', () => {
    it('shows empty state message when benchmarks list is empty', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: async () => [],
        })
      );
      render(<BenchmarkPage isActive={true} />);
      await waitFor(() =>
        expect(screen.getByText('Saved load test results will appear here.')).toBeInTheDocument()
      );
    });

    it('shows error banner when fetch fails', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }));
      render(<BenchmarkPage isActive={true} />);
      await waitFor(() =>
        expect(screen.getByText(/Failed to fetch benchmarks/)).toBeInTheDocument()
      );
    });

    it('shows error banner on network failure', async () => {
      vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')));
      render(<BenchmarkPage isActive={true} />);
      await waitFor(() =>
        expect(screen.getByText(/Failed to fetch benchmarks/)).toBeInTheDocument()
      );
    });
  });

  describe('delete', () => {
    beforeEach(serveBenchmarks);

    it('shows delete button for each row', async () => {
      render(<BenchmarkPage isActive={true} />);
      const buttons = await screen.findAllByRole('button', { name: 'Delete benchmark' });
      expect(buttons.length).toBeGreaterThan(0);
    });

    it('removes row after confirmed delete', async () => {
      const user = userEvent.setup();
      render(<BenchmarkPage isActive={true} />);

      const buttons = await screen.findAllByRole('button', { name: 'Delete benchmark' });
      const initialRows = screen.getAllByRole('row').length;
      await user.click(buttons[0]);
      await user.click(screen.getByRole('button', { name: 'Confirm' }));

      await waitFor(() => {
        expect(screen.getAllByRole('row').length).toBe(initialRows - 1);
      });
    });

    it('keeps row when confirm cancelled', async () => {
      const user = userEvent.setup();
      render(<BenchmarkPage isActive={true} />);

      const buttons = await screen.findAllByRole('button', { name: 'Delete benchmark' });
      const initialRows = screen.getAllByRole('row').length;
      await user.click(buttons[0]);
      await user.click(screen.getByRole('button', { name: 'Cancel' }));

      expect(screen.getAllByRole('row').length).toBe(initialRows);
    });
  });
});
