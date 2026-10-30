import { notFound } from "next/navigation";

import { readPublicEvent } from "../../event-flow";
import RegistrationForm from "./registration-form";
import "../../styles.css";

export const dynamic = "force-dynamic";

export default async function PublicEventPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const event = await readPublicEvent(token);
  if (!event) notFound();

  return (
    <main className="site-shell">
      <header className="topbar">
        <a className="wordmark" href="/">CineBridge</a>
        <p className="context-tag"><span aria-hidden="true" /> Guest access · Public</p>
      </header>
      <section className="handoff-layout" aria-labelledby="public-event-title">
        <div className="handoff-intro">
          <p className="eyebrow">You are invited</p>
          <h1 id="public-event-title">{event.name}</h1>
          <p className="lede">{event.theme}. Your host has made a little room for every taste.</p>
        </div>
        <div>
          <div className="event-summary">
            <p className="kicker">Screening details</p>
            <h2>{event.screening_date}</h2>
            <p>{event.essential_details}</p>
          </div>
          <RegistrationForm token={token} />
        </div>
      </section>
    </main>
  );
}
