import '@testing-library/jest-dom';
import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import TunerConfigForm from './TunerConfigForm';

vi.mock('./TunerProgressBar', () => ({ default: () => null }));

const baseConfig = {
  n_trials: 10,
  vllm_endpoint: '',
  max_num_seqs_min: 1,
  max_num_seqs_max: 256,
  gpu_memory_min: 0.5,
  gpu_memory_max: 0.95,
  max_model_len: 8192,
  max_num_batched_tokens_min: 256,
  max_num_batched_tokens_max: 4096,
  eval_concurrency: 10,
  p99_latency_sla_ms: 10000,
  max_tokens: 256,
  eval_requests: 100,
};

const baseProps = {
  config: baseConfig,
  onChange: vi.fn(),
  onSubmit: vi.fn(),
  onStop: vi.fn(),
  onApplyBest: vi.fn(),
  isRunning: false,
  hasBest: false,
  currentConfig: null as Record<string, unknown> | null,
  currentPhase: null,
  trialsCompleted: 0,
  storageUri: null,
  onSaveStorageUri: vi.fn(),
};

describe('TunerConfigForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders without crashing', () => {
    render(<TunerConfigForm {...baseProps} />);
    expect(screen.getByText('▶ Start Tuning')).toBeInTheDocument();
  });

  it('shows em dash spans when currentConfig is null', () => {
    render(<TunerConfigForm {...baseProps} currentConfig={null} />);
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThan(0);
  });

  it('shows inputs instead of dashes when currentConfig is provided', () => {
    const currentConfig = {
      max_num_seqs: 64,
      gpu_memory_utilization: 0.9,
      max_model_len: 4096,
      max_num_batched_tokens: 2048,
    };
    render(<TunerConfigForm {...baseProps} currentConfig={currentConfig} />);
    // only the 5 resource rows have no search range
    expect(screen.queryAllByText('—')).toHaveLength(5);
  });

  it('Apply Current Values button is disabled when editedValues is empty', () => {
    const currentConfig = {
      max_num_seqs: 64,
      gpu_memory_utilization: 0.9,
      max_model_len: 4096,
      max_num_batched_tokens: 2048,
    };
    render(
      <TunerConfigForm
        {...baseProps}
        currentConfig={currentConfig}
        onApplyCurrentValues={vi.fn()}
      />
    );
    expect(screen.getByText('Apply Current Values')).toBeDisabled();
  });

  it('Apply Current Values button enables after changing a currentConfig input', () => {
    const currentConfig = {
      max_num_seqs: 64,
      gpu_memory_utilization: 0.9,
      max_model_len: 4096,
      max_num_batched_tokens: 2048,
    };
    render(
      <TunerConfigForm
        {...baseProps}
        currentConfig={currentConfig}
        onApplyCurrentValues={vi.fn()}
      />
    );
    const btn = screen.getByText('Apply Current Values');
    expect(btn).toBeDisabled();

    // Find the max_num_seqs input (value "64") and change it
    const spinbuttons = screen.getAllByRole('spinbutton') as HTMLInputElement[];
    const maxNumSeqsInput = spinbuttons.find((el) => el.value === '64');
    expect(maxNumSeqsInput).toBeDefined();
    fireEvent.change(maxNumSeqsInput!, { target: { value: '128' } });

    expect(btn).not.toBeDisabled();
  });

  it('does not render Apply Current Values button when onApplyCurrentValues is not provided', () => {
    render(<TunerConfigForm {...baseProps} currentConfig={{ max_num_seqs: 64 }} />);
    expect(screen.queryByText('Apply Current Values')).not.toBeInTheDocument();
  });

  it('resource rows show dash in range column', () => {
    const currentConfig = {
      max_num_seqs: 64,
      gpu_memory_utilization: 0.9,
      max_model_len: 4096,
      max_num_batched_tokens: 2048,
    };
    render(<TunerConfigForm {...baseProps} currentConfig={currentConfig} />);
    expect(screen.queryAllByText('—')).toHaveLength(5);
  });

  it('resource inputs show values from currentResources', () => {
    const currentConfig = {
      max_num_seqs: 64,
      gpu_memory_utilization: 0.9,
      max_model_len: 4096,
      max_num_batched_tokens: 2048,
    };
    const currentResources = {
      requests: { cpu: '4' },
      limits: { memory: '16Gi' },
    };
    render(
      <TunerConfigForm
        {...baseProps}
        currentConfig={currentConfig}
        currentResources={currentResources}
      />
    );
    const cpuReqInput = screen.getByPlaceholderText('e.g. 4, 500m') as HTMLInputElement;
    expect(cpuReqInput.value).toBe('4');
    const memLimInput = screen.getByPlaceholderText('e.g. 16Gi') as HTMLInputElement;
    expect(memLimInput.value).toBe('16Gi');
  });
});

describe('TunerConfigForm service target', () => {
  it('edits concurrent users, SLA and output tokens', () => {
    const onChange = vi.fn();
    render(<TunerConfigForm {...baseProps} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('Concurrent Users'), { target: { value: '32' } });
    fireEvent.change(screen.getByLabelText('P99 Latency SLA (ms)'), { target: { value: '5000' } });
    fireEvent.change(screen.getByLabelText('Output Tokens / Request'), {
      target: { value: '128' },
    });
    expect(onChange).toHaveBeenCalledWith('eval_concurrency', 32);
    expect(onChange).toHaveBeenCalledWith('p99_latency_sla_ms', 5000);
    expect(onChange).toHaveBeenCalledWith('max_tokens', 128);
  });

  it('blocks start when max_model_len exceeds the model limit', () => {
    const { rerender } = render(<TunerConfigForm {...baseProps} maxModelLenLimit={4096} />);
    expect(screen.getByText(/exceeds the model limit/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Start Tuning/ })).toBeDisabled();
    rerender(<TunerConfigForm {...baseProps} maxModelLenLimit={32768} />);
    expect(screen.queryByText(/exceeds the model limit/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Start Tuning/ })).toBeEnabled();
  });
});
