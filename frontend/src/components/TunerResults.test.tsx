import '@testing-library/jest-dom';
import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import TunerResults from './TunerResults';
import * as exportUtils from '../utils/export';

const rechartsState = vi.hoisted(() => ({ scatterData: [] as (unknown[] | undefined)[] }));

vi.mock('recharts', () => ({
  ScatterChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="scatter-chart">{children}</div>
  ),
  Scatter: ({ data }: { data?: unknown[] }) => {
    rechartsState.scatterData.push(data);
    return null;
  },
  CartesianGrid: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => null,
}));

vi.mock('../utils/export', () => ({
  downloadJSON: vi.fn(),
  downloadCSV: vi.fn(),
  trialsToCSV: vi.fn(() => ({ headers: [], rows: [] })),
}));

const baseStatus = {
  running: false,
  trials_completed: 0,
};

const sampleTrial = {
  id: 1,
  tps: 120.5,
  p99_latency: 450,
  score: 0.85,
  params: { max_num_seqs: 64 },
  status: 'complete',
  is_pareto_optimal: false,
};

const failedTrial = {
  id: 2,
  tps: 0,
  p99_latency: 0,
  score: 0,
  params: { max_num_seqs: 256 },
  status: 'failed',
  is_pareto_optimal: false,
  failure: {
    reason: 'crash',
    diagnoses: [
      {
        code: 'mamba_blocks_exceeded',
        title: '--max-num-seqs가 Mamba 캐시 블록 수보다 큼',
        fix: '--max-num-seqs를 96 이하로 낮춤',
      },
      { code: 'crash_loop', title: '컨테이너가 반복 재시작됨', fix: '로그 확인' },
    ],
  },
};

const skippedTrial = {
  id: 3,
  tps: 0,
  p99_latency: 0,
  score: 0,
  params: { max_num_seqs: 512 },
  status: 'skipped',
  is_pareto_optimal: false,
  failure: {
    reason: 'learned_limit',
    diagnoses: [{ code: 'learned_limit', title: '학습된 상한 초과', fix: '탐색 범위를 낮춤' }],
  },
};

describe('TunerResults', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    rechartsState.scatterData = [];
  });

  it('renders nothing notable when trials is empty and no bestParams', () => {
    render(
      <TunerResults
        trials={[]}
        bestParams={undefined}
        status={baseStatus}
        isRunning={false}
        importance={{}}
      />
    );
    expect(screen.queryByText('Export Results')).not.toBeInTheDocument();
    expect(screen.queryByText('Best Parameters Found')).not.toBeInTheDocument();
  });

  it('shows export buttons when trials exist', () => {
    render(
      <TunerResults
        trials={[sampleTrial]}
        bestParams={undefined}
        status={baseStatus}
        isRunning={false}
        importance={{}}
      />
    );
    expect(screen.getByText('Export Results')).toBeInTheDocument();
    expect(screen.getByText('Export JSON')).toBeInTheDocument();
    expect(screen.getByText('Export CSV')).toBeInTheDocument();
  });

  it('renders best parameters section when bestParams is provided', () => {
    const bestParams = {
      tps: 120.5,
      p99_latency: 450,
      params: { max_num_seqs: 64, gpu_memory_utilization: 0.9 },
    };
    render(
      <TunerResults
        trials={[]}
        bestParams={bestParams}
        status={baseStatus}
        isRunning={false}
        importance={{}}
      />
    );
    expect(screen.getByText('Best Parameters Found')).toBeInTheDocument();
    expect(screen.getByText('Best TPS')).toBeInTheDocument();
    expect(screen.getByText('E2E Latency P99')).toBeInTheDocument();
  });

  it('renders best params table with parameter names and values', () => {
    const bestParams = {
      tps: 100,
      p99_latency: 300,
      params: { max_num_seqs: 64, gpu_memory_utilization: 0.9 },
    };
    render(
      <TunerResults
        trials={[]}
        bestParams={bestParams}
        status={baseStatus}
        isRunning={false}
        importance={{}}
      />
    );
    expect(screen.getByText('max_num_seqs')).toBeInTheDocument();
    expect(screen.getByText('64')).toBeInTheDocument();
    expect(screen.getByText('gpu_memory_utilization')).toBeInTheDocument();
    expect(screen.getByText('0.9')).toBeInTheDocument();
  });

  it('renders parameter importance section when importance is non-empty', () => {
    render(
      <TunerResults
        trials={[]}
        bestParams={undefined}
        status={baseStatus}
        isRunning={false}
        importance={{ max_num_seqs: 0.7, gpu_memory_utilization: 0.3 }}
      />
    );
    expect(screen.getByText('Parameter Importance (FAnova)')).toBeInTheDocument();
    expect(screen.getByText('max_num_seqs')).toBeInTheDocument();
  });

  it('does not render parameter importance when importance is empty', () => {
    render(
      <TunerResults
        trials={[]}
        bestParams={undefined}
        status={baseStatus}
        isRunning={false}
        importance={{}}
      />
    );
    expect(screen.queryByText('Parameter Importance (FAnova)')).not.toBeInTheDocument();
  });

  it('calls downloadJSON when Export JSON is clicked', () => {
    render(
      <TunerResults
        trials={[sampleTrial]}
        bestParams={undefined}
        status={baseStatus}
        isRunning={false}
        importance={{}}
      />
    );
    fireEvent.click(screen.getByText('Export JSON'));
    expect(exportUtils.downloadJSON).toHaveBeenCalled();
  });

  it('renders failed and skipped trials with a status badge and diagnosis titles with the first fix', () => {
    render(
      <TunerResults
        trials={[sampleTrial, failedTrial, skippedTrial]}
        bestParams={undefined}
        status={baseStatus}
        isRunning={false}
        importance={{}}
      />
    );

    const panel = screen.getByTestId('tuner-problem-trials');
    expect(panel).toHaveTextContent('실패/건너뜀 트라이얼 (2)');

    const failedRow = screen.getByTestId('problem-trial-2');
    expect(failedRow).toHaveTextContent('failed');
    expect(failedRow).toHaveTextContent('crash');
    expect(failedRow).toHaveTextContent('--max-num-seqs가 Mamba 캐시 블록 수보다 큼');
    expect(failedRow).toHaveTextContent('컨테이너가 반복 재시작됨');
    expect(failedRow).toHaveTextContent('--max-num-seqs를 96 이하로 낮춤');
    expect(failedRow.querySelector('[title="--max-num-seqs를 96 이하로 낮춤"]')).not.toBeNull();

    const skippedRow = screen.getByTestId('problem-trial-3');
    expect(skippedRow).toHaveTextContent('skipped');
    expect(skippedRow).toHaveTextContent('learned_limit');
    expect(skippedRow).toHaveTextContent('학습된 상한 초과');
  });

  it('keeps failed/skipped trials out of the scatter chart data', () => {
    render(
      <TunerResults
        trials={[sampleTrial, failedTrial, skippedTrial]}
        bestParams={undefined}
        status={baseStatus}
        isRunning={false}
        importance={{}}
      />
    );

    const plotted = rechartsState.scatterData.flatMap((data) => data ?? []);
    expect(plotted).toHaveLength(1);
  });

  it('does not render the scatter chart when every trial failed or was skipped', () => {
    render(
      <TunerResults
        trials={[failedTrial, skippedTrial]}
        bestParams={undefined}
        status={baseStatus}
        isRunning={false}
        importance={{}}
      />
    );

    expect(screen.queryByTestId('scatter-chart')).not.toBeInTheDocument();
    expect(screen.getByTestId('tuner-problem-trials')).toBeInTheDocument();
  });
});
