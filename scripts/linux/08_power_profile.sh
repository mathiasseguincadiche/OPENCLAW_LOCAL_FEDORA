#!/usr/bin/env bash
set -Eeuo pipefail

PROFILE="performance"
APPLY=0

while (($#)); do
  case "$1" in
    --profile)
      shift
      [[ $# -gt 0 ]] || { echo "ERREUR: --profile exige une valeur" >&2; exit 2; }
      PROFILE="$1"
      ;;
    --apply) APPLY=1 ;;
    -h|--help)
      echo "Usage: 08_power_profile.sh [--profile performance|balanced|power-saver] [--apply]"
      exit 0
      ;;
    *) echo "ERREUR: argument inconnu: $1" >&2; exit 2 ;;
  esac
  shift
done

case "$PROFILE" in
  performance|balanced|power-saver) ;;
  *) echo "ERREUR: profil non supporté: $PROFILE" >&2; exit 2 ;;
esac

command -v powerprofilesctl >/dev/null 2>&1 || {
  echo "ERREUR: powerprofilesctl absent; vérifier power-profiles-daemon." >&2
  exit 127
}

CURRENT="$(powerprofilesctl get)"
printf 'POWER_PROFILE_CURRENT=%s\n' "$CURRENT"
printf 'POWER_PROFILE_TARGET=%s\n' "$PROFILE"

if ((APPLY == 0)); then
  echo "DRY_RUN=PASS -- utiliser --apply pour modifier le profil."
  exit 0
fi

powerprofilesctl set "$PROFILE"
OBSERVED="$(powerprofilesctl get)"
[[ "$OBSERVED" == "$PROFILE" ]] || {
  echo "ERREUR: profil attendu=$PROFILE observé=$OBSERVED" >&2
  exit 2
}
printf 'POWER_PROFILE_RESULT=PASS profile=%s previous=%s\n' "$OBSERVED" "$CURRENT"
