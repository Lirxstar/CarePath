import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const fixtureUrl = new URL('../../../data/tokyo/journeys.json', import.meta.url);
const REQUIRED_LANGUAGES = new Set(['en', 'ja', 'zh']);
const REQUIRED_FAILURES = new Set([
  'location_permission_denied',
  'no_matching_resources',
  'incomplete_resource_data',
  'model_unavailable',
  'urgent_or_unsafe_request',
]);

export function loadTokyoJourneyFixtures() {
  const catalog = JSON.parse(readFileSync(fixtureUrl, 'utf8'));
  validateCatalog(catalog);
  return catalog;
}

export function primaryScenarioVariants(catalog = loadTokyoJourneyFixtures()) {
  return catalog.primary_scenarios.flatMap((scenario) =>
    scenario.interactions.map((interaction) => ({
      caseId: `${scenario.scenario_id}:${interaction.language}`,
      scenarioId: scenario.scenario_id,
      language: interaction.language,
      request: interaction.request,
      location: scenario.location,
      expected: scenario.expected,
    })),
  );
}

function validateCatalog(catalog) {
  if (catalog.schema_version !== 'cp202-v1') {
    throw new Error('unsupported CP-202 fixture schema');
  }
  if (catalog.product?.demo_target_seconds > 60) {
    throw new Error('Tokyo primary demo target must be at most 60 seconds');
  }
  if (
    catalog.product?.primary_inputs?.account_required ||
    catalog.product?.primary_inputs?.health_upload_required
  ) {
    throw new Error('Tokyo primary journey must not require account or health-data upload');
  }
  if (!Array.isArray(catalog.primary_scenarios) || catalog.primary_scenarios.length !== 3) {
    throw new Error('CP-202 must contain exactly three primary scenarios');
  }
  for (const scenario of catalog.primary_scenarios) {
    const languages = new Set(scenario.interactions.map((item) => item.language));
    if (
      languages.size !== 3 ||
      ![...REQUIRED_LANGUAGES].every((language) => languages.has(language))
    ) {
      throw new Error(`${scenario.scenario_id} must contain exactly EN/JA/ZH variants`);
    }
    if (scenario.account_required || scenario.health_upload_required) {
      throw new Error(`${scenario.scenario_id} cannot require account or health upload`);
    }
    if (scenario.estimated_demo_seconds > catalog.product.demo_target_seconds) {
      throw new Error(`${scenario.scenario_id} exceeds the frozen demo target`);
    }
    if (
      scenario.expected.language_constraint === 'required' &&
      scenario.expected.filters.unknown_language_is_match
    ) {
      throw new Error(
        `${scenario.scenario_id} cannot treat unknown language support as a match`,
      );
    }
  }
  const failureIds = new Set(catalog.failure_scenarios.map((item) => item.failure_id));
  if (
    failureIds.size !== REQUIRED_FAILURES.size ||
    ![...REQUIRED_FAILURES].every((failureId) => failureIds.has(failureId))
  ) {
    throw new Error('CP-202 failure contract is incomplete');
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const catalog = loadTokyoJourneyFixtures();
  const variants = primaryScenarioVariants(catalog);
  console.log(
    JSON.stringify(
      {
        schema_version: catalog.schema_version,
        primary_scenarios: catalog.primary_scenarios.length,
        multilingual_variants: variants.length,
        failure_scenarios: catalog.failure_scenarios.length,
      },
      null,
      2,
    ),
  );
}
