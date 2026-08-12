# CarePath Tokyo open-data layer (CP-201)

This directory defines the bounded authoritative data inventory used by the CarePath Tokyo extension. The primary Tokyo journey does **not** require a user to upload wearable, CSV, JSON, FHIR, or other personal health data.

## Frozen MVP categories

| Category | Purpose | Authoritative source |
| --- | --- | --- |
| `healthcare` | Find hospitals/clinics, including source-reported language support where present | MHLW Medical Information Net open data |
| `cooling_shelter` | Location-sensitive heat-risk support | Koto City via Tokyo Open Data Catalog |
| `family_support` | Help users who do not know the formal public-service name find child/family support | Tokyo Bureau of Social Welfare |
| `mental_health_support` | Non-emergency public mental-health/welfare navigation | Tokyo Bureau of Social Welfare |

The scope is intentionally small. CP-201 does not ingest arbitrary web pages, claim live availability, or infer missing language/opening/access information.

## Source inventory

The machine-readable inventory is [`sources.json`](sources.json). It contains five representative datasets, below the hackathon maximum of ten. Each entry records publisher, catalogue URL, licence, source date, retrieval date, adapter and freshness policy.

MHLW explicitly publishes Medical Information Net facility data as open data under PDL1.0 and warns that reported data may contain errors or may not always be current. Tokyo Open Data Catalog resources used here are CC BY. Those limitations are retained as provenance/quality metadata rather than hidden.

## Canonical resource contract

`backend.tokyo.models.TokyoResource` contains:

- deterministic resource ID;
- name and bounded category;
- address and optional coordinates/municipality;
- only source-reported language, opening, access, phone and website fields;
- explicit freshness and data-quality flags;
- one or more provenance records with source record ID, source URL, catalogue URL, publisher, licence, source date, retrieval date and SHA-256 content hash.

Unknown fields stay unknown. A missing language field never becomes `English available`; a single coordinate is discarded rather than displayed as a valid location.

## Rebuild/update

From a clean checkout with project dependencies installed:

```bash
carepath-tokyo-data validate-registry
carepath-tokyo-data refresh
```

`refresh` resolves the current named CSV resource for CKAN-backed Tokyo datasets, downloads all five official sources, filters the national MHLW files to Tokyo, normalises rows, merges deterministic duplicates, and writes:

- `data/tokyo/generated/resources.jsonl`
- `data/tokyo/generated/build_report.json`

To retain the exact downloaded inputs for an audit/reproduction bundle:

```bash
carepath-tokyo-data refresh --raw-dir data/tokyo/raw
```

Raw snapshots and generated artifacts are rebuildable and should not be treated as user data. Never place personal health information in this directory.

## Boundaries

- no diagnosis or treatment advice;
- no inference that an unreported service/language/opening hour exists;
- no claim that a listed facility is open or accepting patients in real time;
- no user location or health history stored by this ingestion layer;
- no scraping/redistribution of pages without an explicit reusable-data licence.
