#!/bin/bash
# Install on faepmac2 as root. Credentials are JSON in a private input file.
set -euo pipefail
test "$(uname -s)" = Darwin
test "$(id -u)" = 0
source_root=$(cd "$(dirname "$0")/../../.." && pwd)
assets="$source_root/ops/public-luna/macos"
runtime=/Library/Computor/PublicLuna
account=_computor_luna
credentials_file=${1:?Usage: install.sh PRIVATE_CREDENTIALS_JSON}

if ! id "$account" >/dev/null 2>&1; then
    account_uid=0
    for candidate in $(jot - 499 450); do
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
install -m 0644 "$source_root/src/computor_agent/public_luna_worker.py" "$runtime/worker.py"
install -m 0644 "$assets/worker.sb" "$assets/requirements.lock" "$runtime/"
install -m 0755 "$assets/run.sh" "$runtime/run.sh"
/opt/homebrew/bin/python3.12 -m venv "$runtime/venv"
/opt/homebrew/bin/uv pip sync --python "$runtime/venv/bin/python" \
    --require-hashes "$runtime/requirements.lock"

"$runtime/venv/bin/python" - "$credentials_file" "$runtime" "$account_uid" <<'PY'
import importlib.util, json, os, pathlib, shlex, sys
source, root, uid = sys.argv[1], pathlib.Path(sys.argv[2]), int(sys.argv[3])
spec = importlib.util.spec_from_file_location('public_worker', root / 'worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
values = json.loads(pathlib.Path(source).read_text())
keys = ('PUBLIC_LUNA_BACKEND_URL', 'PUBLIC_LUNA_MODEL_URL',
        'PUBLIC_LUNA_WORKER_KEY', 'PUBLIC_LUNA_MODEL_KEY')
if set(values) != set(keys) or not all(isinstance(values[k], str) for k in keys):
    raise ValueError('Invalid public worker credential file')
worker._validate_config(*(values[k] for k in keys))
if values[keys[0]] != 'https://computor.at/api' or values[keys[1]] != 'http://10.77.0.20:8090':
    raise ValueError('Worker endpoints must match the installed firewall')
env = root / 'worker.env'
fd = os.open(env, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.fchmod(fd, 0o600)
with os.fdopen(fd, 'w') as file:
    file.write(''.join(f'{k}={shlex.quote(values[k])}\n' for k in keys))
policy = (f'pass out quick inet proto tcp from any to 195.201.17.41 port 443 user {uid} keep state\n'
          f'pass out quick inet proto tcp from any to 10.77.0.20 port 8090 user {uid} keep state\n'
          f'block return out quick proto {{ tcp udp }} all user {uid}\n')
(root / 'worker.pf').write_text(policy)
PY
/sbin/pfctl -nf "$runtime/worker.pf"
/usr/bin/sandbox-exec -D PYTHON_EXECUTABLE=/usr/bin/true -f "$runtime/worker.sb" /usr/bin/true
chown -R root:wheel "$runtime"
install -o root -g wheel -m 0644 "$assets/com.computor.public-luna.plist" \
    /Library/LaunchDaemons/com.computor.public-luna.plist
plutil -lint /Library/LaunchDaemons/com.computor.public-luna.plist
echo 'Installed public Luna worker; launch only after the backend and route pass their gates.'
