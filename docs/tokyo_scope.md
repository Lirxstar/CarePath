# CarePath Tokyo scope

## Purpose

CarePath Tokyo is a bounded extension for **multilingual public-health resource navigation**. It helps a user describe a public-health or support need in natural language and navigate to relevant, authoritative Tokyo resources.

The Tokyo extension is not a general civic assistant and does not revive the earlier broad "Tokyo Civic Copilot" direction. New Tokyo features should remain within public-health or closely related public-support resource navigation.

This document records the scope that is already implemented by CP-201. It does **not** narrow or remove any of the current Tokyo resource categories.

## Current resource scope

The implemented Tokyo resource layer contains four bounded categories:

| Category | Role in CarePath Tokyo | Current authoritative source |
| --- | --- | --- |
| `healthcare` | Navigate to hospitals and clinics; show source-reported language support when present | MHLW Medical Information Net open data |
| `cooling_shelter` | Navigate to designated heat-risk cooling locations | Koto City via Tokyo Open Data Catalog |
| `family_support` | Navigate users to child and family public-support services when they do not know the formal service name | Tokyo Bureau of Social Welfare |
| `mental_health_support` | Navigate to non-emergency public mental-health and welfare support | Tokyo Bureau of Social Welfare |

The machine-readable source inventory remains `data/tokyo/sources.json`. The ingestion, normalization, provenance, freshness and quality behavior is documented in `data/tokyo/README.md` and implemented under `backend/tokyo/`.

## Representative user journeys

These journeys are examples of the current product scope, not separate products and not an exhaustive list.

### Heat-risk navigation

A Koto City resident says that hot weather is making them feel dizzy or unusually tired.

CarePath should:

1. provide a conservative safety-oriented response without diagnosing the cause;
2. distinguish urgent red-flag situations from non-urgent resource navigation;
3. for a non-urgent situation, surface relevant nearby `cooling_shelter` resources when location information is available;
4. if symptoms persist, worsen, or the user wants professional help, offer relevant `healthcare` resources;
5. preserve source provenance and avoid claiming real-time opening, capacity or acceptance status unless a future authoritative source explicitly supports such claims.

### Healthcare navigation

A user asks for a nearby hospital or clinic and may prefer support in a particular language.

CarePath should return suitable `healthcare` resources and may display language support only when it is explicitly reported by the authoritative source. Missing language data must remain unknown rather than being inferred.

### Family-support navigation

A user describes a child or family support need but does not know the formal public-service name.

CarePath should map the need to relevant `family_support` resources without expanding into arbitrary municipal-service search.

### Mental-health support navigation

A user asks for non-emergency public mental-health or welfare support.

CarePath should surface relevant `mental_health_support` resources. Emergency or crisis handling belongs to the safety layer rather than ordinary resource ranking.

## Product boundaries

CarePath Tokyo is intentionally bounded. It does not provide:

- general-purpose Tokyo government or civic information search;
- arbitrary web search presented as authoritative public-health guidance;
- diagnosis, treatment decisions or medication advice;
- guarantees that a facility is open, has capacity or is accepting patients in real time;
- inferred language support, opening hours, accessibility or services when the source does not report them;
- storage of user health history or precise user location as part of the Tokyo ingestion layer;
- ingestion or redistribution of sources without an explicit reusable-data basis.

## Multilingual behavior

The product may accept and present navigation interactions in multiple languages, but resource facts remain source-bounded. In particular, CarePath must not convert missing language metadata into a claim that a service supports a language.

Translation of resource names or descriptions, when added at the product layer, should remain distinguishable from source-reported language support.

## Data and provenance requirements

Tokyo resources should continue to use the CP-201 canonical resource contract, including deterministic IDs, bounded categories, addresses, optional coordinates and municipality, source-reported contact/access/language/opening fields, freshness and data-quality flags, and provenance records.

Source inventory entries should retain enough information to reproduce and audit the data path, including publisher, source or catalogue URL, licence, source date, retrieval date, geographic coverage, adapter and freshness policy. Known source limitations should remain visible through provenance or quality metadata rather than being silently corrected.

## Scope-change rule

A new Tokyo dataset or feature should be added only when it clearly supports the same bounded public-health/resource-navigation product. The current four categories do not need to be reduced to satisfy an older "first 1-3 datasets" planning constraint.

Potential future categories such as AED or additional public-health institutions may be considered when they strengthen an existing user journey and have a sufficiently authoritative, reusable and maintainable source. They are not required for the current scope.

## Relationship to CP-201

CP-201 established the current authoritative Tokyo data layer and remains the implementation baseline. This document formalizes that existing product boundary so that future development does not accidentally expand CarePath Tokyo into a generic civic copilot or unnecessarily remove already implemented resource categories.
