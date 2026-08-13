# Two-minute presentation script

**Target length:** about 1 minute 45 seconds to 2 minutes at a clear pace.

Tokyo has a lot of useful public data. The problem is that people often do not know what the official service is called, which agency owns it, or which Japanese term to search for.

Imagine a resident in Koto City on a very hot day. They feel uncomfortable and simply ask: “I need somewhere nearby to cool down.”

CarePath Tokyo starts from that natural-language need. The user can choose English, Japanese or Chinese, use browser location or enter a municipality manually, and no account or health-file upload is required.

Behind the interface, we deliberately separate language understanding from factual authority. A bounded parser maps the request to a supported intent. Deterministic geospatial tools then search canonical Tokyo public data. The model layer, when enabled, can only assist with structured intent or allow-listed explanation reasons. It cannot invent facilities, change location or radius, override safety decisions, or write resource facts.

For this Koto example, CarePath returns designated Cooling Shelters with source provenance, freshness information, directions and only the contact actions actually present in the source. If the request contains urgent warning signs, deterministic safety triage runs before ordinary ranking.

The current data layer combines five authoritative dataset entries and 13,364 normalized resources across healthcare, cooling shelters, family support and mental-health support.

On our fixed 24-case software-engineering evaluation, all 24 cases passed: multilingual intent routing, deterministic ranking, safety escalation, provenance and grounded factual claims all met the frozen acceptance thresholds, with zero unsupported factual resource claims. This is an engineering result, not a clinical-effectiveness claim.

CarePath Tokyo’s goal is simple: reduce the friction between “I need help” and “here is the relevant, source-backed Tokyo resource,” while keeping the data source and uncertainty visible.
