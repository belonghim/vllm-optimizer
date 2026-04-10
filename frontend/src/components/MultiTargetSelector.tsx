import { useState, useEffect, useRef, Fragment } from "react";
import { getTargetKey, parseTargetKey } from "../utils/targetKey";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { TARGET_COLORS } from "../constants";
import { fmt } from "../utils/format";
import { authFetch } from "../utils/authFetch";
import type { ClusterTarget, PerPodMetricSnapshot, PerPodMetricsDict } from "../types";
import ExpandablePodRow from "./ExpandablePodRow";
import "./MultiTargetSelector.css";

const POD_CACHE_TTL_MS = 10_000;

interface PodCacheEntry {
  data: PerPodMetricSnapshot[];
  timestamp: number;
}

interface TargetStatus {
  status: string;
  hasMonitoringLabel: boolean;
}

interface TargetStateData {
  tps?: number | null;
  rps?: number | null;
  ttft_mean?: number | null;
  ttft_p99?: number | null;
  latency_mean?: number | null;
  latency_p99?: number | null;
  kv_cache?: number | null;
  kv_hit_rate?: number | null;
  gpu_util?: number | null;
  gpu_mem_used?: number | null;
  gpu_mem_total?: number | null;
  running?: number | null;
  waiting?: number | null;
  pods_ready?: number;
  pods?: number;
}

interface TargetState {
  status?: string;
  data?: TargetStateData | null;
  metrics?: TargetStateData | null;
  history?: unknown[];
  hasMonitoringLabel?: boolean;
  crExists?: boolean | null;
  error?: string | null;
}

interface MultiTargetSelectorProps {
  targetStatuses?: Record<string, TargetStatus>;
  targetStates?: Record<string, TargetState>;
}

