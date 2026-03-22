import { useState } from "react";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import { COLORS } from "../constants";

const TARGET_COLORS = [COLORS.accent, COLORS.cyan, COLORS.green, COLORS.red, COLORS.purple];

export default function MultiTargetSelector({ targetStatuses = {} }) {
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

      <div className="grid-form" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '8px' }}>
        {targets.map((target, index) => {
          const key = getTargetKey(target);
          const status = targetStatuses[key] || {};
          const hasMonitoringLabel = status.hasMonitoringLabel !== false;
          const targetColor = TARGET_COLORS[index % TARGET_COLORS.length];

          return (
            <div 
              key={index} 
              className="metric-card" 
              style={{ padding: '10px 12px', minHeight: '60px', borderLeft: `3px solid ${targetColor}` }}
              data-testid={`target-card-${index}`}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: '10px', color: 'var(--muted-color)', marginBottom: '2px' }}>
                    {target.namespace}
                  </div>
                  <div style={{ fontSize: '12px', fontWeight: '600', color: targetColor }}>
                    {target.inferenceService}
                  </div>
                </div>
                
                <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                  {target.isDefault ? (
                    <span className="tag tag-completed" style={{ fontSize: '8px' }}>기본</span>
                  ) : (
                    <button 
                      className="btn btn-danger" 
                      style={{ padding: '0 4px', height: '18px', fontSize: '10px', minWidth: '18px', border: 'none' }}
                      onClick={() => removeTarget(index)}
                      data-testid="delete-btn"
                    >
                      ×
                    </button>
                  )}
                </div>
              </div>

              {!hasMonitoringLabel && (
                <div 
                  className="tag tag-failed" 
                  style={{ marginTop: '6px', display: 'inline-flex', alignItems: 'center', gap: '4px', cursor: 'help' }}
                  title="이 namespace에 openshift.io/cluster-monitoring=true 레이블이 없어 메트릭을 수집할 수 없습니다."
                  data-testid="no-monitoring-warning"
                >
                  ⚠️ 메트릭 수집 불가
                </div>
              )}
            </div>
          );
        })}

        {isAdding && (
          <div className="metric-card" style={{ padding: '10px 12px', borderStyle: 'dashed' }}>
            <div className="flex-col-1" style={{ gap: '8px' }}>
              <input 
                type="text" 
                className="input" 
                placeholder="Namespace" 
                style={{ fontSize: '10px', padding: '4px 8px' }}
                value={newTarget.namespace}
                onChange={(e) => setNewTarget(prev => ({ ...prev, namespace: e.target.value }))}
                data-testid="namespace-input"
              />
              <input 
                type="text" 
                className="input" 
                placeholder="InferenceService" 
                style={{ fontSize: '10px', padding: '4px 8px' }}
                value={newTarget.inferenceService}
                onChange={(e) => setNewTarget(prev => ({ ...prev, inferenceService: e.target.value }))}
                data-testid="is-input"
              />
              <div style={{ display: 'flex', gap: '4px' }}>
                <button 
                  className="btn btn-green" 
                  style={{ flex: 1, padding: '2px', fontSize: '9px' }}
                  onClick={handleAdd}
                  data-testid="confirm-add-btn"
                >
                  확인
                </button>
                <button 
                  className="btn btn-danger" 
                  style={{ flex: 1, padding: '2px', fontSize: '9px' }}
                  onClick={() => setIsAdding(false)}
                >
                  취소
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

