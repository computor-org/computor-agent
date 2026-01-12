"""
Prompt loader for reading prompts from markdown files.

Supports hot reloading in development mode.
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

logger = logging.getLogger(__name__)


class PromptFileHandler(FileSystemEventHandler):
    """Handles file system events for prompt files."""

    def __init__(self, loader: "PromptLoader", callback=None):
        self.loader = loader
        self.callback = callback
        super().__init__()

    def on_modified(self, event):
        """Called when a file is modified."""
        if not isinstance(event, FileModifiedEvent):
            return

        if event.src_path.endswith('.md'):
            # Reload the modified file
            file_path = Path(event.src_path)
            if file_path.exists():
                logger.info(f"Prompt file modified: {file_path.name}")
                self.loader.reload_file(file_path)

                # Call callback if provided (for CLI notification)
                if self.callback:
                    self.callback(file_path.name)


class PromptLoader:
    """
    Loads prompts from markdown files and provides hot reload capability.

    Directory structure:
    prompts/
    ├── personality/
    │   ├── friendly_professional.md
    │   ├── strict.md
    │   ├── casual.md
    │   └── encouraging.md
    ├── strategy/
    │   ├── question_example.md
    │   ├── question_howto.md
    │   ├── help_debug.md
    │   ├── help_review.md
    │   ├── clarification.md
    │   └── fallback.md
    └── security/
        ├── detection.md
        └── confirmation.md
    """

    def __init__(
        self,
        prompts_dir: Optional[Path] = None,
        enable_hot_reload: bool = False,
        reload_callback=None
    ):
        """
        Initialize the prompt loader.

        Args:
            prompts_dir: Directory containing prompt files
            enable_hot_reload: Enable file watching for hot reload
            reload_callback: Callback function called on reload (receives filename)
        """
        self.prompts_dir = prompts_dir or self._get_default_prompts_dir()
        self.enable_hot_reload = enable_hot_reload
        self.reload_callback = reload_callback

        # Cache for loaded prompts
        self._personality_prompts: Dict[str, str] = {}
        self._strategy_prompts: Dict[str, str] = {}
        self._security_prompts: Dict[str, str] = {}

        # File watcher
        self._observer: Optional[Observer] = None

        # Load all prompts
        self.load_all()

        # Start file watcher if hot reload is enabled
        if enable_hot_reload:
            self.start_watching()

    def _get_default_prompts_dir(self) -> Path:
        """Get the default prompts directory."""
        # Try config directory first
        config_dir = Path.home() / ".computor" / "prompts"
        if config_dir.exists():
            return config_dir

        # Fall back to package directory
        package_dir = Path(__file__).parent / "templates"
        return package_dir

    def load_all(self) -> None:
        """Load all prompt files."""
        logger.info(f"Loading prompts from: {self.prompts_dir}")

        # Load personality prompts
        personality_dir = self.prompts_dir / "personality"
        if personality_dir.exists():
            for file_path in personality_dir.glob("*.md"):
                self._load_personality_prompt(file_path)

        # Load strategy prompts
        strategy_dir = self.prompts_dir / "strategy"
        if strategy_dir.exists():
            for file_path in strategy_dir.glob("*.md"):
                self._load_strategy_prompt(file_path)

        # Load security prompts
        security_dir = self.prompts_dir / "security"
        if security_dir.exists():
            for file_path in security_dir.glob("*.md"):
                self._load_security_prompt(file_path)

        logger.info(f"Loaded {len(self._personality_prompts)} personality prompts")
        logger.info(f"Loaded {len(self._strategy_prompts)} strategy prompts")
        logger.info(f"Loaded {len(self._security_prompts)} security prompts")

    def reload_file(self, file_path: Path) -> None:
        """Reload a specific prompt file."""
        relative_path = file_path.relative_to(self.prompts_dir)
        category = relative_path.parts[0] if relative_path.parts else None

        if category == "personality":
            self._load_personality_prompt(file_path)
        elif category == "strategy":
            self._load_strategy_prompt(file_path)
        elif category == "security":
            self._load_security_prompt(file_path)
        else:
            logger.warning(f"Unknown prompt category: {category}")

    def _load_personality_prompt(self, file_path: Path) -> None:
        """Load a personality prompt file."""
        if not file_path.exists():
            return

        key = file_path.stem  # filename without extension
        content = self._read_prompt_file(file_path)
        if content:
            self._personality_prompts[key] = content
            logger.debug(f"Loaded personality prompt: {key}")

    def _load_strategy_prompt(self, file_path: Path) -> None:
        """Load a strategy prompt file."""
        if not file_path.exists():
            return

        key = file_path.stem
        content = self._read_prompt_file(file_path)
        if content:
            self._strategy_prompts[key] = content
            logger.debug(f"Loaded strategy prompt: {key}")

    def _load_security_prompt(self, file_path: Path) -> None:
        """Load a security prompt file."""
        if not file_path.exists():
            return

        key = file_path.stem
        content = self._read_prompt_file(file_path)
        if content:
            self._security_prompts[key] = content
            logger.debug(f"Loaded security prompt: {key}")

    def _read_prompt_file(self, file_path: Path) -> Optional[str]:
        """
        Read a prompt from a markdown file.

        The file can have optional frontmatter (YAML between --- markers)
        which will be stripped. The rest is the prompt content.
        """
        try:
            content = file_path.read_text()

            # Strip frontmatter if present
            if content.startswith("---"):
                # Find the closing ---
                match = re.match(r'^---\n.*?\n---\n(.*)$', content, re.DOTALL)
                if match:
                    content = match.group(1)

            # Strip leading/trailing whitespace but preserve internal formatting
            return content.strip()

        except Exception as e:
            logger.error(f"Failed to read prompt file {file_path}: {e}")
            return None

    def get_personality_prompt(self, tone: str) -> Optional[str]:
        """Get a personality prompt by tone."""
        return self._personality_prompts.get(
            tone,
            self._personality_prompts.get("friendly_professional")
        )

    def get_strategy_prompt(self, strategy: str) -> Optional[str]:
        """Get a strategy prompt."""
        return self._strategy_prompts.get(
            strategy,
            self._strategy_prompts.get("fallback")
        )

    def get_security_prompt(self, prompt_type: str) -> Optional[str]:
        """Get a security prompt."""
        return self._security_prompts.get(prompt_type)

    def get_all_personality_prompts(self) -> Dict[str, str]:
        """Get all personality prompts."""
        return self._personality_prompts.copy()

    def get_all_strategy_prompts(self) -> Dict[str, str]:
        """Get all strategy prompts."""
        return self._strategy_prompts.copy()

    def start_watching(self) -> None:
        """Start watching prompt files for changes."""
        if self._observer is not None:
            logger.warning("File watcher already running")
            return

        logger.info("Starting file watcher for hot reload")

        self._observer = Observer()
        handler = PromptFileHandler(self, self.reload_callback)
        self._observer.schedule(handler, str(self.prompts_dir), recursive=True)
        self._observer.start()

    def stop_watching(self) -> None:
        """Stop watching prompt files."""
        if self._observer is None:
            return

        logger.info("Stopping file watcher")
        self._observer.stop()
        self._observer.join()
        self._observer = None

    def __del__(self):
        """Cleanup file watcher on deletion."""
        if hasattr(self, '_observer') and self._observer:
            self.stop_watching()


# Global instance for easy access
_prompt_loader: Optional[PromptLoader] = None


def get_prompt_loader(
    prompts_dir: Optional[Path] = None,
    enable_hot_reload: bool = False,
    reload_callback=None,
    force_reload: bool = False
) -> PromptLoader:
    """
    Get the global prompt loader instance.

    Args:
        prompts_dir: Directory containing prompt files
        enable_hot_reload: Enable file watching for hot reload
        reload_callback: Callback function for reload events
        force_reload: Force creation of a new loader

    Returns:
        PromptLoader instance
    """
    global _prompt_loader

    if _prompt_loader is None or force_reload:
        _prompt_loader = PromptLoader(prompts_dir, enable_hot_reload, reload_callback)

    return _prompt_loader


def get_personality_prompt(tone: str) -> str:
    """Get a personality prompt, falling back to templates.py if needed."""
    loader = get_prompt_loader()
    prompt = loader.get_personality_prompt(tone)

    if prompt is None:
        # Fall back to hardcoded templates
        from computor_agent.tutor.prompts.templates import PERSONALITY_PROMPTS
        prompt = PERSONALITY_PROMPTS.get(tone, PERSONALITY_PROMPTS["friendly_professional"])

    return prompt


def get_strategy_prompt(strategy: str) -> str:
    """Get a strategy prompt, falling back to templates.py if needed."""
    loader = get_prompt_loader()
    prompt = loader.get_strategy_prompt(strategy)

    if prompt is None:
        # Fall back to hardcoded templates
        from computor_agent.tutor.prompts.templates import STRATEGY_PROMPTS
        prompt = STRATEGY_PROMPTS.get(strategy, STRATEGY_PROMPTS["fallback"])

    return prompt