# CP-202 — CarePath Tokyo multilingual journey contract

## Product statement

**CarePath Tokyo turns a natural-language public-health or support need plus a Tokyo location into grounded, actionable public-resource options without requiring a health-data upload or account.**

Tokyo has authoritative public-health and support resources, but people may not know the formal service name, may face language barriers, or may struggle to judge which nearby resource is relevant. CarePath Tokyo provides a bounded multilingual navigation layer while keeping resource facts traceable to official data.

This document freezes the product contract for CP-202. The machine-readable source of truth is [`data/tokyo/journeys.json`](../data/tokyo/journeys.json). Later API, agent and browser work must consume that fixture rather than redefine the scenarios independently.

## Frozen MVP categories

CP-202 retains the four categories already established by CP-201 and `docs/tokyo_scope.md`:

| Category | User outcome |
| --- | --- |
| `healthcare` | Find hospitals or clinics and use source-reported language support when available. |
| `cooling_shelter` | Find designated locations for non-urgent heat-risk navigation. |
| `family_support` | Reach public child/family support without knowing the formal service name. |
| `mental_health_support` | Reach non-emergency public mental-health/welfare support. |

The three judge/demo journeys below use the first three categories. `mental_health_support` remains in the product scope and can be exercised as a secondary journey; it is not removed merely to keep the primary demo to three scenarios.

## Primary input contract

The first useful result must require only:

1. a natural-language request;
2. interface language: English, Japanese or Chinese;
3. location from browser geolocation **or** a manual Tokyo location fallback.

No primary Tokyo journey may require account creation, profile creation, wearable data, CSV, JSON or FHIR upload.

## Three frozen primary scenarios

### 1. Multilingual healthcare access

**Scenario ID:** `tokyo-healthcare-language`

| Language | Frozen request |
| --- | --- |
| EN | I need a nearby clinic in Tokyo where staff can support me in English. |
| JA | 東京で、英語で対応してもらえる近くの診療所を探したいです。 |
| ZH | 我想在东京找一家附近可以用英语沟通的诊所。 |

Expected structured behavior:

- intent: `find_healthcare`;
- category: `healthcare`;
- required language: `en`;
- safety: `standard_navigation`;
- hard constraints: category and explicitly source-reported English support;
- unknown language support **does not** satisfy the language constraint;
- after hard constraints, rank deterministically by distance and stable ID/resource ID;
- if there is no explicit English-language match, return a no-match state rather than silently weakening the constraint.

Judge outcome: a nearby healthcare option with explicit source-reported English support, source/freshness visible, and an actionable next step when the relevant source field exists.

### 2. Location-sensitive heat resource

**Scenario ID:** `tokyo-heat-cooling-shelter`

| Language | Frozen request |
| --- | --- |
| EN | It is extremely hot. I need a nearby designated place where I can cool down. |
| JA | とても暑いので、近くの指定クーリングシェルターを探したいです。 |
| ZH | 天气非常热，我想找一个附近的指定避暑场所。 |

Expected structured behavior:

- intent: `find_cooling_shelter`;
- category: `cooling_shelter`;
- safety: `safety_check_then_navigation`;
- run the safety gate before ordinary resource navigation;
- category is a hard constraint;
- rank deterministically by distance and stable ID/resource ID;
- do not claim live opening, capacity or availability unless an authoritative source later supplies those fields.

Judge outcome: for a non-urgent request, show nearby designated cooling shelters with provenance. An urgent heat-related request follows the failure/safety contract below rather than ordinary ranking alone.

### 3. Public support without knowing the service name

**Scenario ID:** `tokyo-family-support-unknown-service`

| Language | Frozen request |
| --- | --- |
| EN | I am overwhelmed with childcare and do not know which Tokyo public service I should contact for family support. |
| JA | 育児で困っていますが、どの公的な相談先に連絡すればよいのか分かりません。 |
| ZH | 我在育儿方面遇到困难，但不知道应该联系东京的哪种公共支持服务。 |

Expected structured behavior:

- intent: `find_family_support`;
- category: `family_support`;
- safety: `standard_navigation`;
- user does not need to know the phrase “child/family support centre”;
- category is a hard constraint;
- rank deterministically by distance and stable ID/resource ID;
- all displayed contact/access/location facts remain bounded to the official resource record.

Judge outcome: ordinary language is mapped to a concrete family-support resource category and actionable official resource options.

## Result-card contract

Each card must distinguish **verified source facts** from **generated explanation**.

Verified/source-bounded fields include resource name, category, address, source-reported languages, source-reported opening/access information, phone/website and provenance. Distance and freshness are deterministic application-derived fields. `why_match` is generated explanation and may only explain facts/constraints already present in the verified/deterministic context.

The card contract is:

| Field | Origin | Rule |
| --- | --- | --- |
| name | verified source data | required |
| category | verified source data | required |
| distance | deterministic | hide when user/resource location is unavailable |
| address | verified source data | show unknown when absent |
| languages | verified source data | missing means unknown, never inferred |
| opening hours | verified source data | missing means unknown, never inferred |
| access notes | verified source data | hide when absent |
| freshness | deterministic from provenance | required; unknown is allowed |
| source | verified provenance | required |
| why it matches | generated explanation | must be visually/semantically labelled generated |

Actions are also evidence-bounded: directions require a verified address/coordinate, call requires a source phone number, and the official-source action requires provenance URL data.

## Failure and safety journeys

The same machine-readable fixture freezes five required failure cases:

1. **Location permission denied** — preserve the request and immediately offer manual Tokyo location; never force account/profile/upload.
2. **No matching resources** — return a structured empty state, identify the hard constraint and offer bounded adjustments; never invent a resource or silently relax a required language/category constraint.
3. **Incomplete resource data** — keep unknown language/opening/access/contact/location fields unknown and hide unsupported actions.
4. **Model unavailable/invalid** — preserve request/location and use a bounded deterministic or category fallback where possible; verified resource facts remain usable and unsupported generated explanation is omitted.
5. **Urgent or unsafe request** — deterministic safety handling runs before ordinary navigation. Urgent escalation guidance in the selected language cannot be replaced by a normal resource card.

## Shared acceptance fixture

`data/tokyo/journeys.json` is intentionally transport-neutral. It contains product inputs, three scenarios, all EN/JA/ZH requests, expected intent, filters, safety disposition, ranking contract, result-card contract and failure cases.

Backend tests consume it through `backend.tokyo.journeys.load_journey_catalog()`. Browser/Playwright work consumes the **same file** through `apps/mobile/e2e/tokyoFixtures.mjs`. This prevents the API and UI acceptance definitions from drifting apart.

The Python helper exports nine exact acceptance cases (`3 scenarios × 3 languages`) for CP-203/204 API tests. The Node helper exports the same nine variants for CP-206/207 browser E2E tests.

## Under-60-second judge story

Each frozen primary scenario has an explicit budget of less than 60 seconds. The intended judge path is:

`choose language → type/select the frozen request → use browser location or manual fallback → receive grounded ranked cards → inspect why-match + source/freshness → open an available next action`.

There is no persona loading, profile setup or health-file import in that path.

## Dependency boundary

CP-202 freezes expectations; it does not pretend later implementation already exists.

- CP-203 implements deterministic geospatial search/ranking against this contract.
- CP-204 implements bounded multilingual intent parsing/explanation against this contract.
- CP-205 applies Tokyo-specific safety/privacy enforcement.
- CP-206 implements the Tokyo-first web experience using these fixtures.
- CP-207 turns the same fixtures plus edge cases into the final evaluation/acceptance suite.
