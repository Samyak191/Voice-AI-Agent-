const STAGE_ORDER = [
  { key: "stt_final", label: "stt", from: null },
  { key: "llm_request_sent", label: "debounce", from: "stt_final" },
  { key: "llm_first_token", label: "llm", from: "llm_request_sent" },
  { key: "tts_first_audio", label: "tts", from: "llm_first_token" },
];

function buildStages(data) {
  const stages = [];
  let prev = 0;

  for (const stage of STAGE_ORDER) {
    if (!(stage.key in data)) continue;
    const value = data[stage.key];
    const duration = Math.max(0, value - prev);
    stages.push({ label: stage.label, duration, cumulative: value });
    prev = value;
  }

  return stages;
}

export default function LatencyPanel({ data }) {
  if (!data) {
    return (
      <section className="panel panel--signal">
        <header className="panel__header">
          <span>signal</span>
        </header>
        <p className="signal__empty">no reading yet</p>
      </section>
    );
  }

  const stages = buildStages(data);
  const total = stages.length ? stages[stages.length - 1].cumulative : 0;

  return (
    <section className="panel panel--signal">
      <header className="panel__header">
        <span>signal</span>
      </header>

      <p className="latency-total">
        {total}
        <small>ms to first audio</small>
      </p>

      <div className="latency-bar">
        {stages.map((stage) => (
          <div
            key={stage.label}
            className={`latency-bar__segment latency-bar__segment--${stage.label}`}
            style={{ flexGrow: Math.max(stage.duration, 1) }}
          />
        ))}
      </div>

      <ul className="latency-legend">
        {stages.map((stage) => (
          <li key={stage.label}>
            <span className={`latency-legend__swatch latency-legend__swatch--${stage.label}`} />
            <span className="latency-legend__label">{stage.label}</span>
            <span className="latency-legend__value">{stage.duration}ms</span>
          </li>
        ))}
      </ul>
    </section>
  );
}