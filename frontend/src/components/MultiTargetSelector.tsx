import { useState } from "react";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { TARGET_COLORS } from "../constants";
import { fmt } from "../utils/format";
import { authFetch } from "../utils/authFetch";
import type { ClusterTarget } from "../types";

const TOTAL_COLUMNS = 13;

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
      } catch (err) {
        setAddError("Validation error occurred");
      } finally {
        setIsValidating(false);
      }
    }
  };

  const getTargetKey = (t: ClusterTarget) => `${t.namespace}/${t.inferenceService}`;

  return (
    <div className="multi-target-selector panel multi-target-no-border">
      <div className="section-title multi-target-header">
        <span>Monitoring Targets ({targets.length}/{maxTargets})</span>
        {!isAdding && (
          <button 
            className="btn btn-primary multi-target-add-btn" 
            onClick={() => setIsAdding(true)}
            disabled={targets.length >= maxTargets}
            data-testid="add-target-btn"
          >
            + Add
          </button>
        )}
      </div>

      <div className="multi-target-overflow">
        <table className="monitor-table">
          <thead>
            <tr>
              <th>Target</th>
              <th>TPS</th>
              <th>RPS</th>
              <th>TTFT m/p99</th>
              <th>Lat m/p99</th>
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
            {targets.length === 0 ? (
              <tr>
                <td colSpan={TOTAL_COLUMNS} className="multi-target-empty">
                  Add a monitoring target
                </td>
              </tr>
            ) : (
              targets.map((target, index) => {
                 const key = getTargetKey(target);
                 const state = targetStates[key];
                 const status = state?.status || targetStatuses[key]?.status || 'collecting';
                 const data = state?.data || state?.metrics;
                 const hasMonitoringLabel = state?.hasMonitoringLabel !== false && targetStatuses[key]?.hasMonitoringLabel !== false;
                 const targetColor = TARGET_COLORS[index % TARGET_COLORS.length];

                return (
                  <tr key={key} data-testid={`target-row-${index}`}>
                    <td className="target-name multi-target-color-cell" style={{ borderLeftColor: targetColor }}>
                      <div style={{ color: targetColor }}>
                        {target.inferenceService}
                        {target.crType === "llminferenceservice" && (
                          <span 
                            className="tag tag-info"
                            title="LLMInferenceService"
                            data-testid="llmis-badge"
                            style={{ marginLeft: "8px" }}
                          >
                            LLMIS
                          </span>
                        )}
                        {!hasMonitoringLabel && (
                          <span 
                            className="multi-target-warning-icon"
                            title="This namespace lacks the openshift.io/cluster-monitoring=true label, so metrics cannot be collected."
                            data-testid="no-monitoring-warning"
                          >
                            ⚠️
                          </span>
                        )}
                      </div>
                      <div className="target-ns">{target.namespace}</div>
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
                        <td>{data.pods_ready} / {data.pods}</td>
                      </>
                    )}
                    <td className="multi-target-action-cell">
                       {target.isDefault ? (
                          <span className="tag tag-completed multi-target-default-tag">Default</span>
                       ) : (
                         <div className="multi-target-action-btns">
                           <button
                             className="btn btn-secondary multi-target-setdefault-btn"
                             onClick={() => setDefaultTarget(target.namespace, target.inferenceService)}
                             data-testid="set-default-btn"
                              title="Set as default"
                           >
                             ★
                           </button>
                           <button
                             className="btn btn-danger multi-target-delete-btn"
                             onClick={() => removeTarget(target.namespace, target.inferenceService)}
                             data-testid="delete-btn"
                           >
                             ×
                           </button>
                         </div>
                       )}
                     </td>
                  </tr>
                );
              })
            )}
            {isAdding && (
              <tr>
                <td colSpan={TOTAL_COLUMNS - 2}>
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
                      <option value="llminferenceservice">llmisvc (LLMIS)</option>
                    </select>
                    {addError && <div className="multi-target-error-msg" data-testid="add-target-error">{addError}</div>}
                  </div>
                </td>
                <td colSpan={2}>
                  <div className="multi-target-btn-row">
                    <button 
                      className="btn btn-green multi-target-action-btn" 
                      onClick={handleAdd} 
                      data-testid="confirm-add-btn"
                      disabled={isValidating}
                    >
                      {isValidating ? "Validating..." : "Confirm"}
                    </button>
                     <button className="btn btn-danger multi-target-action-btn" onClick={() => setIsAdding(false)} disabled={isValidating}>Cancel</button>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
