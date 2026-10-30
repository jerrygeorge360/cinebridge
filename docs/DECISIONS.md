# Decisions

| Decision | Status | Rationale |
| --- | --- | --- |
| Independent `web/` and `api/` applications in one product repository | Approved | Clear deployment boundary without microservice overhead. |
| Next.js + TypeScript for web; FastAPI + Python for API | Approved | Product brief technology choice. |
| SQLite + SQLAlchemy on one persistent application instance | Approved | Sufficient for the MVP and simpler to operate. |
| Qloo is called from the backend only | Approved | Protect credentials and centralize recommendation policy. |
| Normalize ranks within each Qloo query; never mix incomparable raw affinity scores | Approved | Avoid invalid cross-query comparisons. |
| Penpot is the visual-design source of truth | Approved | Figma draft is unapproved reference material only. |
| Dark, warm independent-cinema direction | Approved | Establishes the brand starting point. |
| Organizer recommendation screen high-fidelity design | Pending production and human approval | The factory owns the phased Penpot production workflow; checkpoint metadata records when real boards exist. |
| Factory remains external to product runtime, tests, builds, and deployment | Approved | Keeps the product independently maintainable. |
| Bounded DeepSeek Film Programming Agent is advisory only | Pending review | It may inspect deterministic evidence and request one current-information search; it cannot alter eligibility, ranking, or constraints. |
| TMDB artwork is a deterministic cached backend integration | Pending review | Accurate posters improve scanability without granting the runtime another AI authority. |

Any material change to approved requirements, architecture, or brand direction requires an explicit human decision recorded here.
