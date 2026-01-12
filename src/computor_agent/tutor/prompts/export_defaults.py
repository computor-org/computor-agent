#!/usr/bin/env python3
"""
Export default prompts to markdown files.

This utility creates the default prompt files in markdown format.
"""

import os
from pathlib import Path
from typing import Optional

from computor_agent.tutor.prompts.templates import (
    PERSONALITY_PROMPTS,
    STRATEGY_PROMPTS,
    SECURITY_DETECTION_PROMPT,
    SECURITY_CONFIRMATION_PROMPT,
)


def export_prompts(target_dir: Optional[Path] = None):
    """
    Export all default prompts to markdown files.

    Args:
        target_dir: Directory to export to (default: ~/.computor/prompts)
    """
    if target_dir is None:
        target_dir = Path.home() / ".computor" / "prompts"

    # Create directories
    personality_dir = target_dir / "personality"
    strategy_dir = target_dir / "strategy"
    security_dir = target_dir / "security"

    for dir_path in [personality_dir, strategy_dir, security_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)

    print(f"Exporting prompts to: {target_dir}")

    # Export personality prompts
    for tone, prompt in PERSONALITY_PROMPTS.items():
        file_path = personality_dir / f"{tone}.md"
        write_prompt_file(file_path, prompt, f"Personality: {tone}")
        print(f"  ✓ {file_path.relative_to(target_dir)}")

    # Export strategy prompts
    for strategy, prompt in STRATEGY_PROMPTS.items():
        file_path = strategy_dir / f"{strategy}.md"
        write_prompt_file(file_path, prompt, f"Strategy: {strategy}")
        print(f"  ✓ {file_path.relative_to(target_dir)}")

    # Export security prompts
    security_prompts = {
        "detection": SECURITY_DETECTION_PROMPT,
        "confirmation": SECURITY_CONFIRMATION_PROMPT,
    }

    for name, prompt in security_prompts.items():
        file_path = security_dir / f"{name}.md"
        write_prompt_file(file_path, prompt, f"Security: {name}")
        print(f"  ✓ {file_path.relative_to(target_dir)}")

    print(f"\nExported {len(PERSONALITY_PROMPTS)} personality prompts")
    print(f"Exported {len(STRATEGY_PROMPTS)} strategy prompts")
    print(f"Exported {len(security_prompts)} security prompts")
    print(f"\nYou can now edit these files, and changes will hot-reload in dev mode!")


def write_prompt_file(file_path: Path, content: str, title: str = ""):
    """
    Write a prompt to a markdown file with optional frontmatter.

    Args:
        file_path: Path to write to
        content: Prompt content
        title: Optional title for frontmatter
    """
    # Add frontmatter with metadata
    frontmatter = f"""---
title: {title}
generated: true
editable: true
---

"""

    # Write the file
    full_content = frontmatter + content
    file_path.write_text(full_content)


if __name__ == "__main__":
    import sys

    # Allow specifying target directory
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    else:
        target = None

    export_prompts(target)