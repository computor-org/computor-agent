# Public Luna on faepmac2

This is a separate native worker. It has no model tools, general Computor
credential, listener, writable cache, or learner files. Its dedicated non-login
UID can connect only to computor.at (`195.201.17.41:443`) and Slopgate
(`10.77.0.20:8090`). PF changes affect that UID only. The native sandbox also
denies listeners, file writes and child processes. Local DNS IPC is allowed.
The launcher stops the worker if PF is disabled or its rules change.

The installer does not start the worker. On faepmac2, supply a private JSON
file with exactly these four string fields:

- `PUBLIC_LUNA_BACKEND_URL`: `https://computor.at/api`
- `PUBLIC_LUNA_MODEL_URL`: `http://10.77.0.20:8090`
- `PUBLIC_LUNA_WORKER_KEY`: the dedicated backend key
- `PUBLIC_LUNA_MODEL_KEY`: the distinct Slopgate `public_luna` credential

Stop any existing public worker before reinstalling; the installer refuses to modify a loaded service. Install the pinned worker checkout with:

```sh
sudo bash ops/public-luna/macos/install.sh /private/path/credentials.json
```

The runtime is root-owned at `/Library/Computor/PublicLuna`; the JSON input can
be removed after installation. Dependencies are hash-locked, and inference
uses the existing batched Qwen model. The worker starts its native Python
framework executable directly with the venv launcher environment, so the
sandbox can forbid child processes from the start. No model is restarted.

Before starting, load only the dedicated PF anchor and run `probe.py` as the
worker UID through the installed sandbox. Compare with an unrestricted
connection to `1.1.1.1:443` and check that the PF block counter increases during
the negative probe. All six probe fields must be true. The probe sends no
learner data and no inference. Verify route authorization, content-free logs,
backend admission/recovery, and one synthetic answer before opening signup.

```sh
sudo launchctl bootstrap system /Library/LaunchDaemons/com.computor.public-luna.plist
sudo launchctl print system/com.computor.public-luna
```

The worker processes up to four requests concurrently. It logs no content;
stdout and stderr go to `/dev/null`. Monitor process liveness and backend queue
counts without periodic inference. HTTP redirects and environment proxies are
disabled. TLS verification remains enabled for the backend.

To stop or roll back, first disable backend public Luna admission, then:

```sh
sudo launchctl bootout system/com.computor.public-luna
sudo pfctl -a com.apple/computor-luna -F rules
```

Do not clear the anchor while the worker is running. Keep backend admission
disabled if the destination IP changes until the new firewall and TLS path pass
the probe. Existing TU teaching workers and both model services are independent.
