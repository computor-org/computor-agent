"""Options for the tutor agent runtime."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class RuntimeOptions:
    """CLI-level options for a messaging-agent run."""

    dry_run: bool = False
    prompts_dir: Optional[Path] = None
    api_port: Optional[int] = None
    api_host: str = "127.0.0.1"
    log_file: Optional[str] = None
    llm_probe_interval: float = 30.0
