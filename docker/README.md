# Running the Computor Agent with Docker

Everything an admin needs: **Docker** (with the compose plugin), a **config
file**, and the **start script**.

## Quick start

```bash
# 1. First run creates config.yaml from the example and exits
./start.sh

# 2. Edit config.yaml: backend url + api_token, llm provider/model
$EDITOR config.yaml

# 3. Start the agent with 8 workers
./start.sh --workers 8

# 4. Check it
./start.sh status      # container state + /health snapshot
./start.sh logs        # follow logs
```

Stop with `./start.sh down`. Rebuild after a code update with
`./start.sh up --build`.

**Required settings in config.yaml:**
- `backend.url` — Backend API URL
- `backend.api_token` or `backend.username`/`password` — Authentication
- `llm.provider`, `llm.model`, `llm.base_url` — LLM settings

## Worker count

The worker count is how many messages the agent processes **concurrently**
(one container, one process — concurrency is bounded by an internal
semaphore). Precedence, highest first:

1. `computor-agent tutor messaging --workers N` (CLI flag)
2. `COMPUTOR_WORKERS` environment variable — what `./start.sh --workers N` sets
3. `scheduler.max_concurrent_processing` in `config.yaml`
4. Default: 5 (compose default: 4)

Valid range: 1–50.

## Environment variable overrides

Any of these can be set in the `environment:` section of
`docker-compose.yml`; they win over the mounted `config.yaml`:

| Variable | Overrides |
|---|---|
| `COMPUTOR_WORKERS` | `scheduler.max_concurrent_processing` |
| `COMPUTOR_BACKEND_URL` | `backend.url` |
| `COMPUTOR_BACKEND_API_TOKEN` | `backend.api_token` |
| `COMPUTOR_BACKEND_USERNAME` | `backend.username` |
| `COMPUTOR_BACKEND_PASSWORD` | `backend.password` |
| `COMPUTOR_LLM_PROVIDER` | `llm.provider` |
| `COMPUTOR_LLM_MODEL` | `llm.model` |
| `COMPUTOR_LLM_BASE_URL` | `llm.base_url` |
| `COMPUTOR_LLM_API_KEY` | `llm.api_key` |

`start.sh` additionally reads `WORKERS` and `DASHBOARD_PORT` (host port for
the dashboard, default 8080).

## Using an LLM on the host machine

The container reaches the host through `host.docker.internal`. In
`config.yaml`:

```yaml
llm:
  provider: ollama
  model: devstral-small
  base_url: http://host.docker.internal:11434/v1
```

| Provider | Host URL |
|----------|----------|
| Ollama | `http://host.docker.internal:11434/v1` |
| LM Studio | `http://host.docker.internal:1234/v1` |

For Ollama, make sure it listens on all interfaces
(`OLLAMA_HOST=0.0.0.0 ollama serve`, or the systemd equivalent) — by default
it binds to 127.0.0.1 and is unreachable from containers.

## Health, restarts, and self-healing

- **`GET /healthz`** (strict): HTTP 200 only when the scheduler is running
  *and* the WebSocket to the backend is connected; 503 otherwise. This is
  what the container HEALTHCHECK polls. LLM state is deliberately excluded —
  restarting the container can't fix an LLM outage.
- **`GET /health`** (informational): always HTTP 200, with the full picture
  (scheduler, WebSocket, LLM probe). Used by `./start.sh status`.
- **Recoverable failures** (backend restart, network blip, idle-connection
  reaping): the agent reconnects on its own with capped exponential backoff
  (5s→300s, jittered) and catches up on unread messages afterwards. The
  container may show `(unhealthy)` while offline; it recovers by itself.
- **Unrecoverable failures** (invalid credentials, unexpected crash): the
  process exits **nonzero** and Docker's `restart: unless-stopped` policy
  relaunches it. Note Docker restarts on process *exit*, not on unhealthy
  healthcheck status.
- A clean `docker compose down` / SIGTERM exits 0.

The healthcheck tolerates ~5 minutes of failure (10 retries × 30s) before
flagging unhealthy, so short reconnect windows don't flap the status.

## Dashboard

The image runs the agent with `--api-port 8080`; compose publishes it as
`127.0.0.1:8080` on the host (change with `DASHBOARD_PORT`). Endpoints:
`/` (dashboard), `/health`, `/healthz`, `/metrics`, `/logs`.

## Verifying the reconnect behavior (manual e2e)

```bash
./start.sh --workers 2
docker ps                                   # wait for (healthy)

# Simulate a long outage (longer than any old retry budget)
docker network disconnect <network> computor-agent   # find it: docker inspect computor-agent
sleep 700
docker network connect <network> computor-agent

./start.sh logs   # expect: capped backoff attempts, then
                  # "WebSocket reconnected after N attempt(s)" and a catch-up run
curl -s http://127.0.0.1:8080/healthz       # back to {"status": "ok"}
```

Clean-shutdown check: `docker kill -s TERM computor-agent` → exit code 0, no
restart loop (`docker inspect -f '{{.State.ExitCode}}' computor-agent`).

## Without start.sh

```bash
cp config.example.yaml config.yaml && $EDITOR config.yaml
WORKERS=8 docker compose up -d --build
docker compose logs -f
docker compose down
```

One-off commands and an interactive shell:

```bash
docker compose run --rm computor-agent bash
docker compose run --rm computor-agent \
    computor-agent ask "Hello" -p ollama -m devstral-small
```

## Troubleshooting

- **Container restarts in a loop** — `docker compose logs` shows why; most
  common: invalid `backend.api_token` (exit after repeated auth failures) or
  unreachable `backend.url`.
- **`(unhealthy)` but running** — the WebSocket to the backend is down and
  the agent is retrying; check backend availability, then `/health` for
  detail.
- **Cannot reach the LLM** — `/health` shows the last LLM probe result;
  verify `llm.base_url` is reachable *from inside the container* (use
  `host.docker.internal`, not `localhost`), and that the LLM server listens
  on all interfaces.
- **Config file not found** — `config.yaml` must exist next to
  `docker-compose.yml` (`./start.sh` creates it from the example on first
  run).
