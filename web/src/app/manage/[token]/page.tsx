import { notFound } from "next/navigation";

import RecommendationExperience from "./recommendation-client";
import { readPrivateEvent, readRecommendations } from "../../event-flow";
import "../../styles.css";

export const dynamic = "force-dynamic";

export default async function PrivateEventPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const [event, recommendation] = await Promise.all([
    readPrivateEvent(token),
    readRecommendations(token),
  ]);
  if (!event) notFound();

  return <RecommendationExperience token={token} event={event} initialRecommendation={recommendation} />;
}
