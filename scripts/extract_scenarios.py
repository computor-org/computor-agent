#!/usr/bin/env python3
"""
Extract scenarios from the computor database for offline testing.

Extracts submission groups that have:
- An official submission (submit=true)
- A matching grade (graded after the submission was uploaded)

Output per qualifying submission group:
    <output_dir>/<course>__<assignment>__<sg_number>/
    ├── scenario.yaml           # Metadata (obfuscated student name, assignment, grade)
    ├── assignment/
    │   └── description.md      # Assignment README (index_en.md from example repo)
    ├── submission/             # Actual submission files from MinIO
    │   └── *.py
    ├── reference/              # Reference solution files from example repo
    │   └── *.py
    ├── test-results.json       # Test results for the graded artifact
    ├── grade.json              # Grade info (score, status, comment)
    └── prompts/                # Student messages as prompt files
        ├── 001_initial.md
        └── 002_follow_up.md

Usage:
    python scripts/extract_scenarios.py --output ./extracted_scenarios/
    python scripts/extract_scenarios.py --output ./extracted/ --course-id <uuid>
    python scripts/extract_scenarios.py --output ./extracted/ --limit 10
"""

import argparse
import io
import json
import logging
import re
import sys
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras
import yaml
from minio import Minio

logger = logging.getLogger(__name__)


# --- Obfuscation ---

class Obfuscator:
    """Consistent obfuscation of PII across an extraction run."""

    def __init__(self):
        self._name_map: dict[str, str] = {}
        self._email_map: dict[str, str] = {}
        self._counter = 0

    def _next_id(self) -> int:
        self._counter += 1
        return self._counter

    def obfuscate_name(self, given_name: str, family_name: str) -> str:
        """Return a consistent fake name for a real name."""
        key = f"{given_name}|{family_name}"
        if key not in self._name_map:
            n = self._next_id()
            self._name_map[key] = f"Student {n:03d}"
        return self._name_map[key]

    def obfuscate_email(self, email: str) -> str:
        """Return a consistent fake email."""
        if not email:
            return email
        if email not in self._email_map:
            n = self._next_id()
            self._email_map[email] = f"student_{n:03d}@example.com"
        return self._email_map[email]

    def scrub_text(self, text: str) -> str:
        """Remove PII patterns from free text (message content, comments)."""
        if not text:
            return text

        result = text

        # Replace known real names/emails with their obfuscated versions
        for real, fake in self._name_map.items():
            given, family = real.split("|", 1)
            if given and given in result:
                result = result.replace(given, fake.split()[0])
            if family and family in result:
                result = result.replace(family, fake.split()[-1])

        for real, fake in self._email_map.items():
            if real in result:
                result = result.replace(real, fake)

        # Scrub any remaining email-like patterns
        result = re.sub(
            r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+',
            'redacted@example.com',
            result,
        )

        # Scrub GitLab-like URLs (keep structure, replace domain/paths)
        result = re.sub(
            r'https?://[a-zA-Z0-9.-]+(?::\d+)?/[a-zA-Z0-9_./-]+\.git\b',
            'https://gitlab.example.com/org/repo.git',
            result,
        )
        result = re.sub(
            r'https?://(?:gitlab|git)\.[a-zA-Z0-9.-]+(?::\d+)?/[a-zA-Z0-9_./-]+',
            'https://gitlab.example.com/org/repo',
            result,
        )

        return result


# --- Database queries ---

GRADED_SUBMISSIONS_QUERY = """
SELECT
    sg.id AS submission_group_id,
    sg.course_id,
    sg.course_content_id,
    cc.title AS assignment_title,
    cc.description AS assignment_description,
    cc.path AS assignment_path,
    c.title AS course_title,
    sa.id AS artifact_id,
    sa.object_key,
    sa.bucket_name,
    sa.version_identifier,
    sa.uploaded_at,
    sa.file_size,
    sgr.grade,
    sgr.status AS grade_status,
    sgr.comment AS grade_comment,
    sgr.graded_at
FROM submission_group sg
JOIN course_content cc ON cc.id = sg.course_content_id
JOIN course c ON c.id = sg.course_id
JOIN submission_artifact sa ON sa.submission_group_id = sg.id
    AND sa.submit = true
JOIN submission_grade sgr ON sgr.artifact_id = sa.id
    AND sgr.graded_at > sa.uploaded_at
WHERE sg.course_id = COALESCE(%(course_id)s, sg.course_id)
ORDER BY c.title, cc.path, sg.id, sa.uploaded_at ASC
"""

