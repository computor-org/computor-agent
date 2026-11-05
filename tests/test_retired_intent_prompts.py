"""The per-intent prompts and request tags stay retired (issues#596).

Replies come from one unified prompt (`strategy/tutor.md`) and a conversation
starts with an @mention, but dev mode still wrote `question_example.md` and the
other per-intent prompts into every prompts directory, `/new` announced an
`#ai::request` tag (and did not start a new thread), the CLI help spoke of
trigger tags, and the example config offered a username/password login.
"""

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[1]


def _strategy_files(prompts_dir: Path) -> list[str]:
    return sorted(path.name for path in (prompts_dir / "strategy").iterdir())


def test_dev_mode_writes_only_the_live_strategy_prompt(tmp_path):
    from computor_agent.tutor.dev_mode import _ensure_prompt_files

    _ensure_prompt_files(tmp_path)

    assert _strategy_files(tmp_path) == ["tutor.md"]


def test_the_exporter_writes_the_live_tutor_prompt(tmp_path):
    from computor_agent.tutor.prompts.export_defaults import export_prompts

    export_prompts(tmp_path)

    assert _strategy_files(tmp_path) == ["tutor.md"]


class TestDevModeThreads:
    @pytest.fixture
    def scheduler(self):
        from computor_agent.tutor.dev_mode import DevelopmentScheduler, MessageSimulator

        return DevelopmentScheduler(agent=None, simulator=MessageSimulator())

    async def test_new_starts_a_new_thread(self, scheduler, capsys):
        assert await scheduler._handle_command("/new", "previous") is None
        assert "#ai::request" not in capsys.readouterr().out

    async def test_reply_continues_the_named_message(self, scheduler):
        message = scheduler.simulator.create_message("first", mention_agent=True)

        assert await scheduler._handle_command(f"/reply {message.id}", None) == message.id
        assert await scheduler._handle_command("/reply unknown", "previous") == "previous"

    async def test_clear_starts_a_new_thread(self, scheduler):
        assert await scheduler._handle_command("/clear", "previous") is None

    async def test_other_commands_keep_the_thread(self, scheduler):
        assert await scheduler._handle_command("/show", "previous") == "previous"


def test_messaging_help_describes_mentions():
    from computor_agent.cli.main import cli

    result = CliRunner().invoke(cli, ["tutor", "messaging", "--help"])

    assert result.exit_code == 0
    assert "@mention" in result.output
    assert "tag" not in result.output.lower()


def test_the_example_config_offers_no_password_login():
    example = REPO_ROOT / "examples" / "config.example.yaml"
    text = example.read_text()

    assert "username:" not in text
    assert "password:" not in text
    assert yaml.safe_load(text)["backend"]["api_token"].startswith("ctp_")
