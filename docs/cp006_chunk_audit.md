# CP-006 Manual Evidence Chunk Audit

**Audit date:** 2026-07-29  
**Scope:** manual content-quality review complementing the deterministic `audit_chunks` and
reproducibility tests.

## Method

The reviewer inspected chunk-sized source segments from official pages across all CP-006
content categories. Review focused on the properties that require semantic inspection:

- main-content text is distinguishable from site navigation, footer, share, and related-link
  noise;
- headings describe the following evidence and can support section-aware chunking;
- numerical recommendations, age/time ranges, conditions, and units remain meaningful;
- negative or cautionary language is not converted into positive advice;
- professional-help or escalation language remains visible where present;
- title, organisation, canonical page, and page date/review date agree with the registry where
  the page exposes them.

Stable `source_id`, `chunk_id`, hash, ordering, overlap, and serialized metadata are checked by
automated repeated-run tests rather than manual visual comparison. The CLI also emits a
machine-readable `chunk_audit.json` for any built corpus containing at least 30 chunks.

No `metadata_only` source body was copied into this audit.

## Reviewed sources

| Source ID | Source | CP-006 areas represented |
|---|---|---|
| `src-e979225fc93f357e` | CDC — Adult Activity: An Overview | physical activity |
| `src-8bb86ecca979ff97` | CDC — About Sleep | sleep, professional help |
| `src-b37974b937669d8f` | NHLBI/NIH — Healthy Sleep Habits | sleep, professional help |
| `src-96bfea7cb444be56` | CDC — Managing Stress | stress management, professional help |
| `src-369786fa43381315` | CDC — Preventing Falls and Hip Fractures | fall prevention, professional help |
| `src-9c8a9578dc976362` | NIDDK/NIH — Changing Your Habits for Better Health | behaviour change, physical activity |
| `src-ab46b043dc231540` | NIMH/NIH — Help for Mental Illnesses | professional help |
| `src-2f96ac370430c274` | NIA/NIH — Falls and Fractures in Older Adults | fall prevention, physical activity, professional help |

## 32 reviewed chunk-sized units

| # | Source | Section/content unit | Result |
|---:|---|---|---|
| 1 | CDC Adult Activity | key points and weekly activity framing | pass |
| 2 | CDC Adult Activity | adult aerobic recommendation and alternatives | pass |
| 3 | CDC Adult Activity | muscle-strengthening recommendation | pass |
| 4 | CDC Adult Activity | `move more, sit less` qualification | pass |
| 5 | CDC About Sleep | sleep-quality and enough-sleep key points | pass |
| 6 | CDC About Sleep | age-dependent sleep-duration table | pass |
| 7 | CDC About Sleep | adult 18–60 sleep-duration row | pass |
| 8 | CDC About Sleep | professional-help statement for sleep problems | pass |
| 9 | NHLBI Healthy Sleep | regular bed/wake schedule | pass |
| 10 | NHLBI Healthy Sleep | weekday/weekend schedule consistency | pass |
| 11 | NHLBI Healthy Sleep | pre-bed quiet time and bright-light caution | pass |
| 12 | NHLBI Healthy Sleep | shift-worker adaptation and professional-help boundary | pass |
| 13 | CDC Managing Stress | stress as a common response | pass |
| 14 | CDC Managing Stress | distinction between occasional and long-term stress | pass |
| 15 | CDC Managing Stress | routine stress-management framing | pass |
| 16 | CDC Managing Stress | resources/support when coping is difficult | pass |
| 17 | CDC Preventing Falls | clinician fall-risk review | pass |
| 18 | CDC Preventing Falls | medicine review for dizziness/sleepiness | pass |
| 19 | CDC Preventing Falls | strength and balance exercise section | pass |
| 20 | CDC Preventing Falls | hip-fracture seriousness and prevention framing | pass |
| 21 | NIDDK Changing Habits | contemplation/preparation/action/maintenance stages | pass |
| 22 | NIDDK Changing Habits | preparation and specific-goal setting | pass |
| 23 | NIDDK Changing Habits | small-change example and feasible first step | pass |
| 24 | NIDDK Changing Habits | progress tracking and setback handling | pass |
| 25 | NIMH Help | immediate-help boundary | pass |
| 26 | NIMH Help | finding a health-care provider or treatment | pass |
| 27 | NIMH Help | evaluating provider fit | pass |
| 28 | NIMH Help | treatment-change caution and informational-use boundary | pass |
| 29 | NIA Falls | fall preventability and risk context | pass |
| 30 | NIA Falls | physical activity plus strength/balance prevention actions | pass |
| 31 | NIA Falls | medication, vision/hearing, and home/environment risk controls | pass |
| 32 | NIA Falls | reporting a fall and obtaining help after a fall | pass |

## Findings

### Content integrity

All reviewed units retained the meaning of numerical recommendations, conditions, and
professional-help boundaries. Negative/cautionary statements remained negative/cautionary; no
reviewed unit inverted advice such as `do not`, `if`, `when`, or equivalent safety qualifiers.

### Template noise

Official pages can contain substantial navigation and related-content text outside the main
article. This audit directly motivated the HTML parser regression rule that prefers `<main>` or
`<article>` roots when present and falls back to document-level parsing only when neither root
exists. A dedicated automated test covers menu-like `<div>` content both before and after the
main body.

### Structure

The reviewed pages use headings that correspond to coherent recommendation or explanation
sections. The section-aware parser/chunker therefore retains heading context rather than
separating titles from evidence through fixed-character slicing.

### Licensing

The manual content review uses sources whose registry policy allows text or derived-chunk
processing. AASM and NICE entries marked `metadata_only` were intentionally excluded from body
review and remain metadata/link-only in the ingestion path.

## Acceptance disposition

Manual semantic QA: **pass (32 units across 8 sources).**  
Automated generated-chunk audit: **pass (minimum 30 chunks enforced).**  
Repeated-run ID/hash/order/content reproducibility: **pass in CI test suite.**
