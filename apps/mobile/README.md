# Mobile app

This is the canonical shared React Native/Expo application boundary for B Core and future extension tracks. There is no second top-level mobile application directory.

## Application routes

The Expo/TypeScript application exposes four bottom-tab destinations:

- **Today** — API connection status, selected demo persona, 7-day sleep/activity/resting-heart-rate/stress summaries, 30-day comparison and today's plan action;
- **Coach** — bounded coaching request, safe stage-status display, six-section structured answer, Patient Evidence, External Evidence, exact chunks and citations;
- **Health Data** — two built-in personas, raw 7/30/60-day observation charts, coverage/missingness, suspect-record visibility and CSV/JSON import reports;
- **Plan & History** — active seven-day plan plus accept/reject/complete feedback.

The app deliberately uses neutral data-quality styling. Coverage, reliability, missingness and suspect-record labels describe source data only and are not medical classifications.

## Environment

Copy `.env.example` to `.env` when local values are needed.

```bash
EXPO_PUBLIC_CAREPATH_API_URL=http://127.0.0.1:8000
EXPO_PUBLIC_CAREPATH_MOCK_MODE=false
```

`EXPO_PUBLIC_CAREPATH_API_URL` is the FastAPI base URL. `127.0.0.1` works for Expo Web and local simulators when the backend is on the same machine. Expo Go on a physical device must use a backend address reachable from that device, normally the development computer's LAN address.

Set `EXPO_PUBLIC_CAREPATH_MOCK_MODE=true` for the complete local synthetic journey without a backend. Mock mode preserves the same screen contracts: health status, profile, trends, raw observations, import report, coaching response, evidence, plan and feedback.

The production Docker build uses the internal marker `__CAREPATH_SAME_ORIGIN__`. The runtime resolves that marker to relative API requests, allowing FastAPI to serve the Expo Web bundle and API from the same deployment origin without a browser CORS dependency. This marker is deployment plumbing and normally should not be placed in a developer `.env` file.

## Development

From the repository root:

```bash
npm --prefix apps/mobile ci
npm --prefix apps/mobile start
```

Expo shortcuts:

```bash
npm --prefix apps/mobile run ios
npm --prefix apps/mobile run android
npm --prefix apps/mobile run web
```

The default `start` command opens the managed Expo development server used by Expo Go. The Web command starts the same universal application through Expo Web/Metro.

The runtime API client is configured through `EXPO_PUBLIC_CAREPATH_API_URL`. Backend controlled errors preserve `code`, `message` and `request_id`; malformed HTTP and transport failures become bounded client errors. Screen state explicitly represents idle, loading, success, empty and error conditions.

## Reviewer deployment

The production `Dockerfile` performs a locked Expo Web export in a Node build stage, copies the result into the Python runtime image, and configures FastAPI to serve it at `/`. Consequently the deployed backend origin is also the reviewer-facing Web URL. API routes such as `/health/ready`, `/docs` and `/openapi.json` remain on the same host.

For a production-equivalent local reviewer run:

```bash
cp deployment/.env.compose.example deployment/.env.compose
docker compose --env-file deployment/.env.compose up --build --wait
# Open http://127.0.0.1:8000/
```

For a frontend-only fallback when Docker or the cloud backend is unavailable:

```bash
npm --prefix apps/mobile ci
EXPO_PUBLIC_CAREPATH_MOCK_MODE=true npm --prefix apps/mobile run web
```

The fallback is useful for presentation continuity but does not replace the CP-020 real-backend acceptance gate.

## Demo path

1. Open **Today** and confirm `/health` connection status.
2. Select either built-in synthetic persona and load the package.
3. Compare all four 7-day summaries against the API-provided 30-day means and review today's action.
4. Open **Health Data**, switch metric and 7/30/60-day ranges, then inspect missing days and suspect observations without interpolation.
5. Paste a CSV or project JSON package to inspect the backend validation report, including fixed issues, skipped records and blocking errors.
6. Open **Coach**, ask the prepared or edited health-behaviour question, inspect the structured six-section answer, Patient Evidence and expandable External Evidence chunks.
7. Open **Plan & History** and record feedback on a plan action.

No API console is required for this path. Demo scenarios generate fresh synthetic UUIDs when the app loads so separate browser sessions do not intentionally reuse the same user identifiers.

## Quality gates

```bash
npm --prefix apps/mobile run format:check
npm --prefix apps/mobile run lint
npm --prefix apps/mobile run typecheck
npm --prefix apps/mobile run expo:check
npm --prefix apps/mobile run bundle:check
npm --prefix apps/mobile run bundle:web
npm --prefix apps/mobile run test:ci
```

`expo:check` validates Expo configuration. `bundle:check` performs an iOS JavaScript export, and `bundle:web` performs an Expo Web static export using Metro. Repository quality CI runs both bundle targets before Jest so native/Expo Go-compatible application code and the reviewer-facing Web build are validated from the locked dependency set.

`.github/workflows/cp020-reviewer-client.yml` additionally builds the production Docker image, opens the integrated reviewer root and executes the recorded Playwright primary journey against the real containerized backend. After a relevant change reaches `main`, it waits for the public Render deployment and runs the same journey against the recorded public origin.

The `brace-expansion` override pins the patched `5.0.8` release while upstream Jest and ESLint dependency ranges still admit affected older versions. Recheck the override with `npm audit --prefix apps/mobile` when updating the lockfile.