MEMBERS_QUERY = """
SELECT
    sgm.submission_group_id,
    u.id AS user_id,
    u.given_name,
    u.family_name,
    u.email,
    u.username
FROM submission_group_member sgm
JOIN course_member cm ON cm.id = sgm.course_member_id
JOIN "user" u ON u.id = cm.user_id
WHERE sgm.submission_group_id = ANY(%(sg_ids)s::uuid[])
"""

MESSAGES_QUERY = """
SELECT
    m.id,
    m.submission_group_id,
    m.title,
    m.content,
    m.parent_id,
    m.author_id,
    m.created_at,
    u.given_name,
    u.family_name,
    u.is_service
FROM message m
JOIN "user" u ON u.id = m.author_id
WHERE m.submission_group_id = ANY(%(sg_ids)s::uuid[])
    AND m.archived_at IS NULL
ORDER BY m.submission_group_id, m.created_at ASC
"""

TEST_RESULTS_QUERY = """
SELECT
    r.submission_artifact_id,
    r.grade AS test_grade,
    r.status AS test_status,
    r.started_at,
    r.finished_at,
    r.properties
FROM result r
WHERE r.submission_artifact_id = ANY(%(artifact_ids)s::uuid[])
ORDER BY r.created_at ASC
"""

EXAMPLE_VERSION_QUERY = """
SELECT
    ccd.course_content_id,
    ev.storage_path,
    ev.meta_yaml,
    er.source_url
FROM course_content_deployment ccd
JOIN example_version ev ON ev.id = ccd.example_version_id
JOIN example e ON e.id = ev.example_id
JOIN example_repository er ON er.id = e.example_repository_id
WHERE ccd.course_content_id = ANY(%(cc_ids)s::uuid[])
  AND ccd.example_version_id IS NOT NULL
ORDER BY ccd.assigned_at DESC
"""


GRADE_STATUS_MAP = {
    0: "not_reviewed",
    1: "corrected",
    2: "correction_necessary",
    3: "improvement_possible",
}


@dataclass
class ExtractedScenario:
    """All data for one scenario."""
    submission_group_id: str
    course_content_id: str
    course_title: str
    assignment_title: str
    assignment_path: str
    assignment_description: Optional[str]
    grade: float
    grade_status: int
    grade_comment: Optional[str]
    artifact_id: str
    bucket_name: str
    object_key: str
    version_identifier: Optional[str]
    members: list[dict] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    test_results: list[dict] = field(default_factory=list)
    submission_files: dict[str, bytes] = field(default_factory=dict)
    reference_files: dict[str, bytes] = field(default_factory=dict)
    readme_content: Optional[str] = None


