import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { authFetch } from '../utils/authFetch';
import { API } from "../constants";
import { mockBenchmarks } from "../mockData";
import { calcGpuEfficiency } from "../utils/metrics";
import { downloadJSON, downloadCSV, benchmarksToCSV } from '../utils/export';
import { useMockData } from "../contexts/MockDataContext";
import { useBenchmarkSelection } from "../contexts/BenchmarkSelectionContext";
import ErrorAlert from "../components/ErrorAlert";
import LoadingSpinner from "../components/LoadingSpinner";
import BenchmarkTable from "../components/BenchmarkTable";
import BenchmarkMetadataModal from "../components/BenchmarkMetadataModal";
import BenchmarkCompareCharts from "../components/BenchmarkCompareCharts";

export interface BenchmarkMetadata {
  model_identifier?: string | null;
  hardware_type?: string | null;
  runtime?: string | null;
  vllm_version?: string | null;
  replica_count?: number | null;
  notes?: string | null;
  extra?: Record<string, string>;
  source?: string | null;
}
export interface BenchmarkRunConfig { model?: string; [key: string]: unknown; }
export interface BenchmarkResultData {
  tps?: { mean?: number } | null;
  latency?: { p99?: number } | null;
  ttft?: { mean?: number } | null;
  rps_actual?: number;
  gpu_utilization_avg?: number | null;
  metrics_target_matched?: boolean;
}
export interface BenchmarkItem {
  id: string | number;
  name: string;
  timestamp: number;
  config?: BenchmarkRunConfig;
  result: BenchmarkResultData;
  metadata?: BenchmarkMetadata | null;
}
interface BenchmarkPageProps { isActive: boolean; onRerun?: (config: BenchmarkRunConfig) => void; }

