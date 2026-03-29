import { useState, useCallback, lazy, Suspense } from "react";
import type { RerunConfig } from "./components/LoadTestConfig";
import { useSessionKeepAlive } from './hooks/useSessionKeepAlive';
import { Toaster } from "./components/Toast";
const MonitorPage = lazy(() => import("./pages/MonitorPage"));
const LoadTestPage = lazy(() => import("./pages/LoadTestPage"));
const BenchmarkPage = lazy(() => import("./pages/BenchmarkPage"));
const TunerPage = lazy(() => import("./pages/TunerPage"));
const SlaPage = lazy(() => import("./pages/SlaPage"));
import MockDataSwitch from "./components/MockDataSwitch";
import ThemeToggle from "./components/ThemeToggle";
import ErrorBoundary from "./components/ErrorBoundary";
import ClusterConfigBar from "./components/ClusterConfigBar";
import { BenchmarkSelectionProvider } from "./contexts/BenchmarkSelectionContext";

interface PageDef {
  id: string;
  label: string;
}

const PAGES: PageDef[] = [
  { id: "monitor", label: "Monitoring" },
  { id: "tuner", label: "Auto Tuner" },
  { id: "loadtest", label: "Load Test" },
  { id: "benchmark", label: "Benchmark" },
  { id: "sla", label: "SLA" },
];

export default function App() {
  const [page, setPage] = useState("monitor");
  const [isLoadTestRunning, setIsLoadTestRunning] = useState(false);
  const [isTunerRunning, setIsTunerRunning] = useState(false);
  const [pendingLoadTestConfig, setPendingLoadTestConfig] = useState<RerunConfig | null>(null);
  const [loadTestMounted, setLoadTestMounted] = useState(false);
  const [tunerMounted, setTunerMounted] = useState(false);
  useSessionKeepAlive();

  const handleSetPage = useCallback((id: string) => {
    if (id === 'loadtest') setLoadTestMounted(true);
    if (id === 'tuner') setTunerMounted(true);
    setPage(id);
    requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
  }, []);

  const handleRerun = useCallback((config: { [key: string]: unknown }) => {
    setPendingLoadTestConfig({
      total_requests: typeof config.total_requests === 'number' ? config.total_requests : undefined,
      concurrency: typeof config.concurrency === 'number' ? config.concurrency : undefined,
      rps: typeof config.rps === 'number' ? config.rps : undefined,
      max_tokens: typeof config.max_tokens === 'number' ? config.max_tokens : undefined,
      temperature: typeof config.temperature === 'number' ? config.temperature : undefined,
      stream: typeof config.stream === 'boolean' ? config.stream : undefined,
    });
    handleSetPage("loadtest");
  }, [handleSetPage]);

  const handleConfigConsumed = useCallback(() => setPendingLoadTestConfig(null), []);

  return (
    <BenchmarkSelectionProvider>
      <div className="scanline" />
      <Toaster position="top-right" toastOptions={{ style: { maxWidth: 400 } }} />

      <header className="app-header">
        <div className="app-header-logo">
          <div className="app-header-title">
            vLLM<span className="app-header-title-sub">·OPT</span>
          </div>
          <div className="app-header-subtitle">
            Kubernetes Performance Suite
          </div>
        </div>

        <nav className="app-header-nav" aria-label="Page Navigation">
          <div role="tablist">
            {(() => {
              const runningPages = new Set([
                ...(isLoadTestRunning ? ['loadtest'] : []),
                ...(isTunerRunning ? ['tuner'] : []),
              ]);

              return PAGES.map(p => (
                <button type="button" key={p.id}
                  className={`nav-btn ${page === p.id ? "active" : ""} ${runningPages.has(p.id) ? "nav-btn--running" : ""}`}
                  role="tab"
                  aria-selected={page === p.id}
                  onClick={() => handleSetPage(p.id)}>
                  {p.label}
                  {runningPages.has(p.id) && <span role="img" className="nav-btn-dot" aria-label="Running" />}
                </button>
              ));
            })()}
          </div>
        </nav>

        <div className="app-header-right">
          <ThemeToggle />
          <div className="app-header-divider" />
          <MockDataSwitch />
          <div className="app-header-divider" />
          <div className="app-header-status-dot" />
          <span className="app-header-status-text" aria-live="assertive" aria-atomic="true">CONNECTED</span>
        </div>
      </header>

      {page === "tuner" && <ClusterConfigBar />}

      <main className="app-main">
        <ErrorBoundary>
          <Suspense fallback={<div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>Loading...</div>}>
            {page === 'monitor' && <MonitorPage isActive={page === 'monitor'} />}
            {tunerMounted && (
              <div style={page !== 'tuner' ? { display: 'none' } : undefined}>
                <TunerPage isActive={page === 'tuner'} onTabChange={handleSetPage} onRunningChange={setIsTunerRunning} />
              </div>
            )}
            {loadTestMounted && (
              <div style={page !== 'loadtest' ? { display: 'none' } : undefined}>
                <LoadTestPage isActive={page === 'loadtest'} pendingConfig={pendingLoadTestConfig} onConfigConsumed={handleConfigConsumed} onRunningChange={setIsLoadTestRunning} />
              </div>
            )}
            {page === 'benchmark' && <BenchmarkPage isActive={page === 'benchmark'} onRerun={handleRerun} />}
            {page === 'sla' && <SlaPage isActive={page === 'sla'} />}
          </Suspense>
        </ErrorBoundary>
      </main>
    </BenchmarkSelectionProvider>
  );
}
