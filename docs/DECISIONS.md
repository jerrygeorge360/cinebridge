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
| Organizer recommendation screen high-fidelity design | Pending human approval | No Penpot screen exists yet. |
| Factory remains external to product runtime, tests, builds, and deployment | Approved | Keeps the product independently maintainable. |

Any material change to approved requirements, architecture, or brand direction requires an explicit human decision recorded here.
