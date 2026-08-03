"""The documented prompt overrides must be reachable and must actually apply.

Three separate ways an override silently did nothing:

- the live messaging prompt was only readable through a private loader
  attribute, and nothing ever created the `strategy/tutor.md` it looked for;
- the default prompts directory pointed at `<package>/templates`, which has
  never existed (the prompts live in `templates.py`, a module), so every start
  logged "Loaded 0 prompts";
- a custom grading rubric was passed to a grader that only consults it on the
  single-step path, while defaulting to multi-step.
"""

from pathlib import Path

import pytest

from computor_agent.tutor.prompts import loader as loader_module
from computor_agent.tutor.prompts.loader import PromptLoader, get_tutor_prompt
from computor_agent.tutor.prompts.templates import TUTOR_SYSTEM_PROMPT


@pytest.fixture(autouse=True)
def _reset_global_loader():
    """The loader is a module-level singleton; don't leak it between tests."""
    original = loader_module._prompt_loader
    yield
    loader_module._prompt_loader = original


def _write(prompts_dir: Path, relative: str, text: str) -> None:
    path = prompts_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class TestTutorPromptAccessor:
    def test_falls_back_to_the_built_in_prompt(self, tmp_path):
        loader_module._prompt_loader = PromptLoader(prompts_dir=tmp_path, enable_hot_reload=False)

        assert get_tutor_prompt() == TUTOR_SYSTEM_PROMPT

    def test_a_tutor_md_override_is_used(self, tmp_path):
        _write(tmp_path, "strategy/tutor.md", "MY OWN PROMPT")
        loader_module._prompt_loader = PromptLoader(prompts_dir=tmp_path, enable_hot_reload=False)

        assert get_tutor_prompt() == "MY OWN PROMPT"

    def test_frontmatter_is_stripped_from_the_override(self, tmp_path):
        _write(tmp_path, "strategy/tutor.md", "---\ntitle: x\n---\n\nMY OWN PROMPT")
        loader_module._prompt_loader = PromptLoader(prompts_dir=tmp_path, enable_hot_reload=False)

        assert get_tutor_prompt() == "MY OWN PROMPT"

    def test_a_retired_fallback_prompt_is_not_used_as_the_tutor_prompt(self, tmp_path):
        """The dangerous near-miss: fallback.md must not stand in for tutor.md."""
        _write(tmp_path, "strategy/fallback.md", "RETIRED INTENT PROMPT")
        loader_module._prompt_loader = PromptLoader(prompts_dir=tmp_path, enable_hot_reload=False)

        assert get_tutor_prompt() == TUTOR_SYSTEM_PROMPT

    def test_the_agent_uses_the_public_accessor(self):
        import inspect
        from computor_agent.tutor.agent import TutorAgent

        source = inspect.getsource(TutorAgent._build_system_prompt)
        assert "get_tutor_prompt" in source
        assert "_strategy_prompts" not in source, "no reaching into loader internals"


class TestDefaultPromptsDir:
    def test_default_is_the_documented_location(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        loader = PromptLoader.__new__(PromptLoader)

        assert loader._get_default_prompts_dir() == tmp_path / ".computor" / "prompts"

    def test_a_missing_directory_is_not_an_error(self, tmp_path):
        loader = PromptLoader(prompts_dir=tmp_path / "nope", enable_hot_reload=False)

        assert loader.get_strategy_prompt_exact("tutor") is None


class TestGradingPromptOverride:
    def test_a_custom_rubric_selects_the_path_that_uses_it(self):
        from computor_agent.tutor.grading.grader import SubmissionGrader

        grader = SubmissionGrader(llm=object(), prompt_template="MY RUBRIC")

        assert grader.prompt_template == "MY RUBRIC"
        assert grader.use_multi_step is False, (
            "a custom template is only consumed by the single-step path"
        )

    def test_multi_step_stays_the_default_without_a_custom_rubric(self):
        from computor_agent.tutor.grading.grader import SubmissionGrader

        assert SubmissionGrader(llm=object()).use_multi_step is True

    def test_an_explicit_choice_still_wins(self):
        from computor_agent.tutor.grading.grader import SubmissionGrader

        grader = SubmissionGrader(
            llm=object(), prompt_template="MY RUBRIC", use_multi_step=True
        )

        assert grader.use_multi_step is True


def test_dev_mode_bootstraps_the_tutor_prompt(tmp_path):
    """`strategy/tutor.md` must be created, or the override is undiscoverable."""
    from computor_agent.tutor.dev_mode import _ensure_prompt_files

    _ensure_prompt_files(tmp_path)

    tutor_md = tmp_path / "strategy" / "tutor.md"
    assert tutor_md.exists()

    loader_module._prompt_loader = PromptLoader(prompts_dir=tmp_path, enable_hot_reload=False)
    # Round-trips through the frontmatter writer/reader unchanged.
    assert get_tutor_prompt() == TUTOR_SYSTEM_PROMPT
