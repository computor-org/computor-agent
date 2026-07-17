# Tutor Agent

The Tutor AI Agent responds to student questions and grades submissions using an LLM.

## Commands

### Messaging Agent

Responds to student messages tagged with `#ai::request`.

```bash
# Production mode
computor-agent tutor messaging
computor-agent tutor messaging -c config.yaml --verbose
computor-agent tutor messaging --dry-run

# Development mode (interactive, no API calls)
computor-agent tutor messaging --dev
computor-agent tutor messaging --dev --assignment ./my-assignment
computor-agent tutor messaging --dev --prompts-dir ./custom-prompts
```

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--config` | `-c` | Config file path (default: `config.yaml`) |
| `--verbose` | `-v` | Enable verbose logging |
| `--dry-run` | | Log actions without sending responses |
| `--dev` | | Development mode (interactive shell) |
| `--prompts-dir` | | Custom prompts directory |
| `--assignment` | | [Dev] Assignment directory with `meta.yaml` |

### Grading Agent

Reviews and grades student submissions.

```bash
# Development mode (required for now)
computor-agent tutor grading --dev --reference ./assignment --student ./submission
computor-agent tutor grading --dev --reference ./assignment --student ./submission -l en

# Production mode (not yet implemented)
computor-agent tutor grading
```

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--config` | `-c` | Config file path (default: `config.yaml`) |
| `--verbose` | `-v` | Enable verbose logging |
| `--dev` | | Development mode (local files only) |
| `--prompts-dir` | | Custom prompts directory |
| `--reference` | | [Dev] Reference solution directory |
| `--student` | | [Dev] Student submission directory |
| `--language` | `-l` | Language for assignment (e.g., `en`, `de`) |

---

## Development Mode

Development mode allows testing without making API calls.

### Messaging Dev Mode

```bash
computor-agent tutor messaging --dev
```

**Interactive commands:**

| Command | Description |
|---------|-------------|
| `/new` | Start a new conversation |
| `/reply <id>` | Reply to a specific message |
| `/show` | Display conversation history |
| `/clear` | Clear all messages |
| `/exit` | Exit development mode |
| *(text)* | Send a message |

**Example session:**

```
You: How do I write a for loop in Python?
Processing message...
Intent: question_howto

AI Response:
In Python, you can write a for loop like this:
for item in [1, 2, 3]:
    print(item)
```

### Grading Dev Mode

```bash
computor-agent tutor grading --dev --reference ./assignment --student ./submission
```

**Directory structure:**

```
assignment/           # Reference solution
├── meta.yaml         # Assignment metadata and requirements
├── solution.py       # Reference implementation
└── ...

submission/           # Student submission
├── solution.py       # Student's code
└── ...
```

---

## Custom Prompts

You can customize the agent's prompts by providing a prompts directory:

```bash
computor-agent tutor messaging --prompts-dir ./my-prompts
computor-agent tutor messaging --dev --prompts-dir ./my-prompts
```

**Directory structure:**

```
prompts/
├── personality/           # Tone and style
│   ├── friendly_professional.md
│   ├── strict.md
│   └── casual.md
├── strategy/              # Response strategies
│   ├── question_example.md
│   ├── question_howto.md
│   ├── help_debug.md
│   ├── help_review.md
│   ├── clarification.md
│   └── fallback.md
└── security/              # Security prompts
    ├── detection.md
    └── confirmation.md
```

**Features:**
- Missing files are auto-created with defaults
- Existing files are never overwritten
- Hot reload in dev mode (changes apply immediately)

---

## Configuration

### config.yaml

```yaml
# Backend API
backend:
  url: https://api.computor.example.com
  api_token: ctp_your_token_here
  # Or use username/password:
  # username: tutor@example.com
  # password: secret

# LLM provider
llm:
  provider: ollama          # ollama, lmstudio, openai
  model: qwen2.5-coder:7b
  base_url: http://localhost:11434/v1
  temperature: 0.7

# Secondary vision-capable LLM, used only for figure review (optional)
# vision_llm:
#   provider: ollama
#   model: llava:13b
#   base_url: http://localhost:11434/v1

# Git credentials (for repository access)
credentials:
  - pattern: https://gitlab.example.com
    token: glpat-your-token

# Tutor behavior
tutor:
  personality:
    name: "Tutor AI"
    tone: "friendly_professional"

  triggers:
    request_tags:
      - scope: "ai"
        value: "request"
    response_tag:
      scope: "ai"
      value: "response"

  scheduler:
    poll_interval_seconds: 30
    cooldown_seconds: 5

  # Figure review (see section below)
  figure_review:
    enabled: false
```

