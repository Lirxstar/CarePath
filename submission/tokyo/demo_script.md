# Deterministic demo script

## Public URL

https://carepath-api-8edq.onrender.com/tokyo

## Recommended <= 60 second judging flow

1. Open the public `/tokyo` URL in a logged-out browser.
2. Point out that no account or health-data upload is requested.
3. Keep English selected.
4. Select the built-in **Cooling shelter / Koto City** demo scenario.
5. Point out that the location is explicitly labelled as the demo area rather than real user geolocation.
6. Click **Find help**.
7. Open the first result card and show:
   - source-backed resource name/address;
   - freshness/source information;
   - **Source** action;
   - **Directions** action;
   - optional website/telephone action only when present in the source.
8. Switch to Japanese or Chinese briefly to demonstrate the multilingual interface.
9. End on the message: resource facts come from authoritative datasets; the language/model layer does not create resource facts.

## Cold-start/provider fallback

- Free hosting may cold-start after inactivity; allow the page to load before recording.
- The public build uses the credential-free mock provider.
- The supported deterministic demo path remains functional without a live LLM.
- Do not improvise a claim about live opening, capacity, acceptance, language support or eligibility when the card does not display it.

## Optional operation-video shot list

- 0–8 s: `/tokyo` landing screen, EN/JA/ZH and privacy/no-login framing.
- 8–18 s: select the Koto cooling demo scenario.
- 18–35 s: run search and reveal ranked resource cards.
- 35–50 s: highlight provenance/freshness and directions/source actions.
- 50–60 s: switch language and finish on “source-backed, not generated facts.”
