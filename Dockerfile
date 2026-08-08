FROM node:22-bookworm-slim AS reviewer-web

WORKDIR /web

COPY apps/mobile/package.json apps/mobile/package-lock.json ./
RUN npm ci

COPY apps/mobile ./
ENV EXPO_PUBLIC_CAREPATH_API_URL=__CAREPATH_SAME_ORIGIN__ \
    EXPO_PUBLIC_CAREPATH_MOCK_MODE=false
RUN npm run bundle:web

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    CAREPATH_REVIEWER_WEB_DIR=/app/reviewer_web

WORKDIR /app

RUN addgroup --system carepath \
    && adduser --system --ingroup carepath --home /home/carepath carepath

COPY pyproject.toml alembic.ini ./
COPY alembic ./alembic
COPY backend ./backend
COPY deployment/entrypoint.sh ./deployment/entrypoint.sh
COPY --from=reviewer-web /web/dist/web-smoke ./reviewer_web

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && chmod +x /app/deployment/entrypoint.sh \
    && mkdir -p /app/data/guidelines/qdrant \
    && chown -R carepath:carepath /app /home/carepath

USER carepath

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3).read()" || exit 1

ENTRYPOINT ["/app/deployment/entrypoint.sh"]
