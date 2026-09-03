#!/usr/bin/env bash
set -euo pipefail
: "${WORKDIR:?set WORKDIR}"
: "${TCP_COMMAND:?set TCP_COMMAND, using {input} and {output}}"
: "${COLO_COMMAND:?set COLO_COMMAND, using {input} and {output}}"
exec python3 "$(dirname "$0")/coordinator.py" "$WORKDIR" \
  --colo "${COLO:-HKG}" --repo "${REPO:-}" --path "${RESULT_PATH:-}" \
  --tcp-command "$TCP_COMMAND" --colo-command "$COLO_COMMAND" \
  ${PUBLISHER_COMMAND:+--publisher-command "$PUBLISHER_COMMAND"} \
  --poll-seconds "${POLL_SECONDS:-5}" ${ONCE:+--once}
