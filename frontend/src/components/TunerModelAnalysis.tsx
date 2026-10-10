import { useCallback, useEffect, useState } from 'react';
import { API } from '../constants';
import { authFetch } from '../utils/authFetch';
import { buildDefaultEndpoint } from '../utils/endpointUtils';
import { renderMarkdown } from '../utils/renderMarkdown';
import { useClusterConfig } from '../contexts/ClusterConfigContext';
import ErrorAlert from './ErrorAlert';
import TunerServingAdvice from './TunerServingAdvice';
import type { ClusterTarget, ModelAnalysis, SuggestedSearchSpace } from '../types';

interface TunerModelAnalysisProps {
  isActive: boolean;
  targetOverride?: ClusterTarget | null;
  acceleratorMemoryGib: number | null;
  onAcceleratorMemoryChange: (gib: number | null) => void;
  onApplySearchSpace: (space: SuggestedSearchSpace) => void;
  onMaxModelLenLimit?: (limit: number | null) => void;
  disabled?: boolean;
}

function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '—';
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GiB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MiB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${bytes} B`;
}

function layerSummary(m: NonNullable<ModelAnalysis['model']>): string {
  const parts = [`full ${m.full_attention_layers}`];
  if (m.sliding_attention_layers) parts.push(`sliding ${m.sliding_attention_layers}`);
  if (m.linear_attention_layers) parts.push(`linear ${m.linear_attention_layers}`);
  if (m.kv_shared_layers) parts.push(`KV-shared ${m.kv_shared_layers}`);
  return `${m.num_hidden_layers ?? '—'} (${parts.join(' · ')})`;
}

function chatTemplateSummary(m: NonNullable<ModelAnalysis['model']>): string {
  const parts: string[] = [];
  if (m.chat_template_source) parts.push(m.chat_template_source);
  if (m.template_signatures.length > 0) parts.push(m.template_signatures.join(', '));
  if (m.thinking_default) parts.push(`thinking ${m.thinking_default}`);
  return parts.join(' · ');
}

function samplingSummary(defaults: Record<string, number>): string {
  return Object.entries(defaults)
    .map(([key, value]) => `${key}=${value}`)
    .join(' · ');
}

export default function TunerModelAnalysis({
  isActive,
  targetOverride,
  acceleratorMemoryGib,
  onAcceleratorMemoryChange,
  onApplySearchSpace,
  onMaxModelLenLimit,
  disabled = false,
}: TunerModelAnalysisProps) {
  const { endpoint, namespace, inferenceservice, crType } = useClusterConfig();
  const [analysis, setAnalysis] = useState<ModelAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [memoryInput, setMemoryInput] = useState(
    acceleratorMemoryGib != null ? String(acceleratorMemoryGib) : ''
  );

  const fetchAnalysis = useCallback(
    async (refresh: boolean, signal?: AbortSignal) => {
      const ns = targetOverride?.namespace || namespace;
      const name = targetOverride?.inferenceService || inferenceservice;
      const type = targetOverride?.crType || crType;
      const params = new URLSearchParams();
      if (ns && name) {
        params.set('namespace', ns);
        params.set('is_name', name);
        if (type) params.set('cr_type', type);
        params.set(
          'endpoint',
          targetOverride ? buildDefaultEndpoint(type, ns, name) : endpoint || ''
        );
      }
      if (!params.get('endpoint')) params.delete('endpoint');
      if (acceleratorMemoryGib) params.set('accelerator_memory_gib', String(acceleratorMemoryGib));
      if (refresh) params.set('refresh', 'true');
      setLoading(true);
      setError(null);
      setExplanation(null);
      try {
        const res = await authFetch(`${API}/tuner/model-analysis?${params.toString()}`, { signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as Partial<ModelAnalysis> | null;
        if (!data?.target || !Array.isArray(data.capacity) || !Array.isArray(data.warnings)) {
          throw new Error('unexpected response');
        }
        setAnalysis(data as ModelAnalysis);
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        setError(`Model analysis failed: ${(err as Error).message}`);
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [targetOverride, namespace, inferenceservice, crType, endpoint, acceleratorMemoryGib]
  );

  useEffect(() => {
    onMaxModelLenLimit?.(analysis?.max_model_len_limit ?? null);
  }, [analysis, onMaxModelLenLimit]);

  useEffect(() => {
    if (!isActive) return;
    const controller = new AbortController();
    void fetchAnalysis(false, controller.signal);
    return () => controller.abort();
  }, [isActive, fetchAnalysis]);

  const explain = async () => {
    if (!analysis) return;
    setExplaining(true);
    try {
      const res = await authFetch(`${API}/tuner/model-analysis/explain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(analysis),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: { markdown: string | null } = await res.json();
      setExplanation(data.markdown ?? 'The analyst LLM returned no answer.');
    } catch (err) {
      setExplanation(`Analyst LLM call failed: ${(err as Error).message}`);
    } finally {
      setExplaining(false);
    }
  };

  const commitMemory = () => {
    const parsed = Number(memoryInput);
    onAcceleratorMemoryChange(memoryInput.trim() && parsed > 0 ? parsed : null);
  };

  const m = analysis?.model;
  const observed = analysis?.observed;
  const space = analysis?.suggested_search_space;
  const overheadGib = analysis?.memory_budget.overhead_gib ?? 0;
  const overheadSourceLabel =
    analysis?.memory_budget.overhead_source === 'table'
      ? '추정 테이블'
      : analysis?.memory_budget.overhead_source === 'observed'
        ? '관측 KV 풀로 보정'
        : null;
  const facts: [string, string][] = m
    ? [
        ['Architecture', `${m.architecture ?? '—'}${m.multimodal ? ' (multimodal)' : ''}`],
        ['Layers', layerSummary(m)],
        [
          'Attention',
          m.mla
            ? 'MLA (compressed latent KV)'
            : `${m.num_attention_heads ?? '—'} heads · ${m.num_key_value_heads ?? '—'} KV heads · head_dim ${m.head_dim ?? '—'}${
                m.full_attention_head_dim && m.full_attention_head_dim !== m.head_dim
                  ? ` (full ${m.full_attention_head_dim})`
                  : ''
              }`,
        ],
        ['KV / token (full attention)', formatBytes(m.kv_bytes_per_token)],
        ...(m.sliding_kv_bytes_per_token
          ? ([
              [
                'KV / token (sliding)',
                `${formatBytes(m.sliding_kv_bytes_per_token)} × ≤${m.sliding_window ?? '?'} tokens`,
              ],
            ] as [string, string][])
          : []),
        ...(m.linear_state_bytes_per_seq
          ? ([['Linear state / seq', formatBytes(m.linear_state_bytes_per_seq)]] as [
              string,
              string,
            ][])
          : []),
        ['KV cache dtype', `${m.kv_cache_dtype} (${m.kv_dtype_bytes} B)`],
        ['Weights', m.model_weight_gib != null ? `${m.model_weight_gib.toFixed(2)} GiB` : '—'],
        ['Quantization', m.quantization ?? m.weight_dtype ?? '—'],
        ...(m.num_experts
          ? ([['MoE', `${m.num_experts} experts · top-${m.num_experts_per_tok ?? '?'}`]] as [
              string,
              string,
            ][])
          : []),
        [
          'Context',
          `max_position ${m.max_position_embeddings ?? '—'} · serving ${m.served_max_model_len ?? '—'}`,
        ],
        ...(m.context_limit != null
          ? ([
              [
                'Context limit',
                `${m.context_limit.toLocaleString()}${m.rope_type ? ` · rope ${m.rope_type}` : ''}`,
              ],
            ] as [string, string][])
          : []),
        ...(m.chat_template_source || m.template_signatures.length > 0 || m.thinking_default
          ? ([['Chat template', chatTemplateSummary(m)]] as [string, string][])
          : []),
        ...(Object.keys(m.generation_defaults).length > 0
          ? ([['Default sampling', samplingSummary(m.generation_defaults)]] as [string, string][])
          : []),
        ...(m.mtp_layers > 0 ? ([['MTP layers', String(m.mtp_layers)]] as [string, string][]) : []),
      ]
    : [];

  return (
    <div className="panel" data-testid="tuner-model-analysis">
      <div
        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}
      >
        <div className="section-title" style={{ margin: 0 }}>
          Model Analysis
        </div>
        {analysis && (
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            {analysis.target.namespace}/{analysis.target.name}
          </span>
        )}
        <button
          type="button"
          className="btn btn-secondary"
          style={{ marginLeft: 'auto', fontSize: '11px', padding: '2px 8px' }}
          onClick={() => void fetchAnalysis(true)}
          disabled={loading}
        >
          {loading ? 'Analyzing…' : 'Re-analyze'}
        </button>
      </div>

      <ErrorAlert message={error} />

      <div className="grid-form grid-form-compact" style={{ marginBottom: '0.75rem' }}>
        <div>
          <label className="label" htmlFor="tma-accelerator-memory">
            GPU memory per device (GiB)
          </label>
          <input
            id="tma-accelerator-memory"
            className="input"
            type="number"
            min={1}
            placeholder="e.g. 80 (H100), 141 (H200)"
            value={memoryInput}
            onChange={(e) => setMemoryInput(e.target.value)}
            onBlur={commitMemory}
            onKeyDown={(e) => e.key === 'Enter' && commitMemory()}
            disabled={disabled}
          />
        </div>
        <div>
          <div className="label">Memory budget</div>
          <div style={{ fontSize: '12px', paddingTop: '6px' }}>
            {analysis?.memory_budget.gib != null
              ? analysis.memory_budget.dedicated_kv
                ? `${analysis.memory_budget.gib} GiB KV pool (${analysis.memory_budget.source})`
                : `${analysis.memory_budget.gib} GiB × ${analysis.memory_budget.utilization} (${analysis.memory_budget.source})`
              : '—'}
            {analysis?.runtime.gpu_count ? ` · GPU ×${analysis.runtime.gpu_count}` : ''}
            {analysis?.runtime.tensor_parallel_size
              ? ` · TP ${analysis.runtime.tensor_parallel_size}`
              : ''}
            {analysis?.runtime.max_num_batched_tokens != null
              ? ` · max_num_batched_tokens not required (using ${analysis.runtime.max_num_batched_tokens.toLocaleString()})`
              : ''}
          </div>
        </div>
      </div>

      {analysis?.warnings.map((w) => (
        <ErrorAlert key={w} message={w} severity="warning" />
      ))}

      {m && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: '4px 16px',
            fontSize: '12px',
            marginBottom: '0.75rem',
          }}
        >
          {facts.map(([k, v]) => (
            <div key={k} style={{ display: 'flex', gap: '8px' }}>
              <span style={{ color: 'var(--text-muted)', minWidth: '150px' }}>{k}</span>
              <span>{v}</span>
            </div>
          ))}
        </div>
      )}

      {observed && (
        <div style={{ fontSize: '12px', marginBottom: '0.5rem' }} data-testid="tma-observed">
          <span style={{ color: 'var(--text-muted)' }}>Measured (vLLM): </span>
          KV pool {observed.kv_cache_size_tokens.toLocaleString()} tokens
          {observed.max_concurrency != null && m?.served_max_model_len
            ? ` · ${observed.max_concurrency.toFixed(1)}× @ ${m.served_max_model_len.toLocaleString()}`
            : ''}
          {observed.estimate_ratio != null
            ? ` · estimate/measured ${observed.estimate_ratio.toFixed(2)}`
            : ''}
          {observed.prefix_caching ? ' · prefix caching on' : ''}
        </div>
      )}

      {analysis && analysis.capacity.length > 0 && (
        <table className="table" aria-label="KV capacity by context length">
          <thead>
            <tr>
              <th>Context length</th>
              <th>KV / sequence</th>
              <th>Max concurrent sequences (estimate)</th>
              {observed && <th>Measured (vLLM)</th>}
            </tr>
          </thead>
          <tbody>
            {analysis.capacity.map((row) => (
              <tr key={row.context_len}>
                <td>{row.context_len.toLocaleString()}</td>
                <td>{formatBytes(row.kv_bytes_per_seq)}</td>
                <td>{row.max_concurrent_seqs?.toLocaleString() ?? '—'}</td>
                {observed && <td>{row.observed_max_seqs?.toLocaleString() ?? '—'}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {analysis && analysis.capacity.length > 0 && (
        <div style={{ fontSize: '11px', color: 'var(--muted-color)', margin: '4px 0 0.75rem' }}>
          {overheadGib > 0
            ? `Estimate includes ${overheadGib} GiB reserve for CUDA graph/activations${
                overheadSourceLabel ? ` (${overheadSourceLabel})` : ''
              }.`
            : 'Estimate is a theoretical upper bound — runtime overhead is not subtracted.'}
          {observed &&
            ' Measured = KV pool vLLM actually allocated with the current args (shown up to the served max_model_len); suggestions use it.'}
        </div>
      )}

      <TunerServingAdvice advice={analysis?.advice} />

      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        {space && (
          <>
            <span style={{ fontSize: '12px' }}>
              Suggested: max_num_seqs {space.max_num_seqs_min}–{space.max_num_seqs_max}
            </span>
            <button
              type="button"
              className="btn btn-primary"
              style={{ fontSize: '12px', padding: '4px 12px' }}
              onClick={() => onApplySearchSpace(space)}
              disabled={disabled}
            >
              Apply to search space
            </button>
          </>
        )}
        {analysis?.analyst_available && analysis.available && (
          <button
            type="button"
            className="btn btn-secondary"
            style={{ fontSize: '12px', padding: '4px 12px', marginLeft: 'auto' }}
            onClick={() => void explain()}
            disabled={explaining}
          >
            {explaining ? 'Analyst LLM writing…' : 'Explain with analyst LLM'}
          </button>
        )}
      </div>

      {explanation && (
        <div style={{ marginTop: '0.75rem' }} data-testid="tuner-model-analysis-explanation">
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>
            Analyst LLM narrative — for reference only; the computed values above are authoritative.
          </div>
          {renderMarkdown(explanation)}
        </div>
      )}
    </div>
  );
}
