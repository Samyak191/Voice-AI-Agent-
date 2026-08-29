export default function ResponseView({ text }) {
  return (
    <section className="panel panel--response">
      <header className="panel__header">
        <span>response</span>
      </header>
      <p className="response__text">{text || "—"}</p>
    </section>
  );
}