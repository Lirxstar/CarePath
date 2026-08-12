# CP-204 — bounded Tokyo intent and grounded resource agent

CP-204 adds a multilingual natural-language layer above the deterministic CP-203 Tokyo search service. It does **not** make the language model a factual resource authority.

## Runtime boundary

The request path is:

1. The client supplies natural-language text, an explicit interface language (`en`, `ja`, or `zh`), and either browser coordinates or a manual municipality.
2. A deterministic parser handles the frozen CP-202 primary journeys and explicit hard constraints.
3. Only when the service category cannot be resolved deterministically may the configured `LLMProvider` propose a value in the strict CP-204 intent schema.
4. Pydantic validation rejects extra fields, unsupported categories, invalid intent/category pairs, arbitrary location values, radius overrides, top-k overrides, and free-form factual claims.
5. CP-204 converts the validated intent into a `TokyoResourceSearchRequest` and calls only the CP-203 `TokyoResourceRepository`.
6. CP-203 remains the authority for category filtering, source-reported language constraints, distance, radius, ranking, unknown fields, and provenance.
7. For optional `why_match` explanations, the model receives only returned `resource_id` values plus deterministic allow-listed reason codes. It never receives resource names, addresses, phone numbers, opening hours, coordinates, URLs, or other factual fields. The application validates the selected reason codes and renders the final EN/JA/ZH text locally with source provenance attached.

This means a prompt injection can at worst produce an invalid structured proposal. It cannot directly add a resource, weaken CP-203 hard filters, set the location/radius/top-k, or create a user-visible factual field.

## Frozen MVP intents

CP-204 accepts exactly the CP-202 MVP categories:

| Intent | CP-203 category |
| --- | --- |
| `find_healthcare` | `healthcare` |
| `find_cooling_shelter` | `cooling_shelter` |
| `find_family_support` | `family_support` |
| `find_mental_health_support` | `mental_health_support` |

Other CP-201 categories are not silently promoted into the hackathon agent. A recognized out-of-scope request returns a bounded `unsupported` response; an unclear or multi-category request returns `clarification_required`.

## HTTP contract

`POST /tokyo/agent/search`

Example:

```json
{
  "query": "I need a nearby clinic where staff can support me in English.",
  "interface_language": "en",
  "location": {
    "mode": "coordinates",
    "latitude": 35.6938,
    "longitude": 139.7034
  },
  "radius_km": 5,
  "limit": 5
}
```

The model cannot receive or emit `location`, `radius_km`, or `limit`. Those values come from the validated request and are passed directly to CP-203. Radius remains capped at 50 km and result count at 50 by the shared CP-203 contract.

A resolved response contains:

- the validated structured intent and whether it came from deterministic parsing or the model;
- explicit model status for intent parsing and optional explanation selection;
- the unchanged CP-203 search response, including canonical `TokyoResource` fields and provenance;
- optional grounded explanations whose reason codes are checked against the returned resource before local rendering.

If the configured model fails or returns invalid structured output, deterministic scenarios and verified CP-203 results remain usable. Unsupported generated explanations are omitted rather than guessed.

## Provider configuration

CP-204 uses the repository's existing replaceable `LLMProvider` registry. CI and the public reviewer can remain credential-free with:

```dotenv
CAREPATH_LLM_PROVIDER=mock
```

A real operator-controlled OpenAI-compatible model can be selected without code changes:

```dotenv
CAREPATH_LLM_PROVIDER=local_openai
CAREPATH_LOCAL_LLM_BASE_URL=http://127.0.0.1:8000
CAREPATH_LOCAL_LLM_MODEL_ID=<served-model-id>
CAREPATH_LOCAL_LLM_STRUCTURED_OUTPUT_MODE=openai_json_schema
```

The existing `local_openai` provider is loopback-only and supports strict JSON-schema generation. A hackathon deployment that co-locates an OpenAI-compatible model runtime with the API can therefore switch from mock to a real model through environment configuration only. No paid API or secret credential is required by CP-204 CI.

`CAREPATH_PRIVACY_MODE=local_strict` additionally enforces that the configured provider reports itself as local/operator-controlled.

## Grounding and privacy properties

- Natural-language parsing never gives the model authority over canonical resource facts.
- Precise coordinates are not included in the model intent prompt.
- Result-fact values are not included in the model explanation prompt.
- Required language support is a CP-203 hard filter; unknown language data never counts as a match.
- Missing opening/access/phone/website data never becomes positive evidence.
- Source provenance remains attached to every returned resource and every rendered explanation.
- Static opening-hours data must not be phrased as live availability.
- CP-205 remains responsible for urgent Tokyo safety routing before ordinary navigation; CP-204 deliberately does not claim that safety work is complete.

## Validation

The CP-204 test suite covers:

- all nine frozen EN/JA/ZH variants of the three CP-202 primary scenarios;
- model-assisted paraphrase resolution;
- provider failure and invalid structured output;
- unsupported and ambiguous service requests;
- prompt injection attempts to change category, radius or facts;
- explanation reason codes that are not backed by a returned resource;
- provenance-preserving grounded explanations;
- API validation of coordinates, radius, result limits, query length and forbidden extra arguments.
