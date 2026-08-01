# Backend

## Install

Run from the repository root:

```bash
python -m pip install -e '.[dev]'
```

## Development startup

```bash
python -m uvicorn backend.api.app.main:app --reload --no-access-log
```

The health check is available at `GET /health`.

Configuration is loaded through Pydantic Settings using `CAREPATH_`-prefixed
environment variables. To load an explicit environment file:

```bash
export CAREPATH_ENV_FILE=/absolute/path/to/carepath.env
```

Start from `.env.example`, keep the real file untracked, and never commit
secrets. `CAREPATH_LLM_PROVIDER=mock` is the default development provider.
