# CP-206 — Tokyo-first web experience

## Product boundary

CarePath Tokyo is a bounded public-resource navigator. A new visitor can open `/tokyo`, choose English, Japanese or Chinese, describe a need in natural language, provide the current browser location or a manual Tokyo municipality, and receive source-grounded public-resource options without creating an account or uploading health data.

CarePath Core remains available at `/`. The Tokyo route does not replace the existing longitudinal health-coaching reviewer.

## Primary journey

1. Open `/tokyo`.
2. Choose `English`, `日本語` or `中文`.
3. Describe the need or choose one of the frozen CP-202 examples.
4. Choose `Use current location` or enter a Tokyo municipality manually.
5. Select `Find help`.
6. Review deterministic/source-backed resource facts and any separately labelled grounded explanation.
7. Use directions, the official page, source record or telephone action only when the required source-backed field exists.

The three quick examples are the frozen CP-202 healthcare-language, cooling-shelter and family-support journeys. They can be completed without a profile, login, CSV, JSON, FHIR or wearable import.

## Location and privacy

Browser geolocation is requested only after the user explicitly selects the current-location action. The screen explains why location is needed before the permission request. If permission is denied or unavailable, manual municipality search remains functional.

The Tokyo API privacy contract is unchanged from CP-205:

- precise coordinates are used for the current request only;
- precise coordinates are not durably persisted by the Tokyo route;
- Tokyo free-text requests are not durably persisted by the Tokyo route;
- longitudinal health history is not required for the Tokyo primary journey.

## Grounding contract

Resource cards follow `data/tokyo/journeys.json` and preserve the CP-201 through CP-205 authority boundaries.

Source-backed or deterministic fields include resource name, category, address/location, distance, source-reported languages, published opening information, access notes, freshness, phone, website and provenance. Missing values remain unknown and are never converted into positive claims.

Generated match explanations are displayed in a separate `Grounded explanation` region. If model explanation selection is unavailable or invalid, the UI shows a model-fallback state and keeps source-backed resource facts usable.

Actions are conditional:

- directions require a verified address or coordinate;
- phone requires a source-reported telephone number;
- official page requires a source-reported website;
- a provenance/source action is exposed from the canonical source record.

## Safety and failure states

The UI implements explicit states for:

- locating;
- location permission denied/unavailable;
- searching;
- input validation;
- no match;
- incomplete official data;
- unavailable/invalid model assistance;
- network/API error with retry;
- clarification or unsupported intent;
- CP-205 urgent/emergency safety boundary.

Emergency or otherwise blocked requests do not render ordinary resource rankings. Safety references remain authoritative CP-205 references.

## Public deployment data

The production Docker image validates the CP-201 Tokyo source registry and rebuilds `data/tokyo/generated/resources.jsonl` from the five authoritative source definitions during image construction. The generated official-resource corpus is therefore present in the deployed API instead of relying on an absent local development artifact.

## Acceptance automation

`CP-206 Tokyo web experience` checks the Tokyo backend regression chain, frontend formatting/lint/typechecking, Tokyo API response-boundary tests and the Expo Web export.

The existing integrated/public reviewer Playwright gate additionally runs `e2e/tokyo_web.spec.ts`, which verifies:

- direct `/tokyo` entry without account UI or health-file import;
- a grounded resource result with visible provenance/freshness;
- EN/JA/ZH interface switching;
- denied browser geolocation followed by a successful manual-location journey on a mobile viewport;
- direct-route refresh;
- CP-205 safety escalation before ordinary results;
- navigation back to the unchanged CarePath Core reviewer.

The fixed CP-202 demo target remains under 60 seconds; CP-207 owns the broader final multilingual evaluation and reproducible metric report.