---

## Figure Review

When enabled, the agent automatically detects figures (plots/pictures:
`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.bmp`) in a student submission
and reviews each one with a vision-capable LLM — one call per figure. The
findings (labels/units, legend, readability, data plausibility, assignment
fit) are injected into both the tutor messaging prompt and the grading
prompts, where they can lower the grade and appear in the feedback.

```yaml
vision_llm:                 # secondary model, used only for figure review
  provider: ollama
  model: llava:13b
  base_url: http://localhost:11434/v1

tutor:
  figure_review:
    enabled: true
    use_agent_llm: false    # true = reuse the main llm instead of vision_llm
    max_figures: 10         # figures reviewed per submission (1-50)
    max_image_bytes: 5242880
    image_extensions: [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"]
    max_response_tokens: 800
    temperature: 0.2
```

Notes:

- **Model choice is your responsibility.** With `use_agent_llm: true` the
  main `llm` model is used and must itself be vision-capable (e.g.
  `llava`, `qwen2.5-vl`, `gpt-4o`). A text-only model will fail per figure.
- **Fail fast:** enabling `figure_review` without a `vision_llm` section
  and without `use_agent_llm: true` is a startup error.
- **Graceful degradation:** if a vision call fails at runtime, the figure
  is reported as "could not be reviewed" and messaging/grading continue.
- **Environment overrides:** `COMPUTOR_VISION_LLM_PROVIDER`,
  `COMPUTOR_VISION_LLM_MODEL`, `COMPUTOR_VISION_LLM_BASE_URL`,
  `COMPUTOR_VISION_LLM_API_KEY`.
- **Custom prompt:** the review prompt can be overridden via
  `<prompts_dir>/figure_review/review.md` (hot-reloaded in dev mode).
- **Dev modes:** both `tutor messaging --dev` (scenario `submission/`
  directory) and `tutor grading --dev` (student submission directory) pick
  up figures from disk and run the same review pipeline.
- **Security note:** text rendered inside student images is untrusted; the
  review prompt instructs the model to ignore embedded instructions, but
  review output is still LLM-generated from student-controlled input.

---

## How It Works

### Messaging Flow

1. **Trigger Detection**: Student message has `#ai::request` tag or is a reply in an AI conversation
2. **Context Gathering**: Fetch conversation history, student info, assignment description
3. **Security Check**: Scan for prompt injection (optional)
4. **Intent Classification**: Determine what the student needs
5. **Response Generation**: Generate LLM response based on intent
6. **Send Response**: Post reply with `#ai::response` tag

**Intent types:**

| Intent | Description |
|--------|-------------|
| `question_example` | About assignment requirements |
| `question_howto` | General programming how-to |
| `help_debug` | Debugging assistance |
| `help_review` | Code review request |
| `clarification` | Follow-up question |

### Grading Flow

1. **Load Reference**: Read assignment requirements from `meta.yaml`
2. **Load Submission**: Read student's code
3. **LLM Analysis**: Compare against requirements
4. **Generate Feedback**: Determine grade and status

**Grading status:**

| Status | Value | Meaning |
|--------|-------|---------|
| `CORRECTED` | 1 | Requirements met |
| `CORRECTION_NECESSARY` | 2 | Requirements not met |
| `IMPROVEMENT_POSSIBLE` | 3 | Met, but could be better |

---

## Transport Modes

The messaging agent supports two transport modes:

### WebSocket (Preferred)

Real-time message delivery. Requires API token authentication.

```yaml
backend:
  api_token: ctp_your_token_here
```

### HTTP Polling (Fallback)

Polls for messages at regular intervals. Used when WebSocket is unavailable.

```yaml
tutor:
  scheduler:
    poll_interval_seconds: 30
```

---

## Troubleshooting

### LLM Connection Error

```bash
# Check if LLM is running
curl http://localhost:11434/v1/models

# For Ollama
ollama serve
```

### Authentication Failed

```bash
# Check config has valid credentials
cat config.yaml | grep -A5 backend
```

### No Messages Detected

- Verify message has `#ai::request` tag in title
- Check `--verbose` output for polling activity
- Ensure backend URL is correct
