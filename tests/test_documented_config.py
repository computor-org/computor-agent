"""The configuration we document must be configuration that actually loads.

`docs/tutor-agent.md` shipped a `config.yaml` example that the schema rejects:
`triggers.request_tags` as `{scope, value}` dicts, `response_tag` as a dict, and
a `tutor.scheduler:` section that moved to the top level. Since every config
model sets `extra="forbid"`, anyone copying the documented example got a
validation error rather than a running agent.
"""

from pathlib import Path

import pytest
import yaml

from computor_agent.settings.config import AgentConfig


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = REPO_ROOT / "docs" / "tutor-agent.md"
EXAMPLE = REPO_ROOT / "config.example.yaml"


def _yaml_blocks(markdown: str) -> list[str]:
    """Every ```yaml fenced block in a markdown document."""
    blocks, inside, current = [], False, []
    for line in markdown.splitlines():
        if line.strip().startswith("```yaml"):
            inside, current = True, []
            continue
        if inside and line.strip().startswith("```"):
            blocks.append("\n".join(current))
            inside = False
            continue
        if inside:
            current.append(line)
    return blocks


def test_the_documented_config_example_validates():
    """The full config.yaml example must load against the real schema."""
    body = DOC.read_text().split("### config.yaml", 1)[1]
    block = body.split("```yaml", 1)[1].split("```", 1)[0]

    AgentConfig(**yaml.safe_load(block))


def test_the_shipped_example_config_validates():
    data = yaml.safe_load(EXAMPLE.read_text()) or {}
    AgentConfig(**data)


def test_every_documented_yaml_block_is_at_least_parseable():
    for index, block in enumerate(_yaml_blocks(DOC.read_text())):
        try:
            yaml.safe_load(block)
        except yaml.YAMLError as e:  # pragma: no cover - only on a bad edit
            pytest.fail(f"YAML block #{index} in {DOC.name} does not parse: {e}")


@pytest.mark.parametrize("stale", [
    "#ai::request",
    "#ai::response",
    "request_tags:",
    "response_tag:",
    "require_all_tags",
    "HTTP Polling",
    "tutor.scheduler",
])
def test_docs_do_not_describe_the_retired_architecture(stale):
    """Activation is @mention-based and the transport is WebSocket-only."""
    assert stale not in DOC.read_text(), (
        f"{DOC.name} still documents {stale!r}, which no longer exists"
    )


@pytest.mark.parametrize("path", [EXAMPLE, REPO_ROOT / "docker" / "README.md"])
def test_scheduler_is_documented_at_the_top_level(path):
    """`scheduler:` is a top-level key; `tutor.scheduler` is rejected."""
    assert "tutor.scheduler" not in path.read_text()
