#!/usr/bin/env bash
# Update Bike Log on the server to the newest main: fetch the code, rebuild, restart.
# Installed as the command  bikelog-update  (and run every night if you said yes to automatic updates).
# Your data is untouched; the app writes a database backup itself before any schema upgrade.
set -euo pipefail
REPO="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
cd "$REPO"
before="$(git rev-parse --short=7 HEAD)"
git fetch --quiet --tags origin main
git merge --quiet --ff-only origin/main
commit="$(git rev-parse --short=7 HEAD)"
if [ "${1:-}" != "--force" ] && [ "$before" = "$commit" ] && docker compose -f deploy/compose.yml ps --status running --quiet bikelog | grep -q .; then
  echo "$(date -Is) Bike Log is up to date ($commit)."
  exit 0
fi
version="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' backend/bikelog/__init__.py)"
if git tag --points-at HEAD | grep -qx "v$version"; then full="$version"; else full="$version+$commit"; fi
echo "$(date -Is) Updating Bike Log $before -> $commit ($full) ..."
export BIKELOG_COMMIT="$commit" BIKELOG_VERSION="$full"
docker compose -f deploy/compose.yml build --pull bikelog
docker compose -f deploy/compose.yml up -d
docker image prune -f >/dev/null
echo "$(date -Is) Bike Log $full is running."
