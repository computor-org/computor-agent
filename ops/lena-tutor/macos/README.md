# Course-message Lena for computor.at on faepmac2

This runs `computor-agent tutor messaging` for computor.at: learners who write
`@lena`, `@luna` or `@ai` in an assignment conversation get an answer in the
thread. It follows the [public Lena worker](../../public-luna/macos/README.md)
isolation:

- a dedicated non-login UID (`_computor_lena`) whose PF anchor
  `com.apple/computor-lena` allows only computor.at (`195.201.17.41:443`) and
  Slopgate (`10.77.0.20:8090`);
- a native sandbox that denies listeners, child processes and file writes
  except the log directory `/var/log/computor-lena-tutor` (0700);
- no tools or code execution, no HTTP dashboard, `--log-llm-content` off;
  the periodic LLM probe is off too (`--llm-probe-interval 0`): it only feeds
  the dashboard and calls `GET /models`, which `public_luna` refuses;
  the log holds ids, sizes and timings, not message text;
- `tutor.yaml` turns off AI notes, student notes, staff comments in the
  prompt, reference comparison and figure review.

The tutor reads the thread, the assignment description, the learner's latest
submission and its test results through the backend API, with the
permissions of its `_tutor` course memberships. Its API token has no extra
scopes.

## Backend prerequisites

- An `agent` service account (admin `POST /services`) with a scope-less API
  token, and a `_tutor` membership in each course Lena serves.
- `TUTOR_AGENT_USER_ID=<service user id>` in the backend `.env`, then recreate
  the API container.
- The tutor discovers its courses at startup: restart it after adding a course.

## Install

Stop a loaded service first; the installer refuses to change it. From a clean
export of the pinned revision, as root:

```sh
bash ops/lena-tutor/macos/install.sh /private/backend.token /private/llm.key
```

Each file holds one secret on its first line: the Computor API token and the
Slopgate `public_luna` key, the one the public Lena worker uses. computor.at
runs on that class rather than on `computor`, so its learners do not queue
behind the TU tutors; Slopgate admits the tutor's request shape on it with
tutor-sized limits (131,072 context, 8192 output, inline images) next to the
Ask Lena form (sloppy-org/slopgate e26722d2, slopcode-infra 5fd6325), always
for the `luna-public` model. The installer writes them to the root-only
`/Library/Computor/LenaTutor/tutor.env`; remove the input files afterwards.
Before the first start, load the anchor and run the public worker's
`probe.py` (installed next to the tutor) as `_computor_lena` in `tutor.sb`;
all six fields must be true.

## Operate

```sh
sudo launchctl bootstrap system /Library/LaunchDaemons/com.computor.lena-tutor.plist
sudo launchctl print system/com.computor.lena-tutor      # state, pid
sudo launchctl kickstart -k system/com.computor.lena-tutor  # restart
sudo tail /var/log/computor-lena-tutor/tutor.log
sudo launchctl bootout system/com.computor.lena-tutor
sudo pfctl -a com.apple/computor-lena -F rules   # only after bootout
```

A healthy start logs `Discovered N course(s)` and `WebSocket connected as
user <id>`. The launcher stops the tutor if PF is disabled or the anchor
changes. `launchctl bootout` returns before the old process exits; wait until
`launchctl print` fails before bootstrapping again.
