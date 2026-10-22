#!/bin/bash
# Install on faepmac2 as root:
#   install.sh BACKEND_TOKEN_FILE LLM_KEY_FILE
# Each file holds one secret on its first line. The source tree is this
# checkout; the runtime gets a non-editable copy of it.
set -euo pipefail
test "$(uname -s)" = Darwin
test "$(id -u)" = 0
label=com.computor.lena-tutor
if launchctl print "system/$label" >/dev/null 2>&1; then
    echo "Stop $label before changing its code or credentials." >&2
    exit 1
fi
source_root=$(cd "$(dirname "$0")/../../.." && pwd)
assets="$source_root/ops/lena-tutor/macos"
runtime=/Library/Computor/LenaTutor
logs=/private/var/log/computor-lena-tutor  # resolved path; the sandbox matches real paths
account=_computor_lena
token_file=${1:?Usage: install.sh BACKEND_TOKEN_FILE LLM_KEY_FILE}
llm_key_file=${2:?Usage: install.sh BACKEND_TOKEN_FILE LLM_KEY_FILE}

if ! id "$account" >/dev/null 2>&1; then
    account_uid=0
    for candidate in $(jot - 498 450); do
        if [ -z "$(dscl . -search /Users UniqueID "$candidate")" ] \
            && [ -z "$(dscl . -search /Groups PrimaryGroupID "$candidate")" ]; then
            account_uid=$candidate
            break
        fi
    done
    test "$account_uid" != 0
    dscl . -create "/Groups/$account"
    dscl . -create "/Groups/$account" PrimaryGroupID "$account_uid"
    dscl . -create "/Users/$account"
    dscl . -create "/Users/$account" UniqueID "$account_uid"
    dscl . -create "/Users/$account" PrimaryGroupID "$account_uid"
    dscl . -create "/Users/$account" UserShell /usr/bin/false
    dscl . -create "/Users/$account" NFSHomeDirectory /var/empty
    dscl . -create "/Users/$account" IsHidden 1
    dscl . -create "/Users/$account" Password '*'
fi
account_uid=$(id -u "$account")
test "$account_uid" != 0
dscl . -read "/Users/$account" UserShell | grep -q '/usr/bin/false$'
dscl . -read "/Users/$account" NFSHomeDirectory | grep -q '/var/empty$'

install -d -o root -g wheel -m 0755 "$runtime"
install -d -o "$account" -g wheel -m 0700 "$logs"
install -m 0644 "$assets/tutor.sb" "$assets/tutor.yaml" "$runtime/"
install -m 0644 "$source_root/ops/public-luna/macos/probe.py" "$runtime/probe.py"
install -m 0755 "$assets/run.sh" "$runtime/run.sh"
# Non-editable install of this checkout with the locked dependencies.
rm -rf "$runtime/venv"
UV_PROJECT_ENVIRONMENT="$runtime/venv" /opt/homebrew/bin/uv sync --frozen --no-dev \
    --no-editable --python /opt/homebrew/bin/python3.12 --project "$source_root"

"$runtime/venv/bin/python" -I - "$token_file" "$llm_key_file" "$runtime" "$account_uid" <<'PY'
import os, pathlib, shlex, sys
import yaml
from computor_agent.settings import ComputorConfig
from computor_agent.tutor.config import TutorConfig
token_file, key_file, root, uid = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3]), int(sys.argv[4])
token = pathlib.Path(token_file).read_text().splitlines()[0].strip()
key = pathlib.Path(key_file).read_text().splitlines()[0].strip()
if not token.startswith('ctp_') or len(token) < 32 or not key:
    raise ValueError('Invalid tutor credentials')
config = ComputorConfig.from_file(root / 'tutor.yaml')
TutorConfig.model_validate(yaml.safe_load((root / 'tutor.yaml').read_text())['tutor'])
if config.backend.url != 'https://computor.at/api' or config.llm.base_url != 'http://10.77.0.20:8090/v1':
    raise ValueError('Tutor endpoints must match the installed firewall')
env = root / 'tutor.env'
fd = os.open(env, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.fchmod(fd, 0o600)
with os.fdopen(fd, 'w') as file:
    file.write(f'COMPUTOR_BACKEND_API_TOKEN={shlex.quote(token)}\n'
               f'COMPUTOR_LLM_API_KEY={shlex.quote(key)}\n')
policy = (f'pass out quick inet proto tcp from any to 195.201.17.41 port 443 user {uid} keep state\n'
          f'pass out quick inet proto tcp from any to 10.77.0.20 port 8090 user {uid} keep state\n'
          f'block return out quick proto {{ tcp udp }} all user {uid}\n')
(root / 'tutor.pf').write_text(policy)
PY
/sbin/pfctl -nf "$runtime/tutor.pf"
/usr/bin/sandbox-exec -D PYTHON_EXECUTABLE=/usr/bin/true -D "LOG_DIR=$logs" \
    -f "$runtime/tutor.sb" /usr/bin/true
chown -R root:wheel "$runtime"
install -o root -g wheel -m 0644 "$assets/$label.plist" "/Library/LaunchDaemons/$label.plist"
plutil -lint "/Library/LaunchDaemons/$label.plist"
echo "Installed Lena tutor; run the probe before bootstrapping $label."
