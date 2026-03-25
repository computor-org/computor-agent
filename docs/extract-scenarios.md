# Extract Scenarios

Extracts real student interactions from the computor database into scenario directories for offline testing with the [Scenario Runner](scenario-runner.md).

## Prerequisites

- PostgreSQL access to the computor database (docker-postgres-1)
- MinIO access for downloading submission files (optional, use `--skip-files` without)
- Python packages: `psycopg2-binary`, `minio`, `pyyaml`

```bash
pip install psycopg2-binary minio pyyaml
```

## Usage

```bash
# Extract all graded submissions
python scripts/extract_scenarios.py -o ./extracted_scenarios/

# Filter by course
python scripts/extract_scenarios.py -o ./extracted/ --course-id <uuid>

# Limit number of scenarios
python scripts/extract_scenarios.py -o ./extracted/ --limit 20

# Skip downloading submission files from MinIO
python scripts/extract_scenarios.py -o ./extracted/ --skip-files

# Custom database connection
python scripts/extract_scenarios.py -o ./extracted/ \
  --db-host localhost --db-port 5432 --db-name codeability \
  --db-user postgres --db-password postgres_secret

# Custom MinIO connection
python scripts/extract_scenarios.py -o ./extracted/ \
  --minio-host localhost:9000 --minio-access-key minioadmin --minio-secret-key minioadmin
```

## What Gets Extracted

The script finds submission groups that have:

1. An **official submission** (`submission_artifact.submit = true`)
2. A **matching grade** (`submission_grade.graded_at > submission_artifact.uploaded_at`)

For each qualifying submission group:

| Output | Source |
|--------|--------|
| `scenario.yaml` | Student name (obfuscated), assignment title, grade info |
| `assignment/description.md` | `course_content.description` from database |
| `submission/` | Actual files downloaded from MinIO |
| `test-results.json` | `result` rows linked to the graded artifact |
| `grade.json` | Grade score, status, grader comment |
| `prompts/*.md` | Student messages (non-AI) as individual prompt files |

## Output Structure

```
extracted_scenarios/
├── intro-programming__numpy-basics__001/
│   ├── scenario.yaml
│   ├── assignment/
│   │   └── description.md
│   ├── submission/
│   │   └── solution.py
│   ├── test-results.json
│   ├── grade.json
│   └── prompts/
│       ├── 001_ai.md
│       └── 002.md
└── intro-programming__loops__002/
    └── ...
```

### scenario.yaml

```yaml
student:
  name: Student 001          # Obfuscated
assignment:
  title: NumPy Basics
  path: itpcp.pgph.py.basis1
  language: en
grade:
  score: 0.85
  status: corrected
  comment: null
extracted_from:
  course: Intro to Programming
  submission_group_id: 651debeb-...
```

## Obfuscation

All personally identifiable information is scrubbed:

| Data | Obfuscation |
|------|-------------|
| Student names | `Student 001`, `Student 002`, ... (consistent per extraction) |
| Email addresses | `student_001@example.com` (consistent mapping) |
| Remaining emails in text | Replaced with `redacted@example.com` |
| GitLab URLs | Replaced with `https://gitlab.example.com/org/repo` |
| UUIDs | Left as-is (not PII) |

Obfuscation is **consistent within a run** — the same real name always maps to the same fake name across all scenarios in one extraction.

## Data Flow

```
Database                          MinIO
   │                                │
   ├─ submission_group              │
   ├─ submission_artifact ──────────┤──→ submission/ files
   │    (submit=true)               │
   ├─ submission_grade              │
   │    (graded_at > uploaded_at)   │
   ├─ result                        │
   │    (submission_artifact_id)    │
   ├─ course_content                │
   │    (title, description)        │
   ├─ submission_group_member       │
   │    → course_member → user      │
   └─ message                       │
        (student messages)          │
                                    │
            ┌───────────────────────┘
            ▼
    extracted_scenarios/
```

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output`, `-o` | (required) | Output directory |
| `--course-id` | all | Filter by course UUID |
| `--limit` | all | Max scenarios to extract |
| `--skip-files` | false | Skip MinIO download |
| `--db-host` | `localhost` | PostgreSQL host |
| `--db-port` | `5432` | PostgreSQL port |
| `--db-name` | `codeability` | Database name |
| `--db-user` | `postgres` | Database user |
| `--db-password` | `postgres_secret` | Database password |
| `--minio-host` | `localhost:9000` | MinIO endpoint |
| `--minio-access-key` | `minioadmin` | MinIO access key |
| `--minio-secret-key` | `minioadmin` | MinIO secret key |
| `--minio-secure` | false | Use HTTPS for MinIO |
| `--verbose`, `-v` | false | Debug logging |
