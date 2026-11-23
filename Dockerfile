# syntax=docker/dockerfile:1
#
# One container holds everything: nginx (TLS), the API, and PostgreSQL 18 on a unix socket,
# supervised by s6. Built on Chainguard's Wolfi, which is rebuilt daily with fixes; every
# package is upgraded at build time, so nothing comes from a stale layer.
#
# Build:  docker build --target runtime -t blindspot .
# Run:    see compose.yaml (or .github/scripts/run-container.sh for the hardened flags)

# The base image is pinned by digest by Dependabot's docker updates (see docs/how-to/container.md).
ARG WOLFI_IMAGE=cgr.dev/chainguard/wolfi-base:latest

# ---- The web app ---------------------------------------------------------------------------
FROM ${WOLFI_IMAGE} AS web
ARG APK_REFRESH=dev
# Wolfi keeps only the current version of each package, so versions cannot be pinned here; the
# build is repeatable through the daily refresh and the digest-pinned base instead.
# hadolint ignore=DL3018
RUN echo "$APK_REFRESH" > /dev/null && apk add --no-cache nodejs-24 npm
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- The API's Python environment ---------------------------------------------------------
FROM ${WOLFI_IMAGE} AS python
ARG APK_REFRESH=dev
# hadolint ignore=DL3018
RUN echo "$APK_REFRESH" > /dev/null && apk add --no-cache python-3.14 uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON_PREFERENCE=only-system \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /src/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-build

# ---- The image that runs ------------------------------------------------------------------
FROM ${WOLFI_IMAGE} AS runtime
ARG RELEASE=dev
ARG COMMIT=unknown
ARG BUILT_AT=unknown
ARG APK_REFRESH=dev
ARG IMAGE_REFRESH=dev

# python: the API. nginx: TLS and the web app. postgresql-18: the database. s6: supervises the
# three. setpriv: drops each service to its own user. openssl: the first-start certificate.
# curl: the health check. All upgraded at build time.
# hadolint ignore=DL3018
RUN echo "$APK_REFRESH $IMAGE_REFRESH" > /dev/null \
    && apk upgrade --no-cache \
    && apk add --no-cache python-3.14 nginx-mainline nginx-mainline-mime-types postgresql-18 \
        s6 setpriv openssl curl ca-certificates-bundle \
    # One user per service. nginx reaches the API's socket through the blindspot group; the
    # API and the database share the pgsock group, which owns the database socket.
    && addgroup -S -g 10001 blindspot \
    && addgroup -S -g 10002 postgres \
    && addgroup -S -g 10003 nginx \
    && addgroup -S -g 10010 pgsock \
    && adduser -S -D -H -u 10001 -G blindspot -h /nonexistent -s /sbin/nologin blindspot \
    && adduser -S -D -H -u 10002 -G postgres -h /data/postgres -s /sbin/nologin postgres \
    && adduser -S -D -H -u 10003 -G nginx -h /nonexistent -s /sbin/nologin nginx \
    && adduser blindspot pgsock \
    && adduser postgres pgsock \
    && adduser nginx blindspot

COPY --from=python /opt/venv /opt/venv
COPY --from=web /src/frontend/dist /usr/share/blindspot/web
COPY backend/app /opt/blindspot/app
COPY docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY docker/nginx/security-headers.conf /etc/nginx/security-headers.conf
COPY docker/pg_hba.conf /etc/blindspot/pg_hba.conf
COPY --chmod=0755 docker/s6 /etc/s6/services
COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/blindspot-entrypoint
COPY --chmod=0755 docker/healthcheck.sh /usr/local/bin/blindspot-healthcheck

RUN /opt/venv/bin/python -m compileall -q /opt/blindspot/app

ENV BLINDSPOT_RELEASE=${RELEASE} \
    BLINDSPOT_ENVIRONMENT=production \
    PATH=/opt/venv/bin:/usr/local/bin:/usr/bin:/bin \
    PYTHONPATH=/opt/blindspot \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.revision=${COMMIT} \
      org.opencontainers.image.created=${BUILT_AT}

# 8080 redirects to https; 8443 is the app. Both are above 1024, so no capability is needed to
# bind them; publish them as 80 and 443 (compose.yaml does).
EXPOSE 8080 8443
VOLUME /data

HEALTHCHECK --interval=15s --timeout=8s --start-period=60s --retries=3 \
    CMD ["/usr/local/bin/blindspot-healthcheck"]

# The entrypoint and s6 run as root, and nothing else does: it prepares /data, then every service
# is started as its own unprivileged user with setpriv. The container is run with every
# capability dropped except the five that takes (see compose.yaml).
# hadolint ignore=DL3002
USER root
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/blindspot-entrypoint"]
