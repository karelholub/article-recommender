#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:5001}"
ACTOR_ID="${ACTOR_ID:-smoke-ops}"

echo "[1/6] Health check"
curl -fsS "$BASE_URL/readyz" >/dev/null

echo "[2/6] Create rollout"
CREATE_PAYLOAD='{"name":"smoke-rollout","baseline_config_id":"balanced","candidate_config_id":"balanced","traffic_percentage":15,"enabled":false,"actor_id":"'"$ACTOR_ID"'"}'
ROLL_CREATE="$(curl -fsS -X POST "$BASE_URL/api/rollouts" -H 'Content-Type: application/json' -d "$CREATE_PAYLOAD")"
ROLL_ID="$(printf '%s' "$ROLL_CREATE" | sed -n 's/.*"rollout_id":"\([^"]*\)".*/\1/p' | head -n1)"
if [[ -z "$ROLL_ID" ]]; then
  echo "Failed to extract rollout_id from response"
  exit 1
fi

echo "[3/6] Start rollout and run recommendation query"
curl -fsS -X POST "$BASE_URL/api/rollouts/$ROLL_ID/start" -H 'Content-Type: application/json' -d '{"actor_id":"'"$ACTOR_ID"'"}' >/dev/null
RECO_RESP="$(curl -fsS -X POST "$BASE_URL/api/recommendations/query" -H 'Content-Type: application/json' -d '{"user_id":"demo_user","top_n":3,"config_id":"balanced","allow_rollout":true}')"
if ! printf '%s' "$RECO_RESP" | grep -q '"recommendations"'; then
  echo "Recommendation response missing recommendations field"
  exit 1
fi

echo "[4/6] Evaluate active rollouts"
EVAL_RESP="$(curl -fsS -X POST "$BASE_URL/api/rollouts/evaluate-active" -H 'Content-Type: application/json' -d '{"actor_id":"'"$ACTOR_ID"'"}')"
if ! printf '%s' "$EVAL_RESP" | grep -q '"evaluated"'; then
  echo "Rollout evaluation response malformed"
  exit 1
fi

echo "[5/6] Queue controls"
curl -fsS -X POST "$BASE_URL/api/events/ingest-queue-control" -H 'Content-Type: application/json' -d '{"action":"disable","actor_id":"'"$ACTOR_ID"'"}' >/dev/null
curl -fsS -X POST "$BASE_URL/api/events/ingest-queue-control" -H 'Content-Type: application/json' -d '{"action":"enable","actor_id":"'"$ACTOR_ID"'"}' >/dev/null

echo "[6/6] API protection status"
curl -fsS "$BASE_URL/api/operations/api-protection-status" >/dev/null

echo "Smoke operator flow passed for rollout $ROLL_ID"
