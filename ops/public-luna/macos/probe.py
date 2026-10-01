"""Run with the deployed worker's UID, sandbox and PF anchor; no learner data."""
import json
import os
import socket
import subprocess

import httpx


def main():
    checks = {}
    with httpx.Client(timeout=10, trust_env=False) as client:
        for name, url, expected in (
            ('backend_https', 'https://computor.at/api/auth/providers', 200),
            ('slopgate', 'http://10.77.0.20:8090/v1/models', 401),
        ):
            try:
                checks[name] = client.get(url).status_code == expected
            except httpx.HTTPError:
                checks[name] = False
    try:
        with socket.create_connection(('1.1.1.1', 443), timeout=5):
            checks['other_egress_denied'] = False
    except OSError:
        checks['other_egress_denied'] = True
    try:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
        checks['listener_denied'] = False
    except PermissionError:
        checks['listener_denied'] = True
    try:
        with open(f'/tmp/public-luna-probe-{os.getpid()}', 'w'):
            pass
        checks['file_write_denied'] = False
    except PermissionError:
        checks['file_write_denied'] = True
    try:
        subprocess.run(['/usr/bin/true'], check=True)
        checks['child_process_denied'] = False
    except PermissionError:
        checks['child_process_denied'] = True
    print(json.dumps(checks))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
