import { useCallback, useEffect, useRef, useState } from 'react';
import { API } from '../constants';
import { authFetch } from '../utils/authFetch';
import ErrorAlert from './ErrorAlert';
import type { BootDiagnosisResponse, ClusterTarget } from '../types';

interface TunerBootDiagnosisProps {
  isActive: boolean;
  targetOverride?: ClusterTarget | null;
}

function targetKey(target: ClusterTarget | null | undefined): string {
  if (!target) return '';
  return `${target.namespace}/${target.inferenceService}/${target.crType}`;
}

function stateTagClass(state: string | null): string {
  if (!state) return 'tag tag-idle';
  if (state === 'Running') return 'tag tag-running';
  if (state === 'Completed') return 'tag tag-completed';
  if (
    state === 'CrashLoopBackOff' ||
    state === 'Error' ||
    state === 'OOMKilled' ||
    state.includes('BackOff')
  ) {
    return 'tag tag-failed';
  }
  return 'tag tag-idle';
}

export default function TunerBootDiagnosis({ isActive, targetOverride }: TunerBootDiagnosisProps) {
  const [expanded, setExpanded] = useState(true);
  const [result, setResult] = useState<BootDiagnosisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showLog, setShowLog] = useState(false);
  const [copiedArg, setCopiedArg] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const key = targetKey(targetOverride);

  // A diagnosis is only valid for the target it was run against.
  useEffect(() => {
    setResult(null);
    setError(null);
    setShowLog(false);
  }, [key]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const run = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const params = new URLSearchParams();
    if (targetOverride) {
      params.set('namespace', targetOverride.namespace);
      params.set('is_name', targetOverride.inferenceService);
      if (targetOverride.crType) params.set('cr_type', targetOverride.crType);
    }
    const query = params.toString();
    setLoading(true);
    setError(null);
    setExpanded(true);
    try {
      const res = await authFetch(`${API}/tuner/boot-diagnosis${query ? `?${query}` : ''}`, {
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as Partial<BootDiagnosisResponse> | null;
      if (!data || typeof data.available !== 'boolean' || !Array.isArray(data.diagnoses)) {
        throw new Error('unexpected response');
      }
      setResult({
        target: data.target ?? { namespace: '', name: '', cr_type: '' },
        available: data.available,
        pod: data.pod ?? null,
        diagnoses: data.diagnoses,
        log_tail: data.log_tail ?? null,
      });
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      setResult(null);
      setError(`기동 진단 실패: ${(err as Error).message}`);
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [targetOverride]);

  const copyArg = async (arg: string) => {
    try {
      if (!navigator.clipboard?.writeText) return;
      await navigator.clipboard.writeText(arg);
      setCopiedArg(arg);
      window.setTimeout(() => setCopiedArg((current) => (current === arg ? null : current)), 1500);
    } catch {
      // Clipboard unavailable (e.g. insecure context) — the args stay selectable as text.
    }
  };

  const pod = result?.pod ?? null;

  return (
    <div className="panel" data-testid="tuner-boot-diagnosis">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <button
          type="button"
          className="btn-icon"
          aria-expanded={expanded}
          aria-label={expanded ? '기동 진단 접기' : '기동 진단 펼치기'}
          onClick={() => setExpanded((value) => !value)}
          data-testid="tbd-toggle"
        >
          {expanded ? '▾' : '▸'}
        </button>
        <div className="section-title" style={{ margin: 0 }}>
          기동 진단
        </div>
        {result && (
          <span
            className={result.available ? 'tag tag-completed' : 'tag tag-idle'}
            data-testid="tbd-availability"
          >
            {result.available ? '파드 발견' : '파드 없음'}
          </span>
        )}
        {result && (
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            {result.target.namespace}/{result.target.name}
          </span>
        )}
        <button
          type="button"
          className="btn btn-secondary"
          style={{ marginLeft: 'auto', fontSize: '11px', padding: '2px 10px' }}
          onClick={() => void run()}
          disabled={loading || !isActive}
          data-testid="tbd-run"
        >
          {loading ? '진단 중…' : '진단'}
        </button>
      </div>

      {expanded && (
        <div style={{ marginTop: '0.75rem' }}>
          <ErrorAlert message={error} />

          {!result && !error && !loading && (
            <div style={{ fontSize: '12px', color: 'var(--muted-color)' }}>
              진단 버튼을 누르면 대상 파드의 상태와 최근 로그를 분석합니다.
            </div>
          )}

          {pod && (
            <div
              data-testid="tbd-pod"
              style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '0.5rem' }}
            >
              <span className="tag tag-idle" title="파드">
                {pod.pod}
              </span>
              <span className="tag tag-idle" title="컨테이너">
                {pod.container}
              </span>
              {pod.phase && <span className={stateTagClass(pod.phase)}>phase {pod.phase}</span>}
              {pod.state && <span className={stateTagClass(pod.state)}>state {pod.state}</span>}
              <span className="tag tag-idle">재시작 {pod.restarts}</span>
              {pod.last_terminated_reason && (
                <span className="tag tag-failed">last {pod.last_terminated_reason}</span>
              )}
              {pod.exit_code != null && (
                <span className="tag tag-failed">exit {pod.exit_code}</span>
              )}
            </div>
          )}

          {result && !result.available && (
            <div style={{ fontSize: '12px', color: 'var(--muted-color)' }}>파드를 찾지 못함</div>
          )}

          {result && result.available && result.diagnoses.length === 0 && (
            <div style={{ fontSize: '12px', color: 'var(--muted-color)' }}>
              알려진 원인과 일치하는 항목 없음
            </div>
          )}

          {result?.diagnoses.map((diagnosis) => (
            <div
              key={diagnosis.code}
              data-testid={`tbd-diagnosis-${diagnosis.code}`}
              style={{
                borderTop: '1px solid var(--border-color)',
                padding: '8px 0',
              }}
            >
              <div style={{ fontSize: '12px', color: 'var(--accent-color)' }}>
                {diagnosis.title}
              </div>
              <div style={{ fontSize: '11px', marginTop: '2px' }}>{diagnosis.cause}</div>
              <div style={{ fontSize: '11px', marginTop: '2px', color: 'var(--green-color)' }}>
                해결: {diagnosis.fix}
              </div>
              {diagnosis.evidence && (
                <div
                  title={diagnosis.evidence}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '10px',
                    color: 'var(--muted-color)',
                    marginTop: '2px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {diagnosis.evidence}
                </div>
              )}
              {diagnosis.fix_args.length > 0 && (
                <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '4px' }}>
                  {diagnosis.fix_args.map((arg) => (
                    <button
                      key={arg}
                      type="button"
                      className="btn btn-secondary"
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '10px',
                        padding: '1px 6px',
                      }}
                      title="클릭하여 복사"
                      onClick={() => void copyArg(arg)}
                    >
                      {copiedArg === arg ? `${arg} 복사됨` : arg}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}

          {result?.log_tail && (
            <div style={{ marginTop: '0.5rem' }}>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ fontSize: '11px', padding: '2px 10px' }}
                onClick={() => setShowLog((value) => !value)}
                data-testid="tbd-log-toggle"
              >
                {showLog ? '로그 숨기기' : '로그 보기'}
              </button>
              {showLog && (
                <pre
                  data-testid="tbd-log-tail"
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '10px',
                    color: 'var(--text-muted)',
                    background: 'var(--bg-color)',
                    border: '1px solid var(--border-color)',
                    padding: '8px',
                    marginTop: '4px',
                    maxHeight: '240px',
                    overflow: 'auto',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {result.log_tail}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
