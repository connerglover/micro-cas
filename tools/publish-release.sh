#!/usr/bin/env bash
# Publish release assets to BOTH Forgejo (the main repo) and its GitHub mirror.
#
#   tools/publish-release.sh [--draft] [--notes-file FILE] <tag> <file>...
#
# For each forge it finds the release for <tag> (creating it if missing, so the
# Forgejo and GitHub halves of a build can finish in either order) and uploads
# every file, replacing an existing asset of the same name. Runs unchanged on
# Forgejo's Linux runner and GitHub's Windows/macOS runners (bash, curl, jq).
#
# Environment (a forge is skipped when its token is empty):
#   FORGEJO_TOKEN  token with write access to the Forgejo repo
#   FORGEJO_URL    default https://git.connerglover.com
#   FORGEJO_REPO   owner/name on Forgejo, default conner/<repo name>
#   GH_TOKEN       token with Contents: write on the GitHub repo
#   GH_REPO        owner/name on GitHub, default connerglover/<repo name>
set -euo pipefail

draft=false notes=""
while [ $# -gt 0 ]; do
  case "$1" in
    --draft) draft=true; shift ;;
    --notes-file) notes=$(cat "$2"); shift 2 ;;
    *) break ;;
  esac
done
tag=${1:?usage: publish-release.sh [--draft] <tag> <file>...}; shift
[ $# -gt 0 ] || { echo "no files to publish" >&2; exit 2; }
for f in "$@"; do [ -s "$f" ] || { echo "missing or empty: $f" >&2; exit 2; }; done

name=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
FORGEJO_URL=${FORGEJO_URL:-https://git.connerglover.com}
FORGEJO_REPO=${FORGEJO_REPO:-conner/$name}
GH_REPO=${GH_REPO:-connerglover/$name}
body=$(jq -n --arg t "$tag" --argjson d "$draft" --arg n "$notes" '{tag_name:$t,name:$t,draft:$d,body:$n}')

# --- Forgejo -----------------------------------------------------------------
forgejo() {
  local api="$FORGEJO_URL/api/v1/repos/$FORGEJO_REPO" auth="Authorization: token $FORGEJO_TOKEN" id
  # Drafts are not found by tag, so search the newest releases (drafts included).
  find_id() { curl -fsS -H "$auth" "$api/releases?limit=50" | jq -r --arg t "$tag" '[.[]|select(.tag_name==$t)|.id]|sort|.[0] // empty'; }
  id=$(find_id)
  for _ in 1 2 3; do [ -n "$id" ] && break; sleep 3; id=$(find_id); done
  if [ -z "$id" ]; then
    id=$(curl -fsS -X POST -H "$auth" -H 'Content-Type: application/json' -d "$body" "$api/releases" | jq -r .id)
    echo "Forgejo: created release $tag (#$id)"
  fi
  for f in "$@"; do
    local base; base=$(basename "$f")
    for old in $(curl -fsS -H "$auth" "$api/releases/$id/assets" | jq -r --arg n "$base" '.[]|select(.name==$n)|.id'); do
      curl -fsS -X DELETE -H "$auth" "$api/releases/$id/assets/$old" >/dev/null
    done
    curl -fsS -X POST -H "$auth" -F "attachment=@$f" "$api/releases/$id/assets?name=$(jq -rn --arg n "$base" '$n|@uri')" >/dev/null
    echo "Forgejo: uploaded $base"
  done
}

# --- GitHub ------------------------------------------------------------------
github() {
  local api="https://api.github.com/repos/$GH_REPO" auth="Authorization: Bearer $GH_TOKEN" id
  local h=(-H "$auth" -H 'Accept: application/vnd.github+json' -H 'X-GitHub-Api-Version: 2022-11-28')
  # GitHub's release list lags a few seconds behind a create (drafts are not found by
  # tag at all), so look again before creating, and fold away a duplicate afterwards.
  find_ids() { curl -fsS "${h[@]}" "$api/releases?per_page=100" | jq -r --arg t "$tag" '[.[]|select(.tag_name==$t)|.id]|sort|.[]'; }
  id=$(find_ids | head -1)
  for _ in 1 2 3; do [ -n "$id" ] && break; sleep 3; id=$(find_ids | head -1); done
  if [ -z "$id" ]; then
    local mine; mine=$(curl -fsS -X POST "${h[@]}" -d "$body" "$api/releases" | jq -r .id)
    echo "GitHub: created release $tag (#$mine)"
    sleep 5; id=$(find_ids | head -1); id=${id:-$mine}
    if [ "$id" != "$mine" ]; then
      curl -fsS -X DELETE "${h[@]}" "$api/releases/$mine" >/dev/null
      echo "GitHub: another run created #$id first; removed the duplicate #$mine"
    fi
  fi
  for f in "$@"; do
    local base; base=$(basename "$f")
    for old in $(curl -fsS "${h[@]}" "$api/releases/$id/assets?per_page=100" | jq -r --arg n "$base" '.[]|select(.name==$n)|.id'); do
      curl -fsS -X DELETE "${h[@]}" "$api/releases/assets/$old" >/dev/null
    done
    curl -fsS -X POST "${h[@]}" -H 'Content-Type: application/octet-stream' --data-binary "@$f" \
      "https://uploads.github.com/repos/$GH_REPO/releases/$id/assets?name=$(jq -rn --arg n "$base" '$n|@uri')" >/dev/null
    echo "GitHub: uploaded $base"
  done
}

done_any=false
if [ -n "${FORGEJO_TOKEN:-}" ]; then forgejo "$@"; done_any=true; fi
if [ -n "${GH_TOKEN:-}" ]; then github "$@"; done_any=true; fi
$done_any || { echo "no FORGEJO_TOKEN or GH_TOKEN set: nothing published" >&2; exit 1; }
