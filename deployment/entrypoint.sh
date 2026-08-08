#!/bin/sh
set -eu

python -m alembic upgrade head

exec uvicorn backend.api.app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="*"
