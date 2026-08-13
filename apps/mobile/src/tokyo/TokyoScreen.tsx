import { useMemo, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import type { ControlledApiError } from "../api/client";
import { createRuntimeApiClient } from "../api/runtime";
import { useI18n } from "../i18n/I18nContext";
import type { AppLocale } from "../i18n/resources";
import {
  explanationFor,
  responseHasModelFallback,
  responseHasPartialResourceData,
  searchTokyoAgent,
} from "./api";
import { TOKYO_COPY, type TokyoCopy, type TokyoExample } from "./copy";
import type {
  TokyoAgentApiResponse,
  TokyoLocation,
  TokyoResourceSearchResult,
  TokyoSafetyReference,
} from "./types";

interface BrowserGeolocationPosition {
  coords: {
    latitude: number;
    longitude: number;
  };
}

interface BrowserGeolocation {
  getCurrentPosition: (
    success: (position: BrowserGeolocationPosition) => void,
    failure: () => void,
    options: { enableHighAccuracy: boolean; maximumAge: number; timeout: number },
  ) => void;
}

function browserGeolocation(): BrowserGeolocation | null {
  const target = globalThis as unknown as {
    navigator?: { geolocation?: BrowserGeolocation };
  };
  return target.navigator?.geolocation ?? null;
}

function openExternal(url: string): void {
  void Linking.openURL(url);
}

function directionsUrl(result: TokyoResourceSearchResult): string | null {
  const { resource } = result;
  if (resource.latitude !== null && resource.longitude !== null) {
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
      `${String(resource.latitude)},${String(resource.longitude)}`,
    )}`;
  }
  if (resource.address !== null) {
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(resource.address)}`;
  }
  return null;
}

function languageLabel(language: string): string {
  const normalized = language.toLowerCase();
  if (normalized === "en") return "English";
  if (normalized === "ja") return "日本語";
  if (normalized === "zh") return "中文";
  return language;
}

function ActionButton({
  label,
  onPress,
  testID,
}: {
  label: string;
  onPress: () => void;
  testID: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [styles.actionButton, pressed ? styles.pressed : null]}
      testID={testID}
    >
      <Text style={styles.actionButtonText}>{label}</Text>
    </Pressable>
  );
}

function ResourceCard({
  copy,
  response,
  result,
}: {
  copy: TokyoCopy;
  response: TokyoAgentApiResponse;
  result: TokyoResourceSearchResult;
}) {
  const { resource } = result;
  const provenance = resource.provenance[0];
  const explanation = explanationFor(response, resource.resource_id);
  const directions = directionsUrl(result);
  const sourceUrl = provenance?.source_url ?? provenance?.catalog_url ?? null;
  const sourceDate = provenance?.source_as_of ?? provenance?.retrieved_at ?? null;
  const category = copy.category[resource.category] ?? resource.category;

  return (
    <View style={styles.resultCard} testID={`tokyo-resource-${resource.resource_id}`}>
      <View style={styles.resultHeader}>
        <View style={styles.resultTitleColumn}>
          <Text accessibilityRole="header" style={styles.resultTitle}>
            {resource.name}
          </Text>
          <Text style={styles.categoryPill}>{category}</Text>
        </View>
        {result.distance_km !== null ? (
          <Text style={styles.distance}>{`${result.distance_km.toFixed(1)} km`}</Text>
        ) : null}
      </View>

      {explanation !== null ? (
        <View style={styles.explanationBox}>
          <Text style={styles.sectionEyebrow}>{copy.whyMatch}</Text>
          <Text style={styles.bodyText}>{explanation}</Text>
        </View>
      ) : (
        <View style={styles.explanationBox}>
          <Text style={styles.sectionEyebrow}>{copy.whyMatch}</Text>
          <Text style={styles.mutedText}>{copy.explanationUnavailable}</Text>
        </View>
      )}

      <View style={styles.factBox}>
        <Text style={styles.sectionEyebrow}>{copy.verifiedFacts}</Text>
        <FactRow label={copy.address} value={resource.address ?? copy.notReported} />
        {result.distance_km !== null ? (
          <FactRow label={copy.distance} value={`${result.distance_km.toFixed(1)} km`} />
        ) : null}
        <FactRow
          label={copy.sourceReportedLanguages}
          value={
            resource.languages.length > 0
              ? resource.languages.map(languageLabel).join(", ")
              : copy.notReported
          }
        />
        <FactRow label={copy.openingHours} value={resource.opening_hours ?? copy.notReported} />
        {resource.access_notes !== null ? (
          <FactRow label={copy.accessNotes} value={resource.access_notes} />
        ) : null}
      </View>

      <View style={styles.sourceBox}>
        <Text style={styles.sectionEyebrow}>{copy.sourceFreshness}</Text>
        <Text style={styles.bodyText}>
          {provenance?.publisher ?? copy.notReported}
          {sourceDate !== null ? ` · ${sourceDate}` : ""}
        </Text>
        <Text style={styles.mutedText}>{copy.freshness[resource.freshness]}</Text>
      </View>

      <View style={styles.actionRow}>
        {directions !== null ? (
          <ActionButton
            label={copy.directions}
            onPress={() => {
              openExternal(directions);
            }}
            testID={`tokyo-directions-${resource.resource_id}`}
          />
        ) : null}
        {resource.website !== null ? (
          <ActionButton
            label={copy.officialPage}
            onPress={() => {
              openExternal(resource.website ?? "");
            }}
            testID={`tokyo-website-${resource.resource_id}`}
          />
        ) : null}
        {resource.phone !== null ? (
          <ActionButton
            label={copy.call}
            onPress={() => {
              openExternal(`tel:${resource.phone ?? ""}`);
            }}
            testID={`tokyo-call-${resource.resource_id}`}
          />
        ) : null}
        {sourceUrl !== null ? (
          <ActionButton
            label={copy.officialSource}
            onPress={() => {
              openExternal(sourceUrl);
            }}
            testID={`tokyo-source-${resource.resource_id}`}
          />
        ) : null}
      </View>
    </View>
  );
}

function FactRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.factRow}>
      <Text style={styles.factLabel}>{label}</Text>
      <Text style={styles.factValue}>{value}</Text>
    </View>
  );
}

function SafetyReferenceButton({
  reference,
  label,
}: {
  reference: TokyoSafetyReference;
  label: string;
}) {
  return (
    <ActionButton
      label={`${label}: ${reference.publisher}`}
      onPress={() => {
        openExternal(reference.canonical_url);
      }}
      testID={`tokyo-safety-source-${reference.source_id}`}
    />
  );
}

function LanguageSelector({
  locale,
  setLocale,
}: {
  locale: AppLocale;
  setLocale: (locale: AppLocale) => void;
}) {
  const options: { locale: AppLocale; label: string }[] = [
    { locale: "en", label: "English" },
    { locale: "ja", label: "日本語" },
    { locale: "zh", label: "中文" },
  ];
  return (
    <View style={styles.languageRow} accessibilityRole="radiogroup">
      {options.map((option) => {
        const selected = option.locale === locale;
        return (
          <Pressable
            key={option.locale}
            accessibilityLabel={`Tokyo ${option.label}`}
            accessibilityRole="radio"
            accessibilityState={{ checked: selected }}
            onPress={() => {
              setLocale(option.locale);
            }}
            style={({ pressed }) => [
              styles.languageButton,
              selected ? styles.languageButtonSelected : null,
              pressed ? styles.pressed : null,
            ]}
            testID={`tokyo-language-${option.locale}`}
          >
            <Text style={selected ? styles.languageTextSelected : styles.languageText}>
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function TokyoScreen() {
  const { locale, setLocale } = useI18n();
  const copy = TOKYO_COPY[locale];
  const client = useMemo(() => createRuntimeApiClient(), []);
  const [query, setQuery] = useState("");
  const [manualMunicipality, setManualMunicipality] = useState("");
  const [location, setLocation] = useState<TokyoLocation | null>(null);
  const [locationLabelText, setLocationLabelText] = useState("");
  const [locating, setLocating] = useState(false);
  const [locationNotice, setLocationNotice] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [response, setResponse] = useState<TokyoAgentApiResponse | null>(null);
  const [error, setError] = useState<ControlledApiError | null>(null);
  const [inputError, setInputError] = useState<string | null>(null);

  const chooseExample = (example: TokyoExample) => {
    setQuery(example.query);
    setManualMunicipality(example.municipality);
    setLocation({ mode: "municipality", municipality: example.municipality });
    setLocationLabelText(example.municipalityLabel);
    setLocationNotice(null);
    setInputError(null);
    setResponse(null);
    setError(null);
  };

  const useCurrentLocation = () => {
    const geolocation = browserGeolocation();
    if (geolocation === null) {
      setLocationNotice(copy.locationDenied);
      setLocation(null);
      return;
    }
    setLocating(true);
    setLocationNotice(null);
    geolocation.getCurrentPosition(
      (position) => {
        setLocating(false);
        setLocation({
          mode: "coordinates",
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        });
        setLocationLabelText(copy.locationReady);
        setInputError(null);
      },
      () => {
        setLocating(false);
        setLocation(null);
        setLocationLabelText("");
        setLocationNotice(copy.locationDenied);
      },
      { enableHighAccuracy: false, maximumAge: 60_000, timeout: 10_000 },
    );
  };

  const useManualLocation = () => {
    const municipality = manualMunicipality.trim();
    if (!municipality) {
      setInputError(copy.missingLocation);
      return;
    }
    setLocation({ mode: "municipality", municipality });
    setLocationLabelText(municipality);
    setLocationNotice(null);
    setInputError(null);
  };

  const runSearch = async () => {
    const normalizedQuery = query.trim();
    if (!normalizedQuery) {
      setInputError(copy.missingRequest);
      return;
    }
    if (location === null) {
      setInputError(copy.missingLocation);
      return;
    }
    setSearching(true);
    setInputError(null);
    setError(null);
    setResponse(null);
    const result = await searchTokyoAgent(client, {
      query: normalizedQuery,
      interface_language: locale,
      location,
      radius_km: 10,
      limit: 5,
    });
    setSearching(false);
    if (result.ok) {
      setResponse(result.data);
    } else {
      setError(result.error);
    }
  };

  return (
    <ScrollView
      contentContainerStyle={styles.page}
      keyboardShouldPersistTaps="handled"
      nativeID="tokyo-screen"
      testID="tokyo-screen"
    >
      <View style={styles.shell}>
        <View style={styles.hero}>
          <View style={styles.brandRow}>
            <Text style={styles.brand}>{copy.productLine}</Text>
            <Text style={styles.privacyBadge}>Open data · no account required</Text>
          </View>
          <Text accessibilityRole="header" style={styles.heading}>
            {copy.heading}
          </Text>
          <Text style={styles.intro}>{copy.intro}</Text>
          <Text style={styles.languageLabel}>{copy.languageLabel}</Text>
          <LanguageSelector locale={locale} setLocale={setLocale} />
        </View>

        <View style={styles.searchCard}>
          <Text style={styles.fieldLabel}>{copy.requestLabel}</Text>
          <TextInput
            accessibilityLabel={copy.requestLabel}
            multiline
            onChangeText={(value) => {
              setQuery(value);
              setInputError(null);
            }}
            placeholder={copy.requestPlaceholder}
            style={styles.queryInput}
            testID="tokyo-query"
            value={query}
          />

          <Text style={styles.examplesLabel}>{copy.examplesLabel}</Text>
          <View style={styles.exampleRow}>
            {copy.examples.map((example) => (
              <Pressable
                key={example.id}
                accessibilityRole="button"
                onPress={() => {
                  chooseExample(example);
                }}
                style={({ pressed }) => [styles.exampleButton, pressed ? styles.pressed : null]}
                testID={`tokyo-example-${example.id}`}
              >
                <Text style={styles.exampleText}>{example.label}</Text>
              </Pressable>
            ))}
          </View>

          <View style={styles.divider} />
          <Text style={styles.fieldLabel}>{copy.locationHeading}</Text>
          <Text style={styles.helperText}>{copy.locationWhy}</Text>
          <Pressable
            accessibilityRole="button"
            disabled={locating || searching}
            onPress={useCurrentLocation}
            style={({ pressed }) => [
              styles.primaryButton,
              locating || searching ? styles.disabled : null,
              pressed ? styles.pressed : null,
            ]}
            testID="tokyo-use-current-location"
          >
            {locating ? <ActivityIndicator color="#FFFFFF" size="small" /> : null}
            <Text style={styles.primaryButtonText}>
              {locating ? copy.locating : copy.useCurrentLocation}
            </Text>
          </Pressable>
          {locationNotice !== null ? (
            <Text
              accessibilityRole="alert"
              style={styles.noticeText}
              testID="tokyo-location-notice"
            >
              {locationNotice}
            </Text>
          ) : null}

          <Text style={styles.manualLabel}>{copy.manualLabel}</Text>
          <View style={styles.manualRow}>
            <TextInput
              accessibilityLabel={copy.manualLabel}
              onChangeText={(value) => {
                setManualMunicipality(value);
                setInputError(null);
              }}
              placeholder={copy.manualPlaceholder}
              style={styles.manualInput}
              testID="tokyo-manual-location"
              value={manualMunicipality}
            />
            <Pressable
              accessibilityRole="button"
              disabled={searching}
              onPress={useManualLocation}
              style={({ pressed }) => [styles.secondaryButton, pressed ? styles.pressed : null]}
              testID="tokyo-use-manual-location"
            >
              <Text style={styles.secondaryButtonText}>{copy.useManualLocation}</Text>
            </Pressable>
          </View>

          {location !== null ? (
            <View style={styles.locationSelected} testID="tokyo-selected-location">
              <Text style={styles.sectionEyebrow}>{copy.selectedLocation}</Text>
              <Text style={styles.locationSelectedText}>{locationLabelText}</Text>
            </View>
          ) : null}

          {inputError !== null ? (
            <Text accessibilityRole="alert" style={styles.errorText} testID="tokyo-input-error">
              {inputError}
            </Text>
          ) : null}

          <Pressable
            accessibilityRole="button"
            disabled={searching || locating}
            onPress={() => void runSearch()}
            style={({ pressed }) => [
              styles.searchButton,
              searching || locating ? styles.disabled : null,
              pressed ? styles.pressed : null,
            ]}
            testID="tokyo-search"
          >
            {searching ? <ActivityIndicator color="#FFFFFF" size="small" /> : null}
            <Text style={styles.searchButtonText}>
              {searching ? copy.searching : copy.findHelp}
            </Text>
          </Pressable>
        </View>

        {error !== null ? (
          <View accessibilityRole="alert" style={styles.errorPanel} testID="tokyo-api-error">
            <Text style={styles.panelTitle}>
              {error.code === "network_error" ? copy.offline : copy.apiError}
            </Text>
            <Text style={styles.bodyText}>{error.message}</Text>
            <Pressable
              accessibilityRole="button"
              onPress={() => void runSearch()}
              style={({ pressed }) => [styles.secondaryButton, pressed ? styles.pressed : null]}
            >
              <Text style={styles.secondaryButtonText}>{copy.retry}</Text>
            </Pressable>
          </View>
        ) : null}

        {response?.status === "safety_boundary" ? (
          <View accessibilityRole="alert" style={styles.safetyPanel} testID="tokyo-safety-boundary">
            <Text style={styles.panelTitle}>{copy.safetyTitle}</Text>
            <Text style={styles.safetyDisposition}>{copy.safetyEmergency}</Text>
            <Text style={styles.bodyText}>{response.safety.message}</Text>
            <View style={styles.actionRow}>
              {response.safety.references.map((reference) => (
                <SafetyReferenceButton
                  key={reference.source_id}
                  label={copy.officialSource}
                  reference={reference}
                />
              ))}
            </View>
          </View>
        ) : null}

        {response !== null && response.status !== "safety_boundary" ? (
          <View style={styles.responseSection}>
            {responseHasModelFallback(response) ? (
              <View style={styles.fallbackPanel} testID="tokyo-model-fallback">
                <Text style={styles.bodyText}>{copy.modelFallback}</Text>
              </View>
            ) : null}
            {responseHasPartialResourceData(response) ? (
              <View style={styles.partialPanel} testID="tokyo-partial-data">
                <Text style={styles.bodyText}>{copy.partialData}</Text>
              </View>
            ) : null}

            {response.status === "clarification_required" ? (
              <View style={styles.infoPanel} testID="tokyo-clarification">
                <Text style={styles.panelTitle}>{copy.clarification}</Text>
                <Text style={styles.bodyText}>{response.clarification?.message ?? ""}</Text>
              </View>
            ) : null}

            {response.status === "unsupported" ? (
              <View style={styles.infoPanel} testID="tokyo-unsupported">
                <Text style={styles.panelTitle}>{copy.unsupported}</Text>
                <Text style={styles.bodyText}>{response.clarification?.message ?? ""}</Text>
              </View>
            ) : null}

            {response.status === "no_match" ? (
              <View style={styles.infoPanel} testID="tokyo-no-match">
                <Text style={styles.panelTitle}>{copy.noMatch}</Text>
                <Text style={styles.bodyText}>{copy.noMatchHint}</Text>
              </View>
            ) : null}

            {response.status === "ok" && response.search !== null ? (
              <View testID="tokyo-results">
                <Text accessibilityRole="header" style={styles.resultsHeading}>
                  {copy.resultsHeading}
                </Text>
                <Text style={styles.resultsCount}>{`${String(response.search.count)} result${
                  response.search.count === 1 ? "" : "s"
                }`}</Text>
                {response.search.results.map((result) => (
                  <ResourceCard
                    key={result.resource.resource_id}
                    copy={copy}
                    response={response}
                    result={result}
                  />
                ))}
              </View>
            ) : null}
          </View>
        ) : null}

        <View style={styles.footerBox}>
          <Text style={styles.helperText}>{copy.privacyNote}</Text>
          <Text style={styles.helperText}>
            CarePath Tokyo is a public-resource navigation prototype, not diagnosis or treatment.
          </Text>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: {
    flexGrow: 1,
    alignItems: "center",
    backgroundColor: "#F3F7F6",
    paddingHorizontal: 16,
    paddingTop: 24,
    paddingBottom: 40,
  },
  shell: { width: "100%", maxWidth: 980, gap: 18 },
  hero: {
    backgroundColor: "#123F3F",
    borderRadius: 24,
    padding: 24,
    gap: 12,
  },
  brandRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, alignItems: "center" },
  brand: { color: "#D8F0EA", fontSize: 18, fontWeight: "800", letterSpacing: 0.4 },
  privacyBadge: {
    color: "#123F3F",
    backgroundColor: "#D8F0EA",
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 5,
    fontSize: 12,
    fontWeight: "700",
  },
  heading: { color: "#FFFFFF", fontSize: 32, lineHeight: 38, fontWeight: "800", maxWidth: 760 },
  intro: { color: "#E7F1EF", fontSize: 16, lineHeight: 24, maxWidth: 760 },
  languageLabel: { color: "#FFFFFF", fontSize: 13, fontWeight: "700", marginTop: 4 },
  languageRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  languageButton: {
    minHeight: 44,
    minWidth: 76,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#94B5AF",
    paddingHorizontal: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  languageButtonSelected: { backgroundColor: "#FFFFFF", borderColor: "#FFFFFF" },
  languageText: { color: "#FFFFFF", fontWeight: "700" },
  languageTextSelected: { color: "#123F3F", fontWeight: "800" },
  searchCard: {
    backgroundColor: "#FFFFFF",
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "#D7E3E0",
    padding: 20,
    gap: 12,
  },
  fieldLabel: { color: "#173B3B", fontSize: 17, fontWeight: "800" },
  queryInput: {
    minHeight: 104,
    borderWidth: 1,
    borderColor: "#AFC5C0",
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: "#173B3B",
    backgroundColor: "#FBFDFC",
    fontSize: 16,
    lineHeight: 23,
    textAlignVertical: "top",
  },
  examplesLabel: { color: "#536A66", fontSize: 13, fontWeight: "700" },
  exampleRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  exampleButton: {
    minHeight: 44,
    justifyContent: "center",
    borderRadius: 12,
    backgroundColor: "#E9F3F0",
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  exampleText: { color: "#285C5C", fontSize: 13, fontWeight: "700" },
  divider: { height: 1, backgroundColor: "#E2EAE8", marginVertical: 4 },
  helperText: { color: "#60736F", fontSize: 13, lineHeight: 20 },
  primaryButton: {
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 8,
    borderRadius: 13,
    backgroundColor: "#285C5C",
    paddingHorizontal: 16,
  },
  primaryButtonText: { color: "#FFFFFF", fontSize: 15, fontWeight: "800" },
  manualLabel: { color: "#536A66", fontSize: 13, fontWeight: "700", marginTop: 2 },
  manualRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  manualInput: {
    flexGrow: 1,
    minWidth: 190,
    minHeight: 48,
    borderWidth: 1,
    borderColor: "#AFC5C0",
    borderRadius: 13,
    paddingHorizontal: 13,
    color: "#173B3B",
    backgroundColor: "#FBFDFC",
    fontSize: 15,
  },
  secondaryButton: {
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 13,
    borderWidth: 1,
    borderColor: "#285C5C",
    backgroundColor: "#FFFFFF",
    paddingHorizontal: 16,
  },
  secondaryButtonText: { color: "#285C5C", fontSize: 14, fontWeight: "800" },
  locationSelected: { borderRadius: 12, backgroundColor: "#EFF7F4", padding: 12, gap: 3 },
  locationSelectedText: { color: "#173B3B", fontSize: 15, fontWeight: "700" },
  sectionEyebrow: {
    color: "#526D67",
    fontSize: 11,
    lineHeight: 15,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 0.4,
  },
  noticeText: { color: "#785F1E", backgroundColor: "#FFF7DB", borderRadius: 10, padding: 10 },
  errorText: { color: "#8A2E2E", fontSize: 13, fontWeight: "700" },
  searchButton: {
    minHeight: 54,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 8,
    borderRadius: 14,
    backgroundColor: "#123F3F",
    paddingHorizontal: 18,
    marginTop: 4,
  },
  searchButtonText: { color: "#FFFFFF", fontSize: 16, fontWeight: "800" },
  disabled: { opacity: 0.55 },
  pressed: { opacity: 0.74 },
  responseSection: { gap: 12 },
  resultsHeading: { color: "#173B3B", fontSize: 24, lineHeight: 30, fontWeight: "800" },
  resultsCount: { color: "#60736F", fontSize: 13, marginBottom: 4 },
  resultCard: {
    backgroundColor: "#FFFFFF",
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "#D7E3E0",
    padding: 18,
    gap: 12,
    marginTop: 12,
  },
  resultHeader: { flexDirection: "row", justifyContent: "space-between", gap: 10 },
  resultTitleColumn: { flex: 1, gap: 6, alignItems: "flex-start" },
  resultTitle: { color: "#173B3B", fontSize: 19, lineHeight: 25, fontWeight: "800" },
  categoryPill: {
    color: "#285C5C",
    backgroundColor: "#E8F2EF",
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 4,
    fontSize: 11,
    fontWeight: "800",
  },
  distance: { color: "#285C5C", fontSize: 15, fontWeight: "800" },
  explanationBox: { backgroundColor: "#F0F6F4", borderRadius: 12, padding: 12, gap: 5 },
  factBox: { gap: 7 },
  factRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, justifyContent: "space-between" },
  factLabel: { color: "#60736F", fontSize: 13, fontWeight: "700", flexBasis: 180 },
  factValue: { color: "#173B3B", fontSize: 13, flex: 1, minWidth: 160, textAlign: "right" },
  sourceBox: { borderTopWidth: 1, borderTopColor: "#E2EAE8", paddingTop: 10, gap: 4 },
  bodyText: { color: "#264844", fontSize: 14, lineHeight: 21 },
  mutedText: { color: "#687B77", fontSize: 12, lineHeight: 18 },
  actionRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  actionButton: {
    minHeight: 44,
    justifyContent: "center",
    borderRadius: 11,
    backgroundColor: "#E8F2EF",
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  actionButtonText: { color: "#285C5C", fontSize: 12, fontWeight: "800" },
  errorPanel: {
    backgroundColor: "#FFF1F1",
    borderWidth: 1,
    borderColor: "#E7C6C6",
    borderRadius: 16,
    padding: 16,
    gap: 10,
  },
  safetyPanel: {
    backgroundColor: "#FFF3E8",
    borderWidth: 1,
    borderColor: "#E4B98F",
    borderRadius: 16,
    padding: 18,
    gap: 10,
  },
  safetyDisposition: { color: "#8B4513", fontWeight: "800", fontSize: 14 },
  fallbackPanel: { backgroundColor: "#F2F2FA", borderRadius: 12, padding: 12 },
  partialPanel: { backgroundColor: "#FFF8E5", borderRadius: 12, padding: 12 },
  infoPanel: {
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#D7E3E0",
    borderRadius: 16,
    padding: 16,
    gap: 7,
  },
  panelTitle: { color: "#173B3B", fontSize: 17, fontWeight: "800" },
  footerBox: { paddingHorizontal: 6, gap: 4 },
});
