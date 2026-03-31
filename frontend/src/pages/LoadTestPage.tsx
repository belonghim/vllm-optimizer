import { useState, useEffect } from "react";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import type { RerunConfig } from "../components/LoadTestConfig";
import LoadTestNormalMode from "../components/LoadTestNormalMode";
import LoadTestSweepMode from "../components/LoadTestSweepMode";

interface LoadTestPageProps {
  isActive: boolean;
  pendingConfig?: RerunConfig | null;
  onConfigConsumed?: () => void;
  onRunningChange?: (running: boolean) => void;
}

function LoadTestPage({ isActive, pendingConfig, onConfigConsumed, onRunningChange }: LoadTestPageProps) {
  const { endpoint: globalEndpoint, isLoading: globalIsLoading, resolvedModelName } = useClusterConfig();
  const [mode, setMode] = useState<'normal' | 'sweep'>('normal');
  const [sharedEndpoint, setSharedEndpoint] = useState("");
  const [sharedModel, setSharedModel] = useState(resolvedModelName || "auto");

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
        ? <LoadTestNormalMode
            isActive={isActive}
            pendingConfig={pendingConfig}
            onConfigConsumed={onConfigConsumed}
            onRunningChange={onRunningChange}
            onEndpointChange={setSharedEndpoint}
            onModelChange={setSharedModel}
          />
        : <LoadTestSweepMode
            isActive={isActive}
            onRunningChange={onRunningChange}
            endpoint={sharedEndpoint}
            model={sharedModel}
          />
      }
    </div>
  );
}

export default LoadTestPage;
