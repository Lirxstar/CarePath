#!/usr/bin/env bash
set -euo pipefail

export CI=1
export EXPO_PUBLIC_CAREPATH_MOCK_MODE=true

mkdir -p docs/evidence/v08 docs/evidence/v08/logs
: > /tmp/carepath-android.log

npm --prefix apps/mobile run android > /tmp/carepath-android.log 2>&1 &
expo_pid=$!

cleanup() {
  if kill -0 "$expo_pid" 2>/dev/null; then
    kill "$expo_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

for attempt in $(seq 1 150); do
  if ! kill -0 "$expo_pid" 2>/dev/null; then
    echo "Expo process exited before the application became visible." >&2
    cat /tmp/carepath-android.log >&2
    exit 1
  fi

  resumed="$(
    adb shell dumpsys activity activities 2>/dev/null \
      | grep -m1 -E 'topResumedActivity=.*host\.exp\.exponent|ResumedActivity:.*host\.exp\.exponent' \
      || true
  )"
  bundled=false
  if grep -Eq 'Android Bundled|Bundled.*index' /tmp/carepath-android.log; then
    bundled=true
  fi

  if [[ -n "$resumed" && "$bundled" == true ]]; then
    # Give React Native a bounded interval to paint the first complete application frame.
    sleep 8
    adb exec-out screencap -p > docs/evidence/v08/android-expo-go.png
    png_size="$(wc -c < docs/evidence/v08/android-expo-go.png)"
    png_signature="$(od -An -t x1 -N8 docs/evidence/v08/android-expo-go.png | tr -d ' \n')"
    if (( png_size < 10000 )) || [[ "$png_signature" != "89504e470d0a1a0a" ]]; then
      echo "Android screenshot is invalid: ${png_size} bytes, signature ${png_signature}." >&2
      cat /tmp/carepath-android.log >&2
      exit 1
    fi
    printf '%s\n' "$resumed" > docs/evidence/v08/logs/android-foreground-activity.log
    adb shell uiautomator dump /sdcard/carepath-window.xml >/dev/null 2>&1 || true
    adb pull /sdcard/carepath-window.xml docs/evidence/v08/logs/android-window.xml >/dev/null 2>&1 || true
    exit 0
  fi

  sleep 2
done

echo "CarePath did not become a bundled foreground Expo Go experience." >&2
cat /tmp/carepath-android.log >&2
adb shell dumpsys activity activities >&2 || true
exit 1
