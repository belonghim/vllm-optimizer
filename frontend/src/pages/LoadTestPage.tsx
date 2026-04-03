import { useState, useEffect, useMemo } from "react";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import type { RerunConfig } from "../components/LoadTestConfig";
import LoadTestNormalMode from "../components/LoadTestNormalMode";
import LoadTestSweepMode from "../components/LoadTestSweepMode";
import TargetSelector from "../components/TargetSelector";
import type { ClusterTarget } from "../types";
import { buildDefaultEndpoint } from "../utils/endpointUtils";

interface LoadTestPageProps {
  isActive: boolean;
  pendingConfig?: RerunConfig | null;
  onConfigConsumed?: () => void;
  onRunningChange?: (running: boolean) => void;
}

function LoadTestPage({ isActive, pendingConfig, onConfigConsumed, onRunningChange }: LoadTestPageProps) {
  const { endpoint: globalEndpoint, isLoading: globalIsLoading, resolvedModelName, crType } = useClusterConfig();
  const [mode, setMode] = useState<'normal' | 'sweep'>('normal');
  const [sharedEndpoint, setSharedEndpoint] = useState("");
  const [sharedModel, setSharedModel] = useState(resolvedModelName || "auto");
  const [selectedTarget, setSelectedTarget] = useState<ClusterTarget | null>(null);

  // Build target-based endpoint when target changes
  const targetEndpoint = useMemo(() => {
    if (!selectedTarget) return "";
    return buildDefaultEndpoint(
      selectedTarget.crType || crType,
      selectedTarget.namespace,
      selectedTarget.inferenceService
    );
  }, [selectedTarget, crType]);

  useEffect(() => {
    if (!globalIsLoading && globalEndpoint) {
      setSharedEndpoint(prev => (prev === "" || prev === globalEndpoint) ? globalEndpoint : prev);
    }
  }, [globalIsLoading, globalEndpoint]);

  useEffect(() => {
    if (!globalIsLoading && resolvedModelName) {
      setSharedModel(prev => (prev === "" || prev === "auto" || prev === resolvedModelName) ? resolvedModelName : prev);
    }
  }, [globalIsLoading, resolvedModelName]);

  return (
    <div className="flex-col-16">
      <div className="tabs">
        <button type="button" className={`tab ${mode === 'normal' ? 'active' : ''}`} onClick={() => setMode('normal')}>Normal Test</button>
        <button type="button" className={`tab ${mode === 'sweep' ? 'active' : ''}`} onClick={() => setMode('sweep')}>Sweep Test</button>
      </div>
      {mode === 'normal'
        ? <>
            <div className="panel" style={{ padding: '8px 16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="label label-no-mb">TARGET:</span>
                <TargetSelector
                  value={selectedTarget}
                  onChange={setSelectedTarget}
                  data-testid="loadtest-target-selector"
                />
              </div>
            </div>
            <LoadTestNormalMode
              isActive={isActive}
              pendingConfig={pendingConfig}
              onConfigConsumed={onConfigConsumed}
              onRunningChange={onRunningChange}
              onEndpointChange={setSharedEndpoint}
              onModelChange={setSharedModel}
              targetEndpoint={targetEndpoint}
            />
          </>
        : <LoadTestSweepMode
            isActive={isActive}
            onRunningChange={onRunningChange}
            endpoint={targetEndpoint || sharedEndpoint}
            model={sharedModel}
          />
      }
    </div>
  );
}

export default LoadTestPage;
