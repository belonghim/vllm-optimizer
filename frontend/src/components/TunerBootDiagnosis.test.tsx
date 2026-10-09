import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TunerBootDiagnosis from './TunerBootDiagnosis';
import { server } from '../mocks/server';
import { API } from '../constants';

const RESPONSE = {
  target: { namespace: 'serving1', name: 'qwen', cr_type: 'llminferenceservice' },
  available: true,
  pod: {
    pod: 'qwen-kserve-0',
    container: 'main',
    phase: 'Running',
    restarts: 3,
    state: 'CrashLoopBackOff',
    last_terminated_reason: 'OOMKilled',
    exit_code: 137,
  },
  diagnoses: [
    {
      code: 'mamba_blocks_exceeded',
      title: '--max-num-seqs가 Mamba 캐시 블록 수보다 큼',
      cause: 'hybrid 모델은 디코드 시퀀스마다 Mamba 캐시 블록 1개가 필요',
      fix: '--max-num-seqs를 96 이하로 낮춤',
      evidence: 'ValueError: max_num_seqs (256) exceeds available Mamba cache blocks (96)',
      fix_args: ['--max-num-seqs', '--gpu-memory-utilization'],
      suggested_value: 96,
    },
  ],
  log_tail: 'ValueError: max_num_seqs (256) exceeds available Mamba cache blocks (96)',
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

describe('TunerBootDiagnosis', () => {
  it('fetches only on the manual 진단 click and renders pod state, diagnoses and copyable fix args', async () => {
    let requestedUrl = '';
    let calls = 0;
    server.use(
      http.get(`${API}/tuner/boot-diagnosis`, ({ request }) => {
        calls += 1;
        requestedUrl = request.url;
        return HttpResponse.json(RESPONSE);
      })
    );
    render(
      <TunerBootDiagnosis
        isActive={true}
        targetOverride={{
          namespace: 'serving1',
          inferenceService: 'qwen',
          crType: 'llminferenceservice',
        }}
      />
    );

    expect(calls).toBe(0);
    fireEvent.click(screen.getByTestId('tbd-run'));

    expect(await screen.findByTestId('tbd-pod')).toBeInTheDocument();
    expect(calls).toBe(1);
    expect(requestedUrl).toContain('namespace=serving1');
    expect(requestedUrl).toContain('is_name=qwen');
    expect(requestedUrl).toContain('cr_type=llminferenceservice');

    expect(screen.getByTestId('tbd-availability')).toHaveTextContent('파드 발견');
    expect(screen.getByText('qwen-kserve-0')).toBeInTheDocument();
    expect(screen.getByText('phase Running')).toBeInTheDocument();
    expect(screen.getByText('state CrashLoopBackOff')).toBeInTheDocument();
    expect(screen.getByText('재시작 3')).toBeInTheDocument();
    expect(screen.getByText('last OOMKilled')).toBeInTheDocument();
    expect(screen.getByText('exit 137')).toBeInTheDocument();

    const diagnosis = screen.getByTestId('tbd-diagnosis-mamba_blocks_exceeded');
    expect(diagnosis).toHaveTextContent('--max-num-seqs가 Mamba 캐시 블록 수보다 큼');
    expect(diagnosis).toHaveTextContent(
      'hybrid 모델은 디코드 시퀀스마다 Mamba 캐시 블록 1개가 필요'
    );
    expect(diagnosis).toHaveTextContent('해결: --max-num-seqs를 96 이하로 낮춤');
    expect(diagnosis).toHaveTextContent('exceeds available Mamba cache blocks');

    fireEvent.click(screen.getByRole('button', { name: '--max-num-seqs' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('--max-num-seqs'));
    expect(
      await screen.findByRole('button', { name: '--max-num-seqs 복사됨' })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('tbd-log-toggle'));
    expect(screen.getByTestId('tbd-log-tail')).toHaveTextContent(
      'exceeds available Mamba cache blocks'
    );
    fireEvent.click(screen.getByTestId('tbd-log-toggle'));
    expect(screen.queryByTestId('tbd-log-tail')).not.toBeInTheDocument();
  });

  it('omits target query params when no target override is selected', async () => {
    let requestedUrl = '';
    server.use(
      http.get(`${API}/tuner/boot-diagnosis`, ({ request }) => {
        requestedUrl = request.url;
        return HttpResponse.json(RESPONSE);
      })
    );
    render(<TunerBootDiagnosis isActive={true} />);

    fireEvent.click(screen.getByTestId('tbd-run'));
    await screen.findByTestId('tbd-pod');

    expect(requestedUrl).not.toContain('namespace=');
    expect(requestedUrl).not.toContain('is_name=');
    expect(requestedUrl).not.toContain('cr_type=');
  });

  it('shows 파드를 찾지 못함 when the target has no pod', async () => {
    server.use(
      http.get(`${API}/tuner/boot-diagnosis`, () =>
        HttpResponse.json({
          ...RESPONSE,
          available: false,
          pod: null,
          diagnoses: [],
          log_tail: null,
        })
      )
    );
    render(<TunerBootDiagnosis isActive={true} />);

    fireEvent.click(screen.getByTestId('tbd-run'));

    expect(await screen.findByText('파드를 찾지 못함')).toBeInTheDocument();
    expect(screen.getByTestId('tbd-availability')).toHaveTextContent('파드 없음');
    expect(screen.queryByTestId('tbd-pod')).not.toBeInTheDocument();
    expect(screen.queryByTestId('tbd-log-toggle')).not.toBeInTheDocument();
  });

  it('shows 알려진 원인과 일치하는 항목 없음 when the pod has no matching diagnosis', async () => {
    server.use(
      http.get(`${API}/tuner/boot-diagnosis`, () =>
        HttpResponse.json({ ...RESPONSE, diagnoses: [], log_tail: null })
      )
    );
    render(<TunerBootDiagnosis isActive={true} />);

    fireEvent.click(screen.getByTestId('tbd-run'));

    expect(await screen.findByText('알려진 원인과 일치하는 항목 없음')).toBeInTheDocument();
  });

  it('shows a failure message when the request fails', async () => {
    server.use(
      http.get(`${API}/tuner/boot-diagnosis`, () => new HttpResponse(null, { status: 500 }))
    );
    render(<TunerBootDiagnosis isActive={true} />);

    fireEvent.click(screen.getByTestId('tbd-run'));

    expect(await screen.findByText(/기동 진단 실패: HTTP 500/)).toBeInTheDocument();
  });

  it('collapses the card and expands again when diagnosing', async () => {
    let calls = 0;
    server.use(
      http.get(`${API}/tuner/boot-diagnosis`, () => {
        calls += 1;
        return HttpResponse.json(RESPONSE);
      })
    );
    render(<TunerBootDiagnosis isActive={true} />);

    fireEvent.click(screen.getByTestId('tbd-toggle'));
    expect(screen.queryByTestId('tbd-pod')).not.toBeInTheDocument();
    expect(screen.getByTestId('tbd-run')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('tbd-run'));
    expect(await screen.findByTestId('tbd-pod')).toBeInTheDocument();
    expect(calls).toBe(1);
  });
});
