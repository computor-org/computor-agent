"""Probe the /messages API with the tutor's config to see what the backend returns.

Usage:
    python scripts/probe_messages.py [--config config.yaml]

Prints each unread message for every tutored course along with parent_id,
title, scope fields, and is_deleted — so we can tell whether a reply that
should trigger the agent is actually being returned by the backend.
"""

import argparse
import asyncio
from pathlib import Path

import yaml
from computor_client import ComputorClient


async def main(config_path: Path) -> None:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    backend = cfg["backend"]
    base_url = backend["url"]
    token = backend.get("api_token")

    async with ComputorClient(base_url=base_url) as client:
        if token:
            client._auth_provider._token = token  # API-token auth
        else:
            await client.login(
                username=backend["username"],
                password=backend["password"],
            )

        courses = await client.tutors.get_courses()
        if not courses:
            print("No tutored courses.")
            return

        for course in courses:
            print(f"\n=== course {course.id} ({getattr(course, 'title', '?')}) ===")
            unread = await client.messages.list(course_id=course.id, unread=True)
            print(f"total unread: {len(unread or [])}")
            for m in (unread or []):
                print(
                    f"  id={m.id}"
                    f"  parent={getattr(m, 'parent_id', None)}"
                    f"  sg={getattr(m, 'submission_group_id', None)}"
                    f"  cc={getattr(m, 'course_content_id', None)}"
                    f"  course={getattr(m, 'course_id', None)}"
                    f"  deleted={getattr(m, 'is_deleted', False)}"
                    f"  title={getattr(m, 'title', None)!r}"
                )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml", type=Path)
    args = ap.parse_args()
    asyncio.run(main(args.config))
