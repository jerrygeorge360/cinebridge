export default function Home() {
  return (
    <main>
      <header>
        <p className="eyebrow">CineBridge</p>
        <p className="phase">Pre-show / foundation</p>
      </header>
      <section aria-labelledby="setup-title">
        <p className="kicker">House lights down. The choice stays human.</p>
        <h1 id="setup-title">A shared screen starts by listening.</h1>
        <p className="lede">
          CineBridge is taking shape for film groups with different tastes. Product flows
          begin after the organizer recommendation screen is designed in Penpot and approved.
        </p>
        <div className="status" role="status">
          <span aria-hidden="true" />
          Setup complete · design checkpoint pending
        </div>
      </section>
    </main>
  );
}
