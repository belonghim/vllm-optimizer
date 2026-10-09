import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, it, expect, vi } from 'vitest';
import TunerModelAnalysis from './TunerModelAnalysis';
import { server } from '../mocks/server';
import { API } from '../constants';

const ANALYSIS = {
  target: { namespace: 'serving1', name: 'qwen', cr_type: 'llminferenceservice' },
  available: true,
  model: {
    architecture: 'Qwen3_5ForConditionalGeneration',
    model_type: 'qwen3_5',
    multimodal: true,
    num_hidden_layers: 24,
    full_attention_layers: 6,
    sliding_attention_layers: 0,
    linear_attention_layers: 18,
    kv_shared_layers: 0,
    num_attention_heads: 8,
    num_key_value_heads: 2,
    head_dim: 256,
    full_attention_head_dim: 256,
    mla: false,
    sliding_window: null,
    max_position_embeddings: 262144,
    num_experts: null,
    num_experts_per_tok: null,
    weight_dtype: 'bfloat16',
    quantization: 'openvino-int4',
    kv_cache_dtype: 'auto',
    kv_dtype_bytes: 2,
    kv_bytes_per_token: 12288,
    sliding_kv_bytes_per_token: 0,
    linear_state_bytes_per_seq: 19542016,
    model_weight_gib: 0.82,
    served_model_name: 'qwen',
    served_max_model_len: 8192,
    context_limit: 262144,
    rope_type: 'yarn',
    mtp_layers: 1,
    auto_map: false,
    auto_map_remote: false,
    custom_code_files: [],
    artifacts_read: true,
    chat_template_source: 'chat_template.jinja',
    template_signatures: ['tool_xml', 'think'],
    thinking_default: 'enabled',
    generation_defaults: { temperature: 0.7, top_p: 0.8 },
    warnings: [],
  },
  runtime: {
    gpu_count: 0,
    tensor_parallel_size: null,
    kv_cache_dtype: 'auto',
    max_num_batched_tokens: 8192,
  },
  memory_budget: { gib: 8, source: 'pod_memory', utilization: 0.9, overhead_gib: 6 },
  capacity: [
    { context_len: 2048, kv_bytes_per_seq: 44708864, max_concurrent_seqs: 154 },
    { context_len: 8192, kv_bytes_per_seq: 120206336, max_concurrent_seqs: 57 },
  ],
  suggested_search_space: {
    max_num_seqs_min: 32,
    max_num_seqs_max: 128,
    max_model_len_min: 2048,
    max_model_len_max: 8192,
  },
  advice: {
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
    notes: [{ level: 'warning', text: 'MTP와 prefix caching 동시 사용 주의' }],
    add_args: '--tool-call-parser=qwen3_coder',
  },
  analyst_available: true,
  warnings: [],
};

describe('TunerModelAnalysis', () => {
  it('renders deterministic facts, capacity and applies the suggested search space', async () => {
    let requestedUrl = '';
    server.use(
      http.get(`${API}/tuner/model-analysis`, ({ request }) => {
        requestedUrl = request.url;
        return HttpResponse.json(ANALYSIS);
      })
    );
    const onApply = vi.fn();
    render(
      <TunerModelAnalysis
        isActive={true}
        targetOverride={{
          namespace: 'serving1',
          inferenceService: 'qwen',
          crType: 'llminferenceservice',
        }}
        acceleratorMemoryGib={null}
        onAcceleratorMemoryChange={vi.fn()}
        onApplySearchSpace={onApply}
      />
    );

    expect(await screen.findByText('24 (full 6 · linear 18)')).toBeInTheDocument();
    expect(screen.getByText('12.0 KiB')).toBeInTheDocument();
    expect(screen.getByText('18.6 MiB')).toBeInTheDocument();
    expect(screen.getByText('154')).toBeInTheDocument();
    expect(requestedUrl).toContain('namespace=serving1');
    expect(requestedUrl).toContain('cr_type=llminferenceservice');

    fireEvent.click(screen.getByRole('button', { name: 'Apply to search space' }));
    expect(onApply).toHaveBeenCalledWith(ANALYSIS.suggested_search_space);
  });

  it('shows vLLM measured KV capacity next to the estimate', async () => {
    server.use(
      http.get(`${API}/tuner/model-analysis`, () =>
        HttpResponse.json({
          ...ANALYSIS,
          capacity: [
            {
              context_len: 2048,
              kv_bytes_per_seq: 44708864,
              max_concurrent_seqs: 154,
              observed_max_seqs: 278,
            },
            {
              context_len: 8192,
              kv_bytes_per_seq: 120206336,
              max_concurrent_seqs: 57,
              observed_max_seqs: 69,
            },
          ],
          observed: {
            kv_cache_size_tokens: 570336,
            max_concurrency: 69.62,
            block_size: 32,
            gpu_memory_utilization: 0.9,
            prefix_caching: true,
            cache_dtype: 'auto',
            pod: 'qwen-0',
            estimate_ratio: 0.819,
          },
        })
      )
    );
    render(
      <TunerModelAnalysis
        isActive={true}
        acceleratorMemoryGib={null}
        onAcceleratorMemoryChange={vi.fn()}
        onApplySearchSpace={vi.fn()}
      />
    );
    const observed = await screen.findByTestId('tma-observed');
    expect(observed).toHaveTextContent('KV pool 570,336 tokens');
    expect(observed).toHaveTextContent('69.6× @ 8,192');
    expect(observed).toHaveTextContent('estimate/measured 0.82');
    expect(screen.getByRole('columnheader', { name: 'Measured (vLLM)' })).toBeInTheDocument();
    expect(screen.getByText('278')).toBeInTheDocument();
  });

  it('asks the analyst LLM only on demand and renders its markdown', async () => {
    let explainBody: unknown = null;
    server.use(
      http.get(`${API}/tuner/model-analysis`, () => HttpResponse.json(ANALYSIS)),
      http.post(`${API}/tuner/model-analysis/explain`, async ({ request }) => {
        explainBody = await request.json();
        return HttpResponse.json({
          markdown: '## 구조 요약\n- hybrid GDN',
          analyst_available: true,
        });
      })
    );
    render(
      <TunerModelAnalysis
        isActive={true}
        acceleratorMemoryGib={null}
        onAcceleratorMemoryChange={vi.fn()}
        onApplySearchSpace={vi.fn()}
      />
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Explain with analyst LLM' }));
    expect(await screen.findByText('구조 요약')).toBeInTheDocument();
    expect((explainBody as { available: boolean }).available).toBe(true);
  });

  it('passes the GPU memory input to the parent', async () => {
    const onMemory = vi.fn();
    render(
      <TunerModelAnalysis
        isActive={true}
        acceleratorMemoryGib={null}
        onAcceleratorMemoryChange={onMemory}
        onApplySearchSpace={vi.fn()}
      />
    );
    const input = screen.getByLabelText('GPU memory per device (GiB)');
    fireEvent.change(input, { target: { value: '141' } });
    fireEvent.blur(input);
    await waitFor(() => expect(onMemory).toHaveBeenCalledWith(141));
  });

  it('renders the new model facts, overhead reserve and max_num_batched_tokens hint', async () => {
    server.use(http.get(`${API}/tuner/model-analysis`, () => HttpResponse.json(ANALYSIS)));
    render(
      <TunerModelAnalysis
        isActive={true}
        acceleratorMemoryGib={null}
        onAcceleratorMemoryChange={vi.fn()}
        onApplySearchSpace={vi.fn()}
      />
    );

    await screen.findByText('24 (full 6 · linear 18)');
    expect(screen.getByText('Context limit').parentElement).toHaveTextContent(
      '262,144 · rope yarn'
    );
    expect(screen.getByText('Chat template').parentElement).toHaveTextContent(
      'chat_template.jinja · tool_xml, think · thinking enabled'
    );
    expect(screen.getByText('Default sampling').parentElement).toHaveTextContent(
      'temperature=0.7 · top_p=0.8'
    );
    expect(screen.getByText('MTP layers').parentElement).toHaveTextContent('1');
    expect(
      screen.getByText(/Estimate includes 6 GiB reserve for CUDA graph\/activations/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/max_num_batched_tokens not required \(using 8,192\)/)
    ).toBeInTheDocument();
  });

  it('renders serving arguments from the API with ready-to-paste args and notes', async () => {
    server.use(http.get(`${API}/tuner/model-analysis`, () => HttpResponse.json(ANALYSIS)));
    render(
      <TunerModelAnalysis
        isActive={true}
        acceleratorMemoryGib={null}
        onAcceleratorMemoryChange={vi.fn()}
        onApplySearchSpace={vi.fn()}
      />
    );

    const advice = await screen.findByTestId('tma-serving-advice');
    expect(advice).toHaveTextContent('Serving arguments');
    expect(advice).toHaveTextContent('required');
    expect(advice).toHaveTextContent('mismatch');
    expect(advice).toHaveTextContent('avoid');
    expect(advice).toHaveTextContent('current: deepseek_r1');
    expect(screen.getByTestId('tma-add-args')).toHaveTextContent('--tool-call-parser=qwen3_coder');
    expect(screen.getByRole('alert')).toHaveTextContent('MTP와 prefix caching 동시 사용 주의');
  });

  it('hides serving arguments when the API returns advice: null', async () => {
    server.use(
      http.get(`${API}/tuner/model-analysis`, () =>
        HttpResponse.json({ ...ANALYSIS, advice: null })
      )
    );
    render(
      <TunerModelAnalysis
        isActive={true}
        acceleratorMemoryGib={null}
        onAcceleratorMemoryChange={vi.fn()}
        onApplySearchSpace={vi.fn()}
      />
    );

    await screen.findByText('24 (full 6 · linear 18)');
    expect(screen.queryByTestId('tma-serving-advice')).not.toBeInTheDocument();
  });

  it('hides serving arguments when the API omits advice', async () => {
    server.use(
      http.get(`${API}/tuner/model-analysis`, () =>
        HttpResponse.json({ ...ANALYSIS, advice: undefined })
      )
    );
    render(
      <TunerModelAnalysis
        isActive={true}
        acceleratorMemoryGib={null}
        onAcceleratorMemoryChange={vi.fn()}
        onApplySearchSpace={vi.fn()}
      />
    );

    await screen.findByText('24 (full 6 · linear 18)');
    expect(screen.queryByTestId('tma-serving-advice')).not.toBeInTheDocument();
  });
});
