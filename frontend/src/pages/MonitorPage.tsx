import { useMonitorLogic } from "../hooks/useMonitorLogic";
import ErrorAlert from "../components/ErrorAlert";
import LoadingSpinner from "../components/LoadingSpinner";
import MultiTargetSelector from "../components/MultiTargetSelector";
import MonitorChartGrid from "../components/MonitorChartGrid";

// Re-export for backwards compatibility (tests import from this module)
export { buildChartLinesMap } from "../components/MonitorChartGrid";

const TIME_RANGES = [
  { label: 'Live' as const, points: 60 },
  { label: '1h' as const,  points: 360, timeRange: '1h' },
  { label: '6h' as const,  points: 720, timeRange: '6h' },
  { label: '24h' as const, points: 1000, timeRange: '24h' },
  { label: '7d' as const,  points: 1400, timeRange: '7d' },
];

function MonitorPage({ isActive }: { isActive: boolean }) {
  const {
    initialized, error, targets, slaProfiles,
    selectedSlaProfileId, setSelectedSlaProfileId,
    chartOrder, hiddenCharts, mergedHistory, targetStatuses, targetStates,
    chartLinesMap, hideChart, showChart, getSlaThreshold,
    selectedRange, setSelectedRange, setTimeRangePoints,
    timeRangePointsRef, selectedRangeRef,
  } = useMonitorLogic(isActive);

  return (
    <div className="flex-col-1">
      <div className="panel flex-row-12" style={{ padding: '12px 20px', borderBottom: 'none', marginBottom: '-1px', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="label label-no-mb">SLA PROFILE:</span>
          <select
            className="input"
            style={{ width: '200px', padding: '4px 8px' }}
            value={selectedSlaProfileId || ''}
            onChange={(e) => setSelectedSlaProfileId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">None (disable warning)</option>
            {slaProfiles.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          {TIME_RANGES.map(r => (
            <button
              key={r.label}
              type="button"
              data-testid="time-range-btn"
              aria-label={`Show last ${r.label}`}
              className={`btn btn-sm${selectedRange === r.label ? ' active' : ''}`}
              onClick={() => {
                setTimeRangePoints(r.points);
                setSelectedRange(r.label);
                timeRangePointsRef.current = r.points;
                selectedRangeRef.current = r.label;
              }}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      {!initialized && targets.length > 0 ? (
        <LoadingSpinner />
      ) : (
        <>
          <MultiTargetSelector
            targetStatuses={targetStatuses}
            targetStates={targetStates}
          />
          <ErrorAlert message={error} className="error-alert--m08" />
          <MonitorChartGrid
            visibleCharts={chartOrder.filter(id => !hiddenCharts.includes(id))}
            hiddenCharts={hiddenCharts}
            chartData={mergedHistory}
            chartLinesMap={chartLinesMap}
            onHideChart={hideChart}
            onShowChart={showChart}
            getSlaThreshold={getSlaThreshold}
            timeRange={selectedRange}
          />
        </>
      )}
    </div>
  );
}
export default MonitorPage;
