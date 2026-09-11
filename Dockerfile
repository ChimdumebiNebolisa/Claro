# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

FROM node:22.23.2-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 AS web-build

WORKDIR /build

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

COPY index.html postcss.config.mjs tsconfig.json tsconfig.node.json vite.config.ts ./
COPY public ./public
COPY src ./src
COPY tests ./tests

RUN npm run build


FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS openpdf-build

WORKDIR /build

COPY workers/openpdf/pom.xml ./pom.xml
RUN --mount=type=cache,target=/root/.m2 \
    mvn -q dependency:go-offline

COPY workers/openpdf/src ./src
RUN --mount=type=cache,target=/root/.m2 \
    mvn -q package -DskipTests


FROM python:3.11.16-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84 AS runtime

ARG VCS_REF="unknown"
ARG BUILD_DATE="unknown"
ARG SOURCE_URL="https://github.com/unknown/unknown"

LABEL org.opencontainers.image.title="Claros V2" \
    org.opencontainers.image.description="Claros V2 FastAPI and Vite service" \
    org.opencontainers.image.source="${SOURCE_URL}" \
    org.opencontainers.image.revision="${VCS_REF}" \
    org.opencontainers.image.created="${BUILD_DATE}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    CLAROS_ENVIRONMENT=production \
    CLAROS_STORAGE_BACKEND=gcs \
    JAVA_HOME=/opt/java/openjdk \
    PATH="/opt/java/openjdk/bin:${PATH}"

WORKDIR /app

RUN groupadd --gid 10001 claros \
    && useradd --uid 10001 --gid 10001 --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin claros

RUN apt-get update \
    && apt-get install --yes --no-install-recommends fontconfig libfreetype6 qpdf \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-server.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --require-hashes --only-binary=:all: \
        --requirement requirements-server.txt

COPY --chown=0:0 backend ./backend
COPY --chown=0:0 assets ./assets
COPY --chown=0:0 public ./public
COPY --chown=0:0 scripts/gate3-container-entrypoint.py ./scripts/gate3-container-entrypoint.py
COPY --from=openpdf-build --chown=0:0 /opt/java/openjdk /opt/java/openjdk
COPY --from=openpdf-build --chown=0:0 \
    /build/target/claros-openpdf-worker-0.1.0-SNAPSHOT-all.jar \
    ./workers/openpdf/target/claros-openpdf-worker-0.1.0-SNAPSHOT-all.jar
COPY --from=web-build --chown=0:0 /build/dist ./dist

USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import json, os, urllib.request; response = urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8080') + '/health', timeout=4); assert response.status == 200 and json.load(response) == {'status': 'ok'}"]

ENTRYPOINT ["python", "scripts/gate3-container-entrypoint.py"]
