# Bike Log server image: the same app as the desktop version, started in server mode (Google sign-in).
# Built on the server by deploy/install.sh and deploy/update.sh:  docker compose -f deploy/compose.yml build
# Build context is the repository root.

# ---- screens (React) ----
FROM node:22-alpine AS screens
ARG BIKELOG_COMMIT=unknown
ENV BIKELOG_COMMIT=${BIKELOG_COMMIT}
WORKDIR /src
COPY backend/bikelog/__init__.py backend/bikelog/__init__.py
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci --no-audit --no-fund
COPY frontend frontend
RUN cd frontend && npm run build

# ---- app (Python) ----
FROM python:3.12-slim
ARG BIKELOG_COMMIT=unknown
ARG BIKELOG_VERSION=""
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    BIKELOG_SERVER=1 BIKELOG_HOST=0.0.0.0 BIKELOG_PORT=8765 BIKELOG_DATA_DIR=/data TZ=Europe/Berlin
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY backend backend
COPY --from=screens /src/frontend/dist frontend/dist
# which commit is running (Settings shows it); written here because the image has no .git
RUN echo "${BIKELOG_COMMIT}" > backend/bikelog/build_commit.txt \
    && if [ -n "${BIKELOG_VERSION}" ]; then echo "${BIKELOG_VERSION}" > backend/bikelog/build_version.txt; fi \
    && useradd --system --uid 10001 --home-dir /data bikelog \
    && mkdir -p /data && chown bikelog /data
USER bikelog
ENV PYTHONPATH=/app/backend
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=4).status == 200 else 1)"
CMD ["python", "-m", "bikelog", "--server", "--no-browser"]
