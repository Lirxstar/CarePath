# v0.8 acceptance issue classification

This register records issues found while closing the v0.8 demo gate. Product defects fixed in PR #59 remain listed for auditability.

## Final validation record

PR #59 implementation head `c449948c9e4416f56d695ff243a5ce2000e9b32b` passed Repository Quality #1075 and v0.8 demo gate #69. The latter completed both the real-backend Expo Web journey and the Android emulator smoke. The Web and Android artifacts were downloaded and inspected: all required screenshots, video, trace, manifest, logs, foreground activity and UI hierarchy were present. No blocker, major or minor issue remains open.

Any later documentation-only commit must retain all required green checks before merge.

## Blocker — resolved and verified

### V08-VAL-001 — GitHub-hosted jobs terminated before step 1

**Status:** resolved and verified.

Early runs of both the existing `Repository quality` workflow and the new `v0.8 demo gate` were created by GitHub Actions but terminated before any workflow step was materialised. The connector reported empty `steps` lists and no usable logs because a runner never started the jobs.

Observed affected runs included:

- Repository quality #1010 and its failed-job rerun;
- v0.8 demo gate #3 and its failed-job rerun;
- Repository quality #1014, #1018 and #1026;
- v0.8 demo gate #7, #11 and #20.

The condition later cleared. GitHub-hosted runners executed checkout, dependency installation, formatting, lint, type-checking, tests, Expo exports, browser setup and emulator setup normally. Repository Quality #1075 and v0.8 demo gate #69 both completed successfully.

### V08-VAL-002 — Browser gate used unstable navigation locators and accepted blank screenshots

**Status:** fixed and verified.

The first fully executed browser gate imported the selected persona successfully but timed out while locating the Health Data tab by visible text. A subsequent attempt showed that the default bottom-tab implementation did not expose its accessibility label or configured test ID to the exported React Native Web DOM. The first PNG was also a blank full-page capture, so file existence alone was not adequate evidence.

The application now renders an explicit accessible custom tab bar. Each `Pressable` has a stable native ID, test ID, tab role, selected state and translated accessibility label under project control rather than relying on navigator-internal DOM. The gate captures the phone-sized viewport instead of using full-page capture and rejects screenshots below a minimum content size. The final Web artifact contained four non-empty screenshots.

### V08-VAL-003 — Evidence artifact paths did not reliably include video and trace

**Status:** fixed and verified.

Early failed runs uploaded a screenshot and temporary logs but did not reliably include the nested Playwright video and trace because the artifact combined repository-relative paths with absolute `/tmp` paths. The gate now copies API, Web and Android logs into `docs/evidence/v08/logs/`, writes Playwright output under the same repository evidence tree, retains trace on successful runs, and uploads the complete `docs/evidence/v08/**` tree with hidden files included.

The final Web artifact contained `video.webm`, `trace.zip`, four screenshots, `manifest.json`, API/Web logs and a Playwright result of `passed` with no failed tests.

### V08-VAL-004 — Android emulator action split the multiline smoke script

**Status:** fixed and verified.

The Android emulator itself booted successfully, but `reactivecircus/android-emulator-runner` executed the multiline `script` input as separate `/bin/sh` commands. The `for … done` loop was therefore split and failed with a shell syntax error before Expo Go could be evaluated.

The Android logic now lives in a repository-owned Bash script that is syntax-checked before the emulator step. The action invokes one Bash command, KVM permissions are enabled where available, and success requires CarePath to be a bundled foreground Expo Go experience plus a non-empty PNG with a valid PNG signature. The final Android artifact contained a valid 191 KB screenshot, foreground `ExperienceActivity`, UI hierarchy and Metro `Android Bundled` log.

### V08-VAL-005 — Android API 35 resumed-activity field was misdetected

**Status:** fixed and verified.

The first standalone Android script searched only for `mResumedActivity`, while Android API 35 emitted `topResumedActivity` and `ResumedActivity`. Expo Go was already visible and the JavaScript bundle had completed, but the script incorrectly timed out.

The detector now matches the API 35 fields directly. Android emulator smoke #69 completed successfully and uploaded the expected evidence.

## Major — fixed and verified in PR #59

### V08-MAJ-001 — Plan & History exposed only Accept / Reject / Complete

**Status:** fixed and verified.

The mobile route now supports Accept, Reject, Choose lighter option (`modified`), Complete, Partly done and Not completed. Rejection/non-completion accepts a reason and lighter-option selection is persisted as structured modified feedback.

### V08-MAJ-002 — Plan history API existed but was not shown in the mobile route

**Status:** fixed and verified.

The mobile route now reads current and historical plans, displays stable IDs/version/supersession status, actions and relative version differences.

### V08-MAJ-003 — Mobile did not have a shared offline/retry boundary

**Status:** fixed and verified.

All four routes now use shared controlled API/offline messaging and an accessible Retry action while retaining page-level loading/empty/error state.

### V08-MAJ-004 — No mobile i18n resource boundary

**Status:** fixed and verified.

`apps/mobile/src/i18n/` defines English, Chinese and Japanese resources. English remains the primary reviewer UI; navigation/common strings and safety-critical text are available through the locale provider, with the safety boundary available in all three languages.

### V08-MAJ-005 — No explicit long-term adaptation acceptance for both directions

**Status:** fixed and verified.

`tests/storage/test_v08_plan_adaptation.py` asserts that repeated high-difficulty rejection reduces the next plan and that stable high completion can increase the next plan difficulty, including source feedback provenance. `tests/test_cp015_v06_mobile_journey.py` and the recorded browser gate additionally prove that persisted `modified` feedback changes the subsequent runtime Planner output from a 12-minute action to an 8-minute action.

### V08-MAJ-006 — CP-015 evidence did not meet the requested v0.8 visual/device gate

**Status:** fixed and verified.

The final gate used the real FastAPI backend with Expo Web for the full recorded journey, captured four non-empty page screenshots, a video, a trace and a version manifest, and separately launched the application through Expo Go on an Android emulator.

### V08-MAJ-007 — Frozen synthetic data could drift outside the runtime context window

**Status:** fixed and verified.

The Agent runtime previously used wall-clock time when no explicit context end was supplied. A frozen synthetic package could therefore be treated as stale, causing a conservative low-data plan before any feedback and invalidating the adaptation demonstration. Explicitly marked synthetic demo profiles now anchor their Agent context to the latest persisted observation. Non-synthetic profiles continue to use current time.

### V08-MAJ-008 — Structured reliability objects crashed the real mobile dashboard

**Status:** fixed and verified.

The mobile trend contract incorrectly typed backend reliability as a string, while the real FastAPI response returns `{level, reason_codes}`. Importing a real persona therefore attempted to render an object as a React child and raised React error #31. The mobile contract now accepts the structured backend object as well as the legacy mock string, formats it into readable text, and has unit coverage for both forms and reason-code rendering.

## Minor — fixed and verified in PR #59

### V08-MIN-001 — Eight-minute activity text used the wrong English article

**Status:** fixed and verified.

The feedback loop already reduced the second Planner output from 12 minutes to 8 minutes, but the generated text used “a 8-minute”. Timed action wording now selects the appropriate article for 8, 11 and 18 minute phrases, including alternatives, and the Planner regression test requires “an 8-minute”.

No unresolved product-level minor issue is recorded.