def fetch_scenarios(conn, course_id: Optional[str] = None, limit: Optional[int] = None, limit_per_assignment: Optional[int] = None) -> list[ExtractedScenario]:
    """Fetch all qualifying scenarios from the database."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get graded submissions
    cur.execute(GRADED_SUBMISSIONS_QUERY, {"course_id": course_id})
    rows = cur.fetchall()

    if not rows:
        logger.warning("No graded submissions found")
        return []

    # Deduplicate: keep latest graded artifact per submission_group
    seen_sg = set()
    unique_rows = []
    for row in rows:
        sg_id = str(row["submission_group_id"])
        if sg_id not in seen_sg:
            seen_sg.add(sg_id)
            unique_rows.append(row)

    # Cap per assignment (course_content) if requested
    if limit_per_assignment:
        count_per_cc: dict[str, int] = {}
        filtered = []
        for row in unique_rows:
            cc_id = str(row["course_content_id"])
            count_per_cc.setdefault(cc_id, 0)
            if count_per_cc[cc_id] < limit_per_assignment:
                count_per_cc[cc_id] += 1
                filtered.append(row)
        unique_rows = filtered

    if limit:
        unique_rows = unique_rows[:limit]

    sg_ids = [str(r["submission_group_id"]) for r in unique_rows]
    artifact_ids = [str(r["artifact_id"]) for r in unique_rows]

    # Fetch members
    cur.execute(MEMBERS_QUERY, {"sg_ids": sg_ids})
    members_by_sg = defaultdict(list)
    for m in cur.fetchall():
        members_by_sg[str(m["submission_group_id"])].append(dict(m))

    # Fetch messages
    cur.execute(MESSAGES_QUERY, {"sg_ids": sg_ids})
    messages_by_sg = defaultdict(list)
    for m in cur.fetchall():
        messages_by_sg[str(m["submission_group_id"])].append(dict(m))

    # Fetch test results
    cur.execute(TEST_RESULTS_QUERY, {"artifact_ids": artifact_ids})
    results_by_artifact = defaultdict(list)
    for r in cur.fetchall():
        results_by_artifact[str(r["submission_artifact_id"])].append(dict(r))

    # Build scenarios
    scenarios = []
    for row in unique_rows:
        sg_id = str(row["submission_group_id"])
        art_id = str(row["artifact_id"])

        scenario = ExtractedScenario(
            submission_group_id=sg_id,
            course_content_id=str(row["course_content_id"]),
            course_title=row["course_title"] or "Unknown Course",
            assignment_title=row["assignment_title"] or "Unknown Assignment",
            assignment_path=str(row["assignment_path"]) if row["assignment_path"] else "unknown",
            assignment_description=row["assignment_description"],
            grade=float(row["grade"]),
            grade_status=int(row["grade_status"]),
            grade_comment=row["grade_comment"],
            artifact_id=art_id,
            bucket_name=row["bucket_name"],
            object_key=row["object_key"],
            version_identifier=row["version_identifier"],
            members=members_by_sg.get(sg_id, []),
            messages=messages_by_sg.get(sg_id, []),
            test_results=results_by_artifact.get(art_id, []),
        )
        scenarios.append(scenario)

    cur.close()
    return scenarios


def download_submission_files(minio_client: Minio, scenario: ExtractedScenario) -> dict[str, bytes]:
    """Download submission files from MinIO for a scenario."""
    files = {}

    # Object key pattern: submissions/{sg_id}/{version_identifier}/{file_path}
    # or it could be a single zip object
    bucket = scenario.bucket_name
    object_key = scenario.object_key

    try:
        # Try to get the object directly (might be a zip)
        response = minio_client.get_object(bucket, object_key)
        data = response.read()
        response.close()
        response.release_conn()

        # Check if it's a zip
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for name in zf.namelist():
                    if name.endswith("/"):
                        continue  # skip directories
                    files[name] = zf.read(name)
            logger.info(f"Extracted {len(files)} files from ZIP")
        else:
            # Single file — use the last path component as filename
            filename = object_key.rsplit("/", 1)[-1] if "/" in object_key else object_key
            files[filename] = data
            logger.info(f"Downloaded single file: {filename}")

    except Exception as e:
        logger.warning(f"Failed to download {bucket}/{object_key}: {e}")

        # Try listing objects with prefix (version_identifier path)
        if scenario.version_identifier:
            prefix = f"{scenario.submission_group_id}/{scenario.version_identifier}/"
            try:
                objects = minio_client.list_objects(bucket, prefix=prefix, recursive=True)
                for obj in objects:
                    rel_path = obj.object_name[len(prefix):]
                    if not rel_path:
                        continue
                    resp = minio_client.get_object(bucket, obj.object_name)
                    files[rel_path] = resp.read()
                    resp.close()
                    resp.release_conn()
                logger.info(f"Listed and downloaded {len(files)} files from prefix {prefix}")
            except Exception as e2:
                logger.error(f"Failed to list/download from prefix {prefix}: {e2}")

    return files


def fetch_example_data(conn, minio_client: Minio, scenarios: list[ExtractedScenario]):
    """Fetch reference solution files and assignment README from MinIO for each scenario.

    Resolves course_content → deployment → example_version → example → repository
    to find the MinIO bucket and storage path, then downloads:
    - Reference solution files (from meta_yaml properties)
    - Assignment README (content/index_en.md or content/index.md)
    """
    # Collect unique course_content_ids
    cc_ids = list({s.course_content_id for s in scenarios})
    if not cc_ids:
        return

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(EXAMPLE_VERSION_QUERY, {"cc_ids": cc_ids})
    rows = cur.fetchall()
    cur.close()

    # Deduplicate: keep latest deployment per course_content_id
    version_by_cc: dict[str, dict] = {}
    for row in rows:
        cc_id = str(row["course_content_id"])
        if cc_id not in version_by_cc:
            version_by_cc[cc_id] = dict(row)

    if not version_by_cc:
        logger.warning("No example version deployments found for any course content")
        return

    # Cache downloaded data per course_content_id (multiple scenarios may share one)
    cache: dict[str, tuple[dict[str, bytes], Optional[str]]] = {}

    for cc_id, version_info in version_by_cc.items():
        storage_path = version_info["storage_path"]
        meta_yaml_text = version_info["meta_yaml"]
        source_url = version_info["source_url"]
        bucket_name = source_url.split("/")[0]

        # --- Download README ---
        readme_content = None
        for readme_name in ["content/index_en.md", "content/index.md"]:
            object_key = f"{storage_path}/{readme_name}"
            try:
                resp = minio_client.get_object(bucket_name, object_key)
                readme_content = resp.read().decode("utf-8")
                resp.close()
                resp.release_conn()
                logger.debug(f"Downloaded README: {bucket_name}/{object_key}")
                break
            except Exception:
                continue

        if not readme_content:
            logger.warning(f"No README found for CC {cc_id} at {storage_path}/content/")

        # --- Download reference files ---
        ref_files: dict[str, bytes] = {}
        if meta_yaml_text:
            try:
                meta = yaml.safe_load(meta_yaml_text)
                properties = meta.get("properties", {}) if meta else {}
                submission_files = properties.get("studentSubmissionFiles", []) or []
                additional_files = properties.get("additionalFiles", []) or []
                ref_paths = set(submission_files + additional_files)

                for ref_path in ref_paths:
                    if "_master." in ref_path:
                        continue
                    object_key = f"{storage_path}/{ref_path}"
                    try:
                        resp = minio_client.get_object(bucket_name, object_key)
                        ref_files[ref_path] = resp.read()
                        resp.close()
                        resp.release_conn()
                    except Exception as e:
                        logger.warning(f"Failed to download reference file {bucket_name}/{object_key}: {e}")

                logger.info(f"Downloaded {len(ref_files)} reference files for CC {cc_id}")
            except yaml.YAMLError as e:
                logger.warning(f"Failed to parse meta_yaml for CC {cc_id}: {e}")

        cache[cc_id] = (ref_files, readme_content)

    # Attach to scenarios
    for scenario in scenarios:
        if scenario.course_content_id in cache:
            ref_files, readme = cache[scenario.course_content_id]
            scenario.reference_files = ref_files
            scenario.readme_content = readme


def write_scenario(
    scenario: ExtractedScenario,
    output_dir: Path,
    obfuscator: Obfuscator,
    scenario_number: int,
) -> Path:
    """Write a single scenario to disk."""

    # Build directory name
    course_slug = re.sub(r'[^a-z0-9]+', '-', scenario.course_title.lower()).strip('-')[:30]
    assignment_slug = re.sub(r'[^a-z0-9]+', '-', scenario.assignment_title.lower()).strip('-')[:40]
    dir_name = f"{course_slug}__{assignment_slug}__{scenario_number:03d}"
    scenario_dir = output_dir / dir_name
    scenario_dir.mkdir(parents=True, exist_ok=True)

    # Obfuscate student names
    student_names = []
    for member in scenario.members:
        fake_name = obfuscator.obfuscate_name(
            member.get("given_name", ""),
            member.get("family_name", ""),
        )
        student_names.append(fake_name)

    # Pre-register all names/emails in obfuscator for text scrubbing
    for member in scenario.members:
        obfuscator.obfuscate_email(member.get("email", ""))

    # --- scenario.yaml ---
    scenario_yaml = {
        "student": {
            "name": student_names[0] if student_names else "Unknown Student",
        },
        "assignment": {
            "title": scenario.assignment_title,
            "path": scenario.assignment_path,
            "language": "en",
        },
        "grade": {
            "score": round(scenario.grade, 4),
            "status": GRADE_STATUS_MAP.get(scenario.grade_status, "unknown"),
            "comment": obfuscator.scrub_text(scenario.grade_comment) if scenario.grade_comment else None,
        },
        "extracted_from": {
            "course": scenario.course_title,
            "submission_group_id": scenario.submission_group_id,
        },
    }
    (scenario_dir / "scenario.yaml").write_text(
        yaml.dump(scenario_yaml, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )

    # --- assignment/description.md ---
    assignment_dir = scenario_dir / "assignment"
    assignment_dir.mkdir(exist_ok=True)
    description = scenario.readme_content or scenario.assignment_description or "(No description available)"
    (assignment_dir / "description.md").write_text(description, encoding="utf-8")

    # --- submission/ files ---
    if scenario.submission_files:
        sub_dir = scenario_dir / "submission"
        sub_dir.mkdir(exist_ok=True)
        for filename, content in scenario.submission_files.items():
            file_path = sub_dir / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                try:
                    file_path.write_text(content.decode("utf-8"), encoding="utf-8")
                except UnicodeDecodeError:
                    file_path.write_bytes(content)
            else:
                file_path.write_text(content, encoding="utf-8")

    # --- reference/ files ---
    if scenario.reference_files:
        ref_dir = scenario_dir / "reference"
        ref_dir.mkdir(exist_ok=True)
        for filename, content in scenario.reference_files.items():
            file_path = ref_dir / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                try:
                    file_path.write_text(content.decode("utf-8"), encoding="utf-8")
                except UnicodeDecodeError:
                    file_path.write_bytes(content)
            else:
                file_path.write_text(content, encoding="utf-8")

    # --- test-results.json ---
    if scenario.test_results:
        test_data = {
            "total": len(scenario.test_results),
            "passed": sum(1 for r in scenario.test_results if r.get("test_status") == 0),
            "failed": sum(1 for r in scenario.test_results if r.get("test_status") != 0),
            "details": [
                {
                    "status": "passed" if r.get("test_status") == 0 else "failed",
                    "grade": r.get("test_grade"),
                    "started_at": r["started_at"].isoformat() if r.get("started_at") else None,
                    "finished_at": r["finished_at"].isoformat() if r.get("finished_at") else None,
                }
                for r in scenario.test_results
            ],
        }
        (scenario_dir / "test-results.json").write_text(
            json.dumps(test_data, indent=2), encoding="utf-8"
        )

    # --- grade.json ---
    grade_data = {
        "score": round(scenario.grade, 4),
        "percentage": round(scenario.grade * 100, 1),
        "status": GRADE_STATUS_MAP.get(scenario.grade_status, "unknown"),
        "comment": obfuscator.scrub_text(scenario.grade_comment) if scenario.grade_comment else None,
    }
    (scenario_dir / "grade.json").write_text(
        json.dumps(grade_data, indent=2), encoding="utf-8"
    )

    # --- prompts/ (only messages from submission group members) ---
    member_user_ids = {str(m["user_id"]) for m in scenario.members if m.get("user_id")}
    student_messages = [
        m for m in scenario.messages
        if str(m.get("author_id", "")) in member_user_ids
    ]

    if student_messages:
        prompts_dir = scenario_dir / "prompts"
        prompts_dir.mkdir(exist_ok=True)
        for i, msg in enumerate(student_messages, 1):
            content = obfuscator.scrub_text(msg.get("content", ""))
            title = msg.get("title", "")
            # Use title as hint in filename if it has a tag
            suffix = ""
            if title and title.startswith("#"):
                suffix = f"_{re.sub(r'[^a-z0-9]+', '_', title.lower()).strip('_')}"
            filename = f"{i:03d}{suffix}.md"
            (prompts_dir / filename).write_text(content, encoding="utf-8")

    logger.info(f"Written scenario: {dir_name}")
    return scenario_dir


def main():
    parser = argparse.ArgumentParser(description="Extract scenarios from computor database")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Output directory")
    parser.add_argument("--course-id", type=str, default=None, help="Filter by course UUID")
    parser.add_argument("--limit", type=int, default=None, help="Max scenarios to extract (global)")
    parser.add_argument("--limit-per-assignment", type=int, default=None, help="Max scenarios per assignment (course content)")

    # Database connection
    parser.add_argument("--db-host", default="localhost")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-name", default="codeability")
    parser.add_argument("--db-user", default="postgres")
    parser.add_argument("--db-password", default="postgres_secret")

    # MinIO connection
    parser.add_argument("--minio-host", default="localhost:9000")
    parser.add_argument("--minio-access-key", default="minioadmin")
    parser.add_argument("--minio-secret-key", default="minioadmin")
    parser.add_argument("--minio-secure", action="store_true", default=False)

    # Options
    parser.add_argument("--skip-files", action="store_true", help="Skip downloading submission files from MinIO")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    # Connect to database
    logger.info(f"Connecting to PostgreSQL {args.db_host}:{args.db_port}/{args.db_name}")
    conn = psycopg2.connect(
        host=args.db_host,
        port=args.db_port,
        dbname=args.db_name,
        user=args.db_user,
        password=args.db_password,
    )

    # Connect to MinIO (unless skipping files)
    minio_client = None
    if not args.skip_files:
        logger.info(f"Connecting to MinIO at {args.minio_host}")
        minio_client = Minio(
            args.minio_host,
            access_key=args.minio_access_key,
            secret_key=args.minio_secret_key,
            secure=args.minio_secure,
        )

    try:
        # Fetch scenarios
        logger.info("Fetching graded submissions from database...")
        scenarios = fetch_scenarios(conn, course_id=args.course_id, limit=args.limit, limit_per_assignment=args.limit_per_assignment)
        logger.info(f"Found {len(scenarios)} qualifying scenarios")

        if not scenarios:
            logger.warning("No scenarios to extract. Check that submissions are graded.")
            return

        # Download submission files
        if minio_client:
            for i, scenario in enumerate(scenarios, 1):
                logger.info(f"Downloading files for scenario {i}/{len(scenarios)}: {scenario.assignment_title}")
                scenario.submission_files = download_submission_files(minio_client, scenario)

            # Fetch reference solutions and assignment READMEs
            logger.info("Fetching reference solutions and assignment READMEs...")
            fetch_example_data(conn, minio_client, scenarios)

        # Write scenarios
        obfuscator = Obfuscator()
        args.output.mkdir(parents=True, exist_ok=True)

        written = []
        for i, scenario in enumerate(scenarios, 1):
            path = write_scenario(scenario, args.output, obfuscator, i)
            written.append(path)

        # Summary
        logger.info(f"\nExtraction complete:")
        logger.info(f"  Scenarios: {len(written)}")
        logger.info(f"  Output: {args.output}")
        for p in written:
            has_files = (p / "submission").exists() and any((p / "submission").iterdir())
            has_prompts = (p / "prompts").exists() and any((p / "prompts").iterdir())
            has_ref = (p / "reference").exists() and any((p / "reference").iterdir())
            logger.info(f"  - {p.name} (files={'yes' if has_files else 'no'}, ref={'yes' if has_ref else 'no'}, prompts={'yes' if has_prompts else 'no'})")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
