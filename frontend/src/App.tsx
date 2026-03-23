import { useState } from "react";
import { useSessionKeepAlive } from './hooks/useSessionKeepAlive';
import MonitorPage from "./pages/MonitorPage";
import LoadTestPage from "./pages/LoadTestPage";
import BenchmarkPage from "./pages/BenchmarkPage";
import TunerPage from "./pages/TunerPage";
import SlaPage from "./pages/SlaPage";
import MockDataSwitch from "./components/MockDataSwitch";
import ErrorBoundary from "./components/ErrorBoundary";
import ClusterConfigBar from "./components/ClusterConfigBar";

interface PageDef {
  id: string;
  label: string;
  Component: React.ComponentType<{ isActive: boolean }>;
}

const PAGES: PageDef[] = [
  { id: "monitor", label: "실시간 모니터링", Component: MonitorPage },
  { id: "tuner", label: "자동 파라미터 튜닝", Component: TunerPage },
  { id: "loadtest", label: "부하 테스트", Component: LoadTestPage },
  { id: "benchmark", label: "벤치마크 비교", Component: BenchmarkPage },
  { id: "sla", label: "SLA", Component: SlaPage },
];

export default function App() {
  const [page, setPage] = useState("monitor");
  useSessionKeepAlive();

  const handleSetPage = (id: string) => {
    setPage(id);
    requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
  };

  return (
    <>
      <div className="scanline" />

      <header className="app-header">
        <div className="app-header-logo">
          <div className="app-header-title">
            vLLM<span className="app-header-title-sub">·OPT</span>
          </div>
          <div className="app-header-subtitle">
            Kubernetes Performance Suite
          </div>
        </div>

        <nav className="app-header-nav" role="tablist" aria-label="페이지 네비게이션">
          {PAGES.map(p => (
            <button key={p.id} className={`nav-btn ${page === p.id ? "active" : ""}`}
              role="tab"
              aria-selected={page === p.id}
              onClick={() => handleSetPage(p.id)}>
              {p.label}
            </button>
          ))}
        </nav>

        <div className="app-header-right">
          <MockDataSwitch />
          <div className="app-header-divider" />
          <div className="app-header-status-dot" />
          <span className="app-header-status-text" aria-live="assertive" aria-atomic="true">CONNECTED</span>
        </div>
      </header>

      {page === "tuner" && <ClusterConfigBar />}

      <main className="app-main">
        {PAGES.map(p => (
          <div key={p.id} className={page === p.id ? undefined : 'app-page--hidden'}>
            <ErrorBoundary>
              <p.Component isActive={page === p.id} />
            </ErrorBoundary>
          </div>
        ))}
      </main>
    </>
  );
}
