#!/bin/bash
# Root-owned launch wrapper; only the native worker runs as the restricted UID.
set -euo pipefail
runtime=/Library/Computor/PublicLuna
anchor=com.apple/computor-luna
account=_computor_luna

test "$(id -u)" = 0
test "$(stat -f '%u:%Lp' "$runtime/worker.env")" = 0:600
if ! /sbin/pfctl -s info 2>/dev/null | /usr/bin/grep -q '^Status: Enabled'; then
    echo 'Public Luna requires its enabled network firewall' >&2
    exit 78
fi
/sbin/pfctl -a "$anchor" -f "$runtime/worker.pf"
expected_rules=$(/sbin/pfctl -a "$anchor" -sr 2>/dev/null)
test -n "$expected_rules"
python_executable=$("$runtime/venv/bin/python" -I -B -c 'import os, sys; print(os.path.realpath(os.path.join(sys.base_prefix, "Resources/Python.app/Contents/MacOS/Python")))')
test -x "$python_executable"
set -a
# shellcheck disable=SC1091
. "$runtime/worker.env"
set +a

/usr/bin/sudo -n -u "$account" \
    --preserve-env=PUBLIC_LUNA_BACKEND_URL,PUBLIC_LUNA_MODEL_URL,PUBLIC_LUNA_WORKER_KEY,PUBLIC_LUNA_MODEL_KEY \
    /usr/bin/env "__PYVENV_LAUNCHER__=$runtime/venv/bin/python" \
    /usr/bin/sandbox-exec -D "PYTHON_EXECUTABLE=$python_executable" -f "$runtime/worker.sb" \
    "$python_executable" -I -B "$runtime/worker.py" &
worker_pid=$!
trap 'kill "$worker_pid" 2>/dev/null || true; wait "$worker_pid" 2>/dev/null || true' EXIT
trap 'exit 0' TERM INT
while kill -0 "$worker_pid" 2>/dev/null; do
    sleep 15
    if ! /sbin/pfctl -s info 2>/dev/null | /usr/bin/grep -q '^Status: Enabled' \
        || [ "$(/sbin/pfctl -a "$anchor" -sr 2>/dev/null)" != "$expected_rules" ]; then
        echo 'Public Luna network firewall changed; stopping worker' >&2
        exit 1
    fi
done
wait "$worker_pid"