export default function MultiTargetSelector({
  targetStatuses = {},
  targetStates = {}
}: MultiTargetSelectorProps) {
  const { targets, maxTargets, addTarget, removeTarget, setDefaultTarget, crType: contextCrType } = useClusterConfig();
  const [isAdding, setIsAdding] = useState(false);
  const [newTarget, setNewTarget] = useState({ namespace: "", inferenceService: "", crType: contextCrType || "inferenceservice" });
  const [isValidating, setIsValidating] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [podData, setPodData] = useState<Record<string, PodCacheEntry>>({});
  const pendingFetches = useRef<Map<string, Promise<void>>>(new Map());

  const [userSelectedKey, setUserSelectedKey] = useState<string | null>(null);
  const pendingDefaultKey = userSelectedKey ?? (targets.length > 0 ? getTargetKey(targets[0]) : '');

  useEffect(() => {
    if (userSelectedKey && !targets.some(t => getTargetKey(t) === userSelectedKey)) {
      setUserSelectedKey(null);
    }
  }, [targets, userSelectedKey]);

  const handleAdd = async () => {
    if (newTarget.namespace && newTarget.inferenceService) {
      setIsValidating(true);
      setAddError(null);
      try {
        const response = await authFetch(`/api/metrics/latest?namespace=${newTarget.namespace}&is_name=${newTarget.inferenceService}&cr_type=${newTarget.crType}`);
        if (!response.ok) {
          setAddError("Target not found");
          return;
        }
        addTarget(newTarget.namespace, newTarget.inferenceService, newTarget.crType);
        setNewTarget({ namespace: "", inferenceService: "", crType: contextCrType || "inferenceservice" });
        setIsAdding(false);
      } catch {
        setAddError("Validation error occurred");
      } finally {
        setIsValidating(false);
      }
    }
  };

  const toggleRowExpand = (target: ClusterTarget) => {
    const key = getTargetKey(target);
    const isExpanded = expandedRows.has(key);

    if (isExpanded) {
      setExpandedRows(prev => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
      return;
    }

    setExpandedRows(prev => new Set(prev).add(key));

    const cached = podData[key];
    if (cached && Date.now() - cached.timestamp < POD_CACHE_TTL_MS) {
      return;
    }

    if (pendingFetches.current.has(key)) {
      return;
    }

    const fetchPromise = (async () => {
      try {
        const response = await authFetch("/api/metrics/pods", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            targets: [{
              namespace: target.namespace,
              inferenceService: target.inferenceService,
              cr_type: target.crType
            }]
          })
        });

        if (response.ok) {
          const data: PerPodMetricsDict = await response.json();
          const pods: PerPodMetricSnapshot[] = data[key]?.per_pod ?? [];
          setPodData(prev => ({ ...prev, [key]: { data: pods, timestamp: Date.now() } }));
        }
      } catch (err) {
        console.error("Failed to fetch pod data:", err);
      } finally {
        pendingFetches.current.delete(key);
      }
    })();

    pendingFetches.current.set(key, fetchPromise);
  };

  const renderTargetItem = (target: ClusterTarget, index: number) => {
    const key = getTargetKey(target);
    const state = targetStates[key];
    const status = state?.status || targetStatuses[key]?.status || 'collecting';
    const data = state?.data || state?.metrics;
    const hasMonitoringLabel = state?.hasMonitoringLabel !== false && targetStatuses[key]?.hasMonitoringLabel !== false;
    const crExists = state?.crExists;
    const targetColor = TARGET_COLORS[index % TARGET_COLORS.length];
    const isExpanded = expandedRows.has(key);
    const pods = data?.pods ?? 1;
    const canExpand = pods > 1;
    const isFirstTarget = index === 0;

    return (
      <Fragment key={key}>
        <tr data-testid={`target-row-${index}`} className={isFirstTarget ? "multi-target-row-default" : ""}>
          <td className="target-name multi-target-color-cell" style={{ borderLeftColor: targetColor }}>
            <div style={{ color: targetColor }}>
              {target.inferenceService}
              {!hasMonitoringLabel && (
                <span
                  className="multi-target-warning-icon"
                  title="This namespace lacks the openshift.io/cluster-monitoring=true label, so metrics cannot be collected."
                  data-testid="no-monitoring-warning"
                >
                  ⚠️
                </span>
              )}
              {crExists === false && (
                <span
                  className="multi-target-warning-icon"
                  title="CR not found in K8s. It may have been deleted. Metrics show last known values."
                  data-testid="cr-not-found-warning"
                >
                  🔴
                </span>
              )}
            </div>
            <div className="target-ns">{target.namespace}</div>
          </td>
          <td>
            {target.crType === "llminferenceservice" ? (
              <span className="tag tag-info" title="LLMInferenceService" data-testid="llmis-badge">LLMIS</span>
            ) : (
              <span className="tag tag-idle" title="InferenceService" data-testid="isvc-badge">ISVC</span>
            )}
          </td>
          {status === 'collecting' ? (
            <>
              <td>...</td><td>...</td><td>...</td><td>...</td><td>...</td>
              <td>...</td><td>...</td><td>...</td><td>...</td><td>...</td><td>...</td>
            </>
          ) : !data ? (
            <>
              <td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>
              <td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>
            </>
          ) : (
            <>
              <td>{fmt(data.tps, 0)}</td>
              <td>{fmt(data.rps, 1)}</td>
              <td>{fmt(data.ttft_mean, 0)} / {fmt(data.ttft_p99, 0)}</td>
              <td>{fmt(data.latency_mean, 0)} / {fmt(data.latency_p99, 0)}</td>
              <td>{fmt(data.kv_cache, 1)}</td>
              <td>{fmt(data.kv_hit_rate, 1)}</td>
              <td>{fmt(data.gpu_util, 1)}</td>
              <td>{fmt(data.gpu_mem_used, 1)} / {fmt(data.gpu_mem_total, 0)}</td>
              <td>{data.running ?? '—'}</td>
              <td>{data.waiting ?? '—'}</td>
              <td>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  {canExpand && (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => toggleRowExpand(target)}
                      style={{ padding: '2px 6px', fontSize: '12px' }}
                      data-testid={`expand-btn-${index}`}
                      aria-label={isExpanded ? `Collapse ${target.inferenceService}` : `Expand ${target.inferenceService}`}
                    >
                      {isExpanded ? '▼' : '▶'}
                    </button>
                  )}
                  <span>{data.pods_ready} / {data.pods}</span>
                </div>
              </td>
            </>
          )}
          <td className="multi-target-action-cell">
            <div className="multi-target-action-btns">
              <input
                type="radio"
                name="default-target"
                value={key}
                checked={pendingDefaultKey === key}
                onChange={() => {
                  setApplyError(null);
                  setUserSelectedKey(key === getTargetKey(targets[0]) ? null : key);
                }}
                data-testid={`radio-default-${index}`}
                aria-label={`Set ${target.inferenceService} as default`}
                style={{ cursor: 'pointer' }}
              />
              <button
                type="button"
                className="btn btn-danger multi-target-delete-btn"
                onClick={() => removeTarget(target.namespace, target.inferenceService, target.crType || "inferenceservice")}
                disabled={targets.length === 1}
                data-testid="delete-btn"
                aria-label={`Remove monitoring target ${target.namespace}/${target.inferenceService}`}
              >
                ×
              </button>
            </div>
          </td>
        </tr>
        {isExpanded && podData[key]?.data && (
          <ExpandablePodRow pods={podData[key].data} parentColor={targetColor} />
        )}
      </Fragment>
    );
  };

  return (
    <div className="multi-target-selector panel multi-target-no-border">
      <div className="section-title multi-target-header">
        <span>Monitoring Targets ({targets.length}/{maxTargets})</span>
        <div className="multi-target-header-actions">
          {targets.length > 1 && userSelectedKey !== null && userSelectedKey !== getTargetKey(targets[0]) && (
            <button
              type="button"
              className="btn btn-primary multi-target-apply-btn"
              data-testid="apply-default-btn"
              onClick={async () => {
                const parsed = parseTargetKey(pendingDefaultKey);
                if (parsed) {
                  try {
                    setApplyError(null);
                    await setDefaultTarget(parsed.namespace, parsed.inferenceService, parsed.crType);
                    setUserSelectedKey(null);
                  } catch {
                    setApplyError("기본 타겟 업데이트 실패");
                  }
                }
              }}
            >
              Change default
            </button>
          )}
          {applyError && (
            <span className="multi-target-error-msg" style={{ fontSize: '12px' }}>{applyError}</span>
          )}
          {!isAdding && (
            <button
              type="button"
              className="btn btn-primary multi-target-add-btn"
              onClick={() => setIsAdding(true)}
              disabled={targets.length >= maxTargets}
              data-testid="add-target-btn"
            >
              + Add
            </button>
          )}
        </div>
      </div>

      {targets.length === 0 ? (
        <div className="multi-target-empty">
          Add a monitoring target
        </div>
      ) : (
        <table className="monitor-table">
          <thead>
            <tr>
              <th>Target</th>
              <th>Type</th>
              <th>TPS</th>
              <th>RPS</th>
              <th>TTFT m/p99</th>
              <th>E2E Lat m/p99</th>
              <th>KV%</th>
              <th>KV Hit%</th>
              <th>GPU%</th>
              <th>GPU Mem</th>
              <th>Run</th>
              <th>Wait</th>
              <th>Pods</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {targets.map((target, i) => renderTargetItem(target, i))}
          </tbody>
        </table>
      )}

      {isAdding && (
        <div className="multi-target-add-form">
          <div className="multi-target-input-row">
            <input
              className="input multi-target-input"
              placeholder="Namespace"
              data-testid="namespace-input"
              value={newTarget.namespace}
              onChange={(e) => setNewTarget(prev => ({ ...prev, namespace: e.target.value }))}
            />
            <input
              className="input multi-target-input"
              placeholder="InferenceService"
              data-testid="is-input"
              value={newTarget.inferenceService}
              onChange={(e) => setNewTarget(prev => ({ ...prev, inferenceService: e.target.value }))}
            />
            <select
              className="input multi-target-input"
              data-testid="cr-type-select"
              value={newTarget.crType}
              onChange={(e) => setNewTarget(prev => ({ ...prev, crType: e.target.value }))}
            >
              <option value="inferenceservice">isvc (KServe)</option>
              <option value="llminferenceservice">LLMIS (llmisvc)</option>
            </select>
            {addError && <div className="multi-target-error-msg" data-testid="add-target-error">{addError}</div>}
          </div>
          <div className="multi-target-btn-row">
            <button
              type="button"
              className="btn btn-green multi-target-action-btn"
              onClick={handleAdd}
              data-testid="confirm-add-btn"
              disabled={isValidating}
            >
              {isValidating ? "Validating..." : "Confirm"}
            </button>
            <button type="button" className="btn btn-danger multi-target-action-btn" onClick={() => setIsAdding(false)} disabled={isValidating}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}
