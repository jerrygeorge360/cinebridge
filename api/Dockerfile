FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
# Run the source directly from /app.  Installing the declared runtime
# dependencies avoids a PEP 517 build backend download, which is unavailable
# in the local Docker package index.
RUN pip install --no-cache-dir \
    "alembic>=1.14,<2" \
    "fastapi>=0.115,<1" \
    "sqlalchemy>=2.0,<3" \
    "uvicorn[standard]>=0.34,<1"
RUN adduser --system --uid 1001 cinebridge \
    && mkdir -p /data \
    && chown -R cinebridge /data
USER cinebridge
EXPOSE 8000
CMD ["python", "-m", "app.start"]
