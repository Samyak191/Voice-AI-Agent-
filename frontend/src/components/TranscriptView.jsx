export default function TranscriptView({ interim, finals }) {
  return (
    <section className="panel panel--transcript">
      <header className="panel__header">
        <span>transcript</span>
      </header>
      {interim && <p className="transcript__interim">{interim}</p>}
      <ol className="transcript__log">
        {finals.map((text, i) => (
          <li key={i}>
            <span className="transcript__index">{String(i + 1).padStart(2, "0")}</span>
            <span>{text}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}