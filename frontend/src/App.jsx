import { useState } from "react";
import MonitorPage from "./pages/MonitorPage";
import LoadTestPage from "./pages/LoadTestPage";
import BenchmarkPage from "./pages/BenchmarkPage";
import TunerPage from "./pages/TunerPage";
import MockDataSwitch from "./components/MockDataSwitch";
import ErrorBoundary from "./components/ErrorBoundary";

const PAGES = [
  { id: "monitor", label: "실시간 모니터링", Component: MonitorPage },
  { id: "loadtest", label: "부하 테스트", Component: LoadTestPage },
  { id: "benchmark", label: "벤치마크 비교", Component: BenchmarkPage },
  { id: "tuner", label: "자동 파라미터 튜닝", Component: TunerPage },
];

export default function App() {
  const [page, setPage] = useState("monitor");

  const handleSetPage = (id) => {
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

        <nav className="app-header-nav">
          {PAGES.map(p => (
            <button key={p.id} className={`nav-btn ${page === p.id ? "active" : ""}`}
              onClick={() => handleSetPage(p.id)}>
              {p.label}
            </button>
          ))}
        </nav>

        <div className="app-header-right">
          <MockDataSwitch />
          <div className="app-header-divider" />
          <div className="app-header-status-dot" />
          <span className="app-header-status-text">CONNECTED</span>
        </div>
      </header>

      <main className="app-main">
        {PAGES.map(p => (
          <div key={p.id} className={page === p.id ? undefined : 'app-page--hidden'}>
            <ErrorBoundary>
              <p.Component />
            </ErrorBoundary>
          </div>
        ))}
      </main>
    </>
  );
}
