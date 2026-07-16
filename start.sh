#!/usr/bin/env bash
# Start/manage the Computor Agent in Docker.
#
# Usage:
#   ./start.sh [command] [options]
#
# Commands:
#   up (default)   Start the agent (creates config.yaml from the example on first run)
#   down           Stop and remove the agent container
#   logs           Follow the agent logs
#   status         Show container state and the agent /health snapshot
#
# Options:
#   --workers N    Worker count: messages processed concurrently (default 4, max 50)
#   --build        Force image rebuild on up
#   -h, --help     Show this help
#
# Environment:
#   WORKERS         Same as --workers (the flag wins)
#   DASHBOARD_PORT  Host port for the dashboard/health endpoint (default 8080)

set -euo pipefail

cd "$(dirname "$0")"

usage() {
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
}

if ! command -v docker >/dev/null 2>&1; then
    echo "Error: docker is not installed. See https://docs.docker.com/engine/install/" >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "Error: the docker compose plugin is missing. See https://docs.docker.com/compose/install/" >&2
    exit 1
fi

CMD="up"
WORKERS="${WORKERS:-}"
BUILD=""

while [ $# -gt 0 ]; do
    case "$1" in
        up|down|logs|status) CMD="$1" ;;
        --workers) shift; WORKERS="${1:?Error: --workers needs a value}" ;;
        --workers=*) WORKERS="${1#*=}" ;;
        --build) BUILD="--build" ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; echo; usage; exit 1 ;;
    esac
    shift
done

DASHBOARD_PORT="${DASHBOARD_PORT:-8080}"

case "$CMD" in
    up)
        if [ ! -f config.yaml ]; then
            cp config.example.yaml config.yaml
            chmod 600 config.yaml
            echo "Created config.yaml from config.example.yaml."
            echo "Edit it now (backend url + api_token, llm provider/model),"
            echo "then run ./start.sh again."
            exit 1
        fi
        if [ -n "$WORKERS" ]; then
            case "$WORKERS" in
                ''|*[!0-9]*) echo "Error: --workers must be a positive integer." >&2; exit 1 ;;
            esac
            export WORKERS
        fi
        # shellcheck disable=SC2086
        docker compose up -d $BUILD
        echo
        echo "Computor Agent started (workers: ${WORKERS:-4})."
        echo "  status:    ./start.sh status"
        echo "  logs:      ./start.sh logs"
        echo "  dashboard: http://127.0.0.1:${DASHBOARD_PORT}/"
        ;;
    down)
        docker compose down
        ;;
    logs)
        docker compose logs -f
        ;;
    status)
        docker compose ps
        echo
        if command -v curl >/dev/null 2>&1; then
            curl -fsS "http://127.0.0.1:${DASHBOARD_PORT}/health" 2>/dev/null | python3 -m json.tool \
                || echo "Agent /health not reachable on port ${DASHBOARD_PORT} (container starting or down?)."
        fi
        ;;
esac
