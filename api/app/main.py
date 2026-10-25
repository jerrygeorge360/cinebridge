from fastapi import FastAPI

app = FastAPI(
    title="CineBridge API",
    summary="Backend boundary for the CineBridge product.",
    version="0.1.0",
)


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}