function BenchmarkPage({ isActive, onRerun }: BenchmarkPageProps) {
  const [benchmarks, setBenchmarks] = useState<BenchmarkItem[]>([]);
  const { selectedIds: selected, setSelectedIds: setSelected } = useBenchmarkSelection();
  const [expanded, setExpanded] = useState<(string | number)[]>([]);
  const [editing, setEditing] = useState<BenchmarkItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { isMockEnabled } = useMockData();
  const [importing, setImporting] = useState(false);
  const importInputRef = useRef<HTMLInputElement>(null);

  const fetchBenchmarks = useCallback(() => {
    setLoading(true);
    if (isMockEnabled) {
      setBenchmarks(mockBenchmarks().map((b) => ({ ...b, config: b.config ? { ...b.config } : undefined })));
      setError(null);
      setLoading(false);
      return () => {};
    }
    const controller = new AbortController();
    authFetch(`${API}/benchmark/list`, { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(data => { setBenchmarks(data); setError(null); })
      .catch(err => {
        if (err instanceof Error && err.name === 'AbortError') return;
        console.error('Failed to fetch benchmarks:', err);
        setError(`Failed to fetch benchmarks: ${(err as Error).message}`);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [isMockEnabled]);

  useEffect(() => { if (isActive) { const cleanup = fetchBenchmarks(); return cleanup; } }, [isActive, fetchBenchmarks]);
  const toggleSelect = (id: string | number, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelected(selected.includes(id) ? selected.filter(x => x !== id) : [...selected, id]);
  };
  const toggleExpand = (id: string | number) =>
    setExpanded(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);

  const handleDelete = async (b: BenchmarkItem, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`Delete benchmark '${b.name}'?`)) return;
    if (isMockEnabled) {
      setBenchmarks(prev => prev.filter(x => x.id !== b.id));
      setSelected(selected.filter(x => x !== b.id));
      setExpanded(prev => prev.filter(x => x !== b.id));
      return;
    }
    try {
      const res = await authFetch(`${API}/benchmark/${b.id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSelected(selected.filter(x => x !== b.id));
      fetchBenchmarks();
    } catch (err) {
      console.error('Failed to delete benchmark:', err);
      setError(`Delete failed: ${(err as Error).message}`);
    }
  };

  const handleSaveMetadata = async (benchmarkId: string | number, metadata: BenchmarkMetadata) => {
    if (isMockEnabled) {
      setBenchmarks(prev => prev.map(b => b.id === benchmarkId ? { ...b, metadata } : b));
      setEditing(null);
      return;
    }
    try {
      const res = await authFetch(`${API}/benchmark/${benchmarkId}/metadata`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(metadata),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const updated: BenchmarkItem = await res.json();
      setBenchmarks(prev => prev.map(b => b.id === benchmarkId ? updated : b));
      setEditing(null);
    } catch (err) {
      console.error('Failed to save benchmark metadata:', err);
      setError(`Failed to save metadata: ${(err as Error).message}`);
    }
  };

  const handleBulkDelete = async () => {
    if (selected.length === 0) return;
    if (!window.confirm(`Delete ${selected.length} benchmark(s)?`)) return;
    if (isMockEnabled) { setBenchmarks(prev => prev.filter(b => !selected.includes(b.id))); setSelected([]); return; }
    try {
      for (const id of selected) {
        const res = await authFetch(`${API}/benchmark/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error(`HTTP ${res.status} for benchmark ID ${id}`);
      }
      setSelected([]);
      fetchBenchmarks();
    } catch (err) {
      console.error('Failed to bulk delete benchmarks:', err);
      setError(`Bulk delete failed: ${(err as Error).message}`);
    }
  };

  const handleExportJSON = () => {
    const data = selected.length > 0 ? benchmarks.filter(b => selected.includes(b.id)) : benchmarks;
    downloadJSON(data, `benchmarks-${new Date().getTime()}.json`);
  };
  const handleExportCSV = () => {
    const data = selected.length > 0 ? benchmarks.filter(b => selected.includes(b.id)) : benchmarks;
    const { headers, rows } = benchmarksToCSV(data);
    downloadCSV(headers, rows, `benchmarks-${new Date().getTime()}.csv`);
  };
  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true); setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const resp = await authFetch(`${API}/benchmark/import`, { method: "POST", body: formData });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setError(null); fetchBenchmarks();
      alert(`${data.imported_count} benchmark(s) imported successfully.`);
    } catch (err: unknown) {
      console.error('Failed to import benchmarks:', err);
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(false);
      if (importInputRef.current) importInputRef.current.value = "";
    }
  };
  const compareData = useMemo(() => benchmarks.filter(b => selected.includes(b.id)).map(b => {
    const gpuEff = calcGpuEfficiency(b.result);
    return {
      name: b.name, tps: b.result?.tps?.mean || 0, ttft: (b.result?.ttft?.mean || 0) * 1000,
      p99: (b.result?.latency?.p99 || 0) * 1000, rps: b.result?.rps_actual || 0,
      gpuEff: gpuEff.value || 0, metricsTargetMatched: !gpuEff.mismatch,
    };
  }), [benchmarks, selected]);

  return (
    <div className="flex-col-16">
      <ErrorAlert message={error} className="error-alert--mb8" />
      {loading && benchmarks.length === 0 ? (
        <LoadingSpinner />
      ) : (
        <>
          <BenchmarkTable
            benchmarks={benchmarks} selected={selected} expanded={expanded} loading={loading}
            importing={importing} importInputRef={importInputRef} onToggleSelect={toggleSelect}
            onToggleExpand={toggleExpand} onDelete={handleDelete} onEdit={setEditing}
            onExportJSON={handleExportJSON} onExportCSV={handleExportCSV}
            onImport={handleImport} onBulkDelete={handleBulkDelete} onRerun={onRerun}
          />
          {editing && (
            <BenchmarkMetadataModal editing={editing} onClose={() => setEditing(null)} onSave={handleSaveMetadata} />
          )}
          {compareData.length >= 2 && <BenchmarkCompareCharts compareData={compareData} />}
        </>
      )}
    </div>
  );
}
export default BenchmarkPage;
