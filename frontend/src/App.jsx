import { useState, useEffect, useRef, useCallback } from "react";
import { API, COLORS, font } from "./constants";
import MetricCard from "./components/MetricCard";
import Chart from "./components/Chart";
import MonitorPage from "./pages/MonitorPage";
import LoadTestPage from "./pages/LoadTestPage";
import BenchmarkPage from "./pages/BenchmarkPage";
import TunerPage from "./pages/TunerPage";
import MockDataSwitch from "./components/MockDataSwitch";
import ErrorBoundary from "./components/ErrorBoundary";

// ──────────────────────────────────────────────
// DESIGN: Industrial / Terminal aesthetic
// 색상: 어두운 배경 + 형광 앰버/시안 강조색
// 폰트: JetBrains Mono (코드) + Barlow Condensed (헤더)
// ──────────────────────────────────────────────

// ── 유틸 함수 ──
const fmt = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));
const fmtTime = (ts) => new Date(ts * 1000).toLocaleTimeString("ko-KR", { hour12: false });

// ── 컴포넌트 ──

// ──────────────────────────
// APP ROOT
// ──────────────────────────
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

      {/* HEADER */}
      <header style={{
        background: COLORS.surface, borderBottom: `1px solid ${COLORS.border}`,
        padding: "0 24px", display: "flex", alignItems: "center",
        gap: 0, position: "sticky", top: 0, zIndex: 100,
      }}>
        <div style={{ marginRight: 32, padding: "14px 0" }}>
          <div style={{ fontFamily: font.display, fontWeight: 700, fontSize: 15, letterSpacing: "0.2em", color: COLORS.accent }}>
            vLLM<span style={{ color: COLORS.text }}>·OPT</span>
          </div>
          <div style={{ fontSize: 8, letterSpacing: "0.15em", color: COLORS.muted, textTransform: "uppercase" }}>
            Kubernetes Performance Suite
          </div>
        </div>

        <nav style={{ display: "flex", flex: 1 }}>
          {PAGES.map(p => (
            <button key={p.id} className={`nav-btn ${page === p.id ? "active" : ""}`}
              onClick={() => handleSetPage(p.id)}>
              {p.label}
            </button>
          ))}
        </nav>

<div style={{ display: "flex", alignItems: "center", gap: 12 }}>
  <MockDataSwitch />
  <div style={{ width: 1, height: 16, background: COLORS.border }} />
  <div style={{ width: 6, height: 6, borderRadius: "50%", background: COLORS.green, boxShadow: `0 0 8px ${COLORS.green}` }} />
  <span style={{ fontSize: 10, color: COLORS.muted, letterSpacing: "0.1em" }}>CONNECTED</span>
</div>
      </header>

      {/* MAIN */}
      <main style={{ padding: 1, minHeight: "calc(100vh - 57px)", background: COLORS.bg }}>
        {PAGES.map(p => (
          <div key={p.id} style={{ display: page === p.id ? undefined : 'none' }}>
            <ErrorBoundary>
              <p.Component />
            </ErrorBoundary>
          </div>
        ))}
      </main>
    </>
  );
}
