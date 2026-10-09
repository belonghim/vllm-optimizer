import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import TunerServingAdvice from './TunerServingAdvice';
import type { ServingAdvice } from '../types';

const ADVICE: ServingAdvice = {
  recommendations: [
    {
      flag: '--tool-call-parser',
      kind: 'required',
      status: 'missing',
      reason: 'template tool_xml — 툴 호출이 텍스트로 반환됨',
      value: 'qwen3_coder',
      current: null,
      arg: '--tool-call-parser=qwen3_coder',
      evidence: 'chat template tool_xml',
    },
    {
      flag: '--reasoning-parser',
      kind: 'required',
      status: 'mismatch',
      reason: '추론 파서 값이 템플릿과 불일치',
      value: 'qwen3',
      current: 'deepseek_r1',
      arg: null,
      evidence: 'template think',
    },
    {
      flag: '--enable-auto-tool-choice',
      kind: 'workload',
      status: 'present',
      reason: '툴 선택 자동화는 워크로드에 따라 결정',
      value: null,
      current: null,
      arg: null,
      evidence: '',
    },
    {
      flag: '--quantization',
      kind: 'avoid',
      status: 'present',
      reason: 'config가 양자화(openvino-int4)를 자동 감지 — 제거 권장',
      value: null,
      current: 'openvino-int4',
      arg: null,
      evidence: 'quantization_config',
    },
  ],
  notes: [
    { level: 'warning', text: 'MTP와 prefix caching 동시 사용 주의' },
    { level: 'info', text: 'hybrid 모델은 max-num-seqs 상한 주의' },
  ],
  add_args: '--tool-call-parser=qwen3_coder',
};

const writeText = vi.fn();

beforeEach(() => {
  writeText.mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText },
  });
});

afterEach(() => {
  Reflect.deleteProperty(navigator, 'clipboard');
  writeText.mockReset();
});

describe('TunerServingAdvice', () => {
  it('renders the advice table with kind labels, statuses and current values', () => {
    render(<TunerServingAdvice advice={ADVICE} />);

    expect(screen.getByRole('table', { name: 'Serving arguments' })).toBeInTheDocument();
    expect(screen.getByTestId('tma-serving-advice')).toBeInTheDocument();
    expect(screen.getAllByText('required')).toHaveLength(2);
    expect(screen.getByText('workload')).toBeInTheDocument();
    expect(screen.getByText('avoid')).toBeInTheDocument();
    expect(screen.getByText('missing')).toBeInTheDocument();
    expect(screen.getByText('mismatch')).toBeInTheDocument();
    expect(screen.getAllByText('present')).toHaveLength(2);

    // ready-to-paste value shown next to the flag; mismatch and avoid expose the current value
    expect(screen.getByText('qwen3_coder')).toBeInTheDocument();
    expect(screen.getByText('current: deepseek_r1')).toBeInTheDocument();
    expect(screen.getByText('current: openvino-int4')).toBeInTheDocument();
    expect(screen.getByText('quantization_config')).toHaveAttribute('title', 'quantization_config');
    expect(screen.getByText('--quantization').closest('tr')).toHaveStyle({
      background: 'var(--red-rgb-alpha-0-05)',
    });
  });

  it('copies add_args to the clipboard and shows a brief Copied state', async () => {
    render(<TunerServingAdvice advice={ADVICE} />);

    expect(screen.getByTestId('tma-add-args')).toHaveTextContent(ADVICE.add_args);
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith('--tool-call-parser=qwen3_coder'));
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument();
  });

  it('does not call the clipboard when it is unavailable', () => {
    Reflect.deleteProperty(navigator, 'clipboard');
    render(<TunerServingAdvice advice={ADVICE} />);

    fireEvent.click(screen.getByRole('button', { name: 'Copy' }));
    expect(writeText).not.toHaveBeenCalled();
  });

  it('renders warning notes as alerts and info notes as muted text', () => {
    render(<TunerServingAdvice advice={ADVICE} />);

    expect(screen.getByRole('alert')).toHaveTextContent('MTP와 prefix caching 동시 사용 주의');
    expect(screen.getByText('hybrid 모델은 max-num-seqs 상한 주의')).toBeInTheDocument();
  });

  it('renders nothing when advice is null, undefined or empty', () => {
    const { container: nullAdvice } = render(<TunerServingAdvice advice={null} />);
    expect(nullAdvice).toBeEmptyDOMElement();

    const { container: undefinedAdvice } = render(<TunerServingAdvice advice={undefined} />);
    expect(undefinedAdvice).toBeEmptyDOMElement();

    const { container: noRecommendations } = render(
      <TunerServingAdvice advice={{ recommendations: [], notes: [], add_args: '' }} />
    );
    expect(noRecommendations).toBeEmptyDOMElement();
  });
});
