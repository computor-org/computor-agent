#!/bin/bash
# Root-owned launch wrapper; only the tutor runs as the restricted UID.
set -euo pipefail
runtime=/Library/Computor/LenaTutor
logs=/private/var/log/computor-lena-tutor  # resolved path; the sandbox matches real paths
anchor=com.apple/computor-lena
account=_computor_lena

test "$(id -u)" = 0
test "$(stat -f '%u:%Lp' "$runtime/tutor.env")" = 0:600
if ! /sbin/pfctl -s info 2>/dev/null | /usr/bin/grep -q '^Status: Enabled'; then
    echo 'Lena tutor requires its enabled network firewall' >&2
    exit 78
fi
/sbin/pfctl -a "$anchor" -f "$runtime/tutor.pf" 2>/dev/null
expected_rules=$(/sbin/pfctl -a "$anchor" -sr 2>/dev/null)
test -n "$expected_rules"
python_executable=$("$runtime/venv/bin/python" -I -B -c 'import os, sys; print(os.path.realpath(os.path.join(sys.base_prefix, "Resources/Python.app/Contents/MacOS/Python")))')
test -x "$python_executable"
set -a
# shellcheck disable=SC1091
. "$runtime/tutor.env"
set +a

cd "$runtime"
/usr/bin/sudo -n -u "$account" \
    --preserve-env=COMPUTOR_BACKEND_API_TOKEN,COMPUTOR_LLM_API_KEY \
    /usr/bin/env "__PYVENV_LAUNCHER__=$runtime/venv/bin/python" HOME=/var/empty \
    /usr/bin/sandbox-exec -D "PYTHON_EXECUTABLE=$python_executable" -D "LOG_DIR=$logs" \
    -f "$runtime/tutor.sb" \
    "$python_executable" -I -B -m computor_agent.cli.main tutor messaging \
    -c "$runtime/tutor.yaml" -l "$logs/tutor.log" --llm-probe-interval 0 \
    >/dev/null &
tutor_pid=$!
trap 'kill "$tutor_pid" 2>/dev/null || true; wait "$tutor_pid" 2>/dev/null || true' EXIT
trap 'exit 0' TERM INT
while kill -0 "$tutor_pid" 2>/dev/null; do
    sleep 15
    if ! /sbin/pfctl -s info 2>/dev/null | /usr/bin/grep -q '^Status: Enabled' \
        || [ "$(/sbin/pfctl -a "$anchor" -sr 2>/dev/null)" != "$expected_rules" ]; then
        echo 'Lena tutor network firewall changed; stopping tutor' >&2
        exit 1
    fi
done
wait "$tutor_pid"
