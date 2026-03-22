import { useState } from "react";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { COLORS, TARGET_COLORS } from "../constants";

const fmt = (n, d = 1) => (n == null ? '—' : Number(n).toFixed(d));

export default function MultiTargetSelector({ targetStatuses = {}, targetStates = {} }) {
  const { targets, maxTargets, addTarget, removeTarget } = useClusterConfig();
  const [isAdding, setIsAdding] = useState(false);
  const [newTarget, setNewTarget] = useState({ namespace: "", inferenceService: "" });

  const handleAdd = () => {
    if (newTarget.namespace && newTarget.inferenceService) {
      addTarget(newTarget.namespace, newTarget.inferenceService);
      setNewTarget({ namespace: "", inferenceService: "" });
      setIsAdding(false);
    }
  };

  const getTargetKey = (t) => `${t.namespace}/${t.inferenceService}`;

  return (
    <div className="multi-target-selector panel" style={{ marginBottom: '1px', borderBottom: 'none' }}>
      <div className="section-title" style={{ marginBottom: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>모니터링 대상 ({targets.length}/{maxTargets})</span>
        {!isAdding && (
          <button 
            className="btn btn-primary" 
            style={{ padding: '2px 8px', fontSize: '9px' }}
            onClick={() => setIsAdding(true)}
            disabled={targets.length >= maxTargets}
            data-testid="add-target-btn"
          >
            + 추가
          </button>
        )}
      </div>

      <div style={{ overflowX: 'auto' }}>
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
                <td colSpan={13} style={{ textAlign: 'center', color: 'var(--muted-color)', padding: '20px' }}>
                  모니터링 대상을 추가하세요
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
                    <td className="target-name" style={{ borderLeft: `3px solid ${targetColor}` }}>
                      <div style={{ color: targetColor }}>
                        {target.inferenceService}
                        {!hasMonitoringLabel && (
                          <span 
                            style={{ marginLeft: '6px', cursor: 'help' }} 
                            title="이 namespace에 openshift.io/cluster-monitoring=true 레이블이 없어 메트릭을 수집할 수 없습니다."
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
                    <td style={{ textAlign: 'right' }}>
                      {target.isDefault ? (
                        <span className="tag tag-completed" style={{ fontSize: '8px' }}>기본</span>
                      ) : (
                        <button 
                          className="btn btn-danger" 
                          style={{ padding: '0 6px', height: '20px', fontSize: '12px', minWidth: '20px', border: 'none' }}
                          onClick={() => removeTarget(index)}
                          data-testid="delete-btn"
                        >
                          ×
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
            {isAdding && (
              <tr>
                <td colSpan={11}>
                  <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    <input 
                      className="input" 
                      placeholder="Namespace" 
                      data-testid="namespace-input" 
                      value={newTarget.namespace}
                      onChange={(e) => setNewTarget(prev => ({ ...prev, namespace: e.target.value }))}
                      style={{ fontSize: '10px', padding: '3px 6px', flex: 1 }} 
                    />
                    <input 
                      className="input" 
                      placeholder="InferenceService" 
                      data-testid="is-input" 
                      value={newTarget.inferenceService}
                      onChange={(e) => setNewTarget(prev => ({ ...prev, inferenceService: e.target.value }))}
                      style={{ fontSize: '10px', padding: '3px 6px', flex: 1 }} 
                    />
                  </div>
                </td>
                <td colSpan={2}>
                  <div style={{ display: 'flex', gap: '4px' }}>
                    <button className="btn btn-green" style={{ fontSize: '9px', padding: '2px 6px' }} onClick={handleAdd} data-testid="confirm-add-btn">확인</button>
                    <button className="btn btn-danger" style={{ fontSize: '9px', padding: '2px 6px' }} onClick={() => setIsAdding(false)}>취소</button>
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
