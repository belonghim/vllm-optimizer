function LoadTestConfig({ config, onChange, onSubmit, onStop, isRunning, status }) {
  return (
    <div className="panel">
      <div className="section-title">부하 테스트 설정</div>
      <div className="grid-form grid-form-compact">
        {[
          ["vLLM Endpoint", "endpoint", "text"],
          ["Total Requests", "total_requests", "number"],
          ["Concurrency", "concurrency", "number"],
          ["RPS (0=unlimited)", "rps", "number"],
          ["Max Tokens", "max_tokens", "number"],
        ].map(([label, key, type]) => (
          <div key={key}>
            <label className="label">{label}</label>
            <input
              className="input"
              type={type}
              aria-label={label}
              value={config[key]}
              onChange={e => onChange(key, type === "number" ? +e.target.value : e.target.value)}
            />
          </div>
        ))}
        <div>
          <label className="label">프롬프트 템플릿</label>
          <textarea
            className="input loadtest-config-textarea"
            aria-label="프롬프트 템플릿"
            rows={3}
            value={config.prompt_template}
            onChange={e => onChange("prompt_template", e.target.value)}
          />
        </div>
        <div>
          <label className="label">Temperature</label>
          <input
            className="input"
            type="number"
            step="0.1"
            min="0"
            max="2"
            aria-label="Temperature"
            value={config.temperature}
            onChange={e => onChange("temperature", +e.target.value)}
          />
        </div>
      </div>

      <div className="loadtest-stream-toggle">
        <input type="checkbox" id="stream" checked={config.stream}
          onChange={e => onChange("stream", e.target.checked)} />
        <label htmlFor="stream" className="label label-no-mb">
          Streaming Mode (TTFT 측정 활성화)
        </label>
      </div>

      <div className="loadtest-config-actions">
        <button className="btn btn-primary" onClick={onSubmit} disabled={isRunning}>
          ▶ Run Load Test
        </button>
        <button className="btn btn-danger" onClick={onStop} disabled={!isRunning}>
          ■ Stop
        </button>
        <span className={`tag tag-${status}`}>{status.toUpperCase()}</span>
      </div>
    </div>
  );
}

export default LoadTestConfig;
