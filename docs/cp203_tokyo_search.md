# CP-203 — Deterministic Tokyo geospatial resource search

CP-203 turns the canonical CP-201 `TokyoResource` corpus into a bounded search service that CP-204 model intent parsing and CP-206 UI work can call without giving the language model authority over factual resource selection.

## Responsibility boundary

The deterministic layer owns:

- coordinate and manual-municipality location validation;
- hard category and source-backed field filters;
- explicit language requirements;
- great-circle distance calculation;
- radius enforcement;
- stable ranking and tie-breaking;
- result limits;
- structured no-match responses;
- preservation of `freshness`, provenance, and unknown values.

It does **not** infer missing language support, opening hours, access features, live availability, or municipality. It also does not parse arbitrary natural language. CP-204 may propose a structured search request, but CP-203 validates that request and remains the final authority for filtering/ranking.

## Corpus loading

The API setting `CAREPATH_TOKYO_RESOURCE_PATH` defaults to:

```text
data/tokyo/generated/resources.jsonl
```

That file is the deterministic JSONL artifact produced by CP-201:

```bash
carepath-tokyo-data refresh
```

`TokyoResourceRepository.from_jsonl()` strictly validates every record as `TokyoResource` and rejects duplicate resource IDs. It never repairs malformed official-data records at query time.

If the configured corpus does not exist, the rest of CarePath can still start, but Tokyo resource endpoints return `503 tokyo_resources_unavailable`. They do not substitute synthetic resource results.

## Location modes

### Coordinates

A coordinate request contains validated latitude/longitude. CP-203 computes great-circle distance with the Haversine formula and returns `distance_km` rounded to three decimals for display.

Bounds:

- latitude: `[-90, 90]`;
- longitude: `[-180, 180]`;
- radius: `(0, 50]` km;
- result limit: `[1, 50]`.

Resources without verified coordinates are excluded from coordinate search rather than assigned a guessed location.

### Manual municipality fallback

The manual fallback accepts an explicit municipality label such as `江東区`. It compares that label only with the canonical resource's explicit `municipality` field after Unicode/whitespace normalization.

The implementation does **not** geocode the label, invent a centroid, or infer municipality from an address. Consequently manual-municipality results return `distance_km: null`. A resource whose address appears to contain the municipality but whose canonical `municipality` is unknown does not satisfy the hard municipality constraint.

## Allow-listed filters

`TokyoResourceFilters` supports only source-bounded fields:

- `category`;
- `required_languages`;
- `require_known_opening_hours`;
- `require_access_notes`;
- `require_phone`;
- `require_website`;
- `allowed_freshness`.

Unknown values never count as positive evidence. In particular, `languages: []` cannot satisfy `required_languages: ["en"]`, and `opening_hours: null` cannot satisfy `require_known_opening_hours: true`.

Extra/unsupported filter names are rejected by the API with the standard `422 validation_error` response.

## Ranking

Ranking is intentionally simple and auditable:

1. apply every hard filter;
2. for coordinate search, exclude resources outside the requested radius;
3. sort coordinate matches by unrounded distance ascending;
4. use `resource_id` as the deterministic final tie-break;
5. for manual municipality search, sort by `resource_id` because no verified distance exists;
6. apply the validated result limit.

The model cannot boost a resource above one that fails a hard constraint. Repeated queries over the same corpus and request therefore produce identical ordering.

## HTTP API

### Search resources

`POST /tokyo/resources/search`

Coordinate example:

```json
{
  "location": {
    "mode": "coordinates",
    "latitude": 35.6938,
    "longitude": 139.7034
  },
  "filters": {
    "category": "healthcare",
    "required_languages": ["en"]
  },
  "radius_km": 5,
  "limit": 10
}
```

Manual fallback example:

```json
{
  "location": {
    "mode": "municipality",
    "municipality": "江東区"
  },
  "filters": {
    "category": "family_support"
  },
  "limit": 10
}
```

A successful result contains a rank, deterministic `distance_km` when coordinates are available, and the complete canonical `TokyoResource`. The resource therefore carries its official provenance and freshness unchanged.

A valid query with zero results returns HTTP 200 with a structured empty state:

```json
{
  "status": "no_match",
  "count": 0,
  "results": [],
  "no_match": {
    "code": "no_matching_resources",
    "message": "No Tokyo resource satisfies all requested hard constraints.",
    "hard_constraints": ["category", "required_languages", "radius_km"]
  }
}
```

This is distinct from an invalid request, which returns 422.

### Fetch one canonical resource

`GET /tokyo/resources/{resource_id}`

This endpoint returns the source-backed canonical resource directly. Unknown fields remain `null`/empty and no generated explanation is added. An unknown ID returns `404 tokyo_resource_not_found`.

## CP-202 journey mapping

CP-203 is intentionally compatible with the frozen CP-202 acceptance contract:

- `tokyo-healthcare-language` maps to `category=healthcare` plus `required_languages=[en]`;
- `tokyo-heat-cooling-shelter` maps to `category=cooling_shelter` plus location/radius;
- `tokyo-family-support-unknown-service` maps to `category=family_support` plus location.

The mapping from natural language to those structured intents is still CP-204. Safety handling before ordinary ranking remains CP-205.

## Acceptance tests

`tests/test_cp203_tokyo_search.py` covers:

- numeric Haversine distance and coordinate boundaries;
- deterministic repeated ordering;
- resource-ID tie breaking;
- category/language hard constraints;
- unknown opening/access/contact data;
- manual municipality fallback without inferred distance/location;
- structured no-match output;
- strict JSONL loading and duplicate IDs;
- provenance/freshness preservation;
- API coordinate, radius, result-limit, unsupported-filter, and free-text-extra rejection;
- explicit 503 behaviour when the CP-201 corpus is unavailable.
