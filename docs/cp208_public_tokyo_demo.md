# CP-208 — Public CarePath Tokyo demo

## Public product boundary

CarePath Tokyo is served from the same HTTPS origin as the backend. A reviewer can open `/tokyo` anonymously, choose English, Japanese or Chinese, describe a need, use browser location or a manual Tokyo municipality, and receive source-backed public resources without creating an account or uploading health data.

The Tokyo route is a public-resource navigator. It is not a diagnostic or clinical service.

## Production readiness

`GET /health/tokyo` is the Tokyo-specific readiness contract.

The endpoint returns HTTP 200 only when the canonical Tokyo resource corpus is loaded and deterministic resource search is available. It exposes model-provider status separately:

- `provider=ok`: optional model assistance is healthy;
- `provider=fallback`: the provider is unavailable, but deterministic source-backed search remains usable;
- missing/empty resource data: HTTP 503 because the product cannot safely fabricate replacement resources.

Render keeps the lightweight `/health/live` platform probe. CP-208's dedicated public acceptance requires `/health/tokyo` readiness before the Tokyo demo is considered deployable. The existing `/health/ready` remains the stricter full CarePath Core readiness probe.

## Privacy and location

The primary Tokyo journey does not require a longitudinal profile, wearable upload, CSV/JSON/FHIR import or account creation. Precise browser coordinates are used only for the current search and are not durably persisted by the Tokyo route. If location permission is denied or unavailable, the user can enter a Tokyo municipality manually.

## Deterministic judging/demo path

The UI includes a visible **demo scenario** section. The fixed cooling-shelter scenario selects Koto City (`江東区`) and can be used for judging, screenshots and video recording without granting browser geolocation.

Recommended deterministic path:

1. Open `/tokyo`.
2. Leave the interface in English or switch to Japanese/Chinese.
3. Choose the cooling-shelter demo scenario.
4. Confirm the selected Koto City demo area.
5. Select **Find help**.
6. Inspect the returned source-backed resource cards, source/freshness information and available action links.

The demo location is synthetic only as a user-location choice. Returned resources are still selected from the deployed canonical Tokyo open/public-data corpus and retain source provenance.

## Provider failure fallback

A model-provider failure must not make source-backed public-resource search unavailable. The agent falls back to bounded deterministic intent parsing for supported requests, runs CP-203 resource search, and omits generated explanation when necessary. It does not invent resource facts to compensate for a failed provider.

## Exact deployment verification

The public backend origin is recorded in `deployment/public_backend_url.txt`.

After a deployment is live, verify the exact commit and Tokyo path with:

```bash
python deployment/verify_backend.py \
  "$(cat deployment/public_backend_url.txt)" \
  --expected-commit "$(git rev-parse HEAD)" \
  --confirmations 3

python deployment/verify_tokyo_public.py \
  "$(cat deployment/public_backend_url.txt)" \
  --expected-commit "$(git rev-parse HEAD)" \
  --output /tmp/cp208-public-verification.json
```

The Tokyo verifier checks:

- process liveness;
- exact build identity when requested;
- Tokyo resource-data readiness;
- explicit provider `ok` or `fallback` state;
- anonymous `/tokyo` HTML availability;
- a real Koto cooling-shelter API search;
- non-empty stable resource IDs and source provenance.

## Browser acceptance

`apps/mobile/e2e/tokyo_public.spec.ts` runs against both the integrated Docker build and, after merge, the exact public Render deployment. It verifies:

- direct anonymous `/tokyo` loading;
- hard refresh/direct-route survival;
- EN/JA/ZH source-backed searches;
- deterministic Koto demo path;
- visible source facts;
- source and directions action URL schemes;
- optional website/telephone actions only when the source record exposes them.

The CP-208 Playwright configuration captures screenshots for every test. CI uploads screenshots, traces on failure, the HTTP verification report and deployment logs/evidence as artifacts.

## Acceptance command for a local production-style stack

```bash
docker compose --env-file deployment/.env.compose.example up -d --build --wait --wait-timeout 180
python deployment/verify_tokyo_public.py http://127.0.0.1:8000

cd apps/mobile
npm ci
npm install --no-save --package-lock=false @playwright/test@1.54.1
npx playwright install --with-deps chromium
CAREPATH_E2E_BASE_URL=http://127.0.0.1:8000 \
  npx playwright test --config=e2e/playwright.cp208.config.ts
```

Then tear the stack down with:

```bash
docker compose --env-file deployment/.env.compose.example down -v --remove-orphans
```

## Evidence and claim boundary

CP-208 evidence demonstrates deployment availability, deterministic resource grounding, privacy-preserving location handling, provider fallback and browser usability. It does not establish medical safety, clinical effectiveness or real-world health outcomes beyond the software safety/grounding contracts already tested in CP-205 and CP-207.
