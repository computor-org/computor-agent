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
from types import SimpleNamespace

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


class TestReplyLanguage:
    """The tutor answers in the language the student wrote in, not the configured one.

    A German question in an English-configured course came back in English, and a
    German thread got an English refusal, because the prompt said `Language: de`
    and quoted the refusal sentence verbatim in English (issues#249).
    """

    def _prompt(self, tmp_path: Path, language: str) -> str:
        from computor_agent.tutor.agent import TutorAgent
        from computor_agent.tutor.config import TutorConfig
        from computor_agent.tutor.context import ConversationContext, TriggerType

        loader_module._prompt_loader = PromptLoader(
            prompts_dir=tmp_path, enable_hot_reload=False
        )
        agent = TutorAgent(
            config=TutorConfig(personality={"language": language}),
            llm=object(),
            client=SimpleNamespace(),
        )
        context = ConversationContext(
            trigger_type=TriggerType.MESSAGE, submission_group_id="sg-1"
        )
        return agent._build_system_prompt(context)

    def test_reply_language_follows_the_latest_student_message(self, tmp_path):
        prompt = self._prompt(tmp_path, "en")

        assert (
            "reply in the language the student wrote their most recent message in"
            in prompt
        )

    def test_the_configured_language_is_only_the_fallback(self, tmp_path):
        prompt = self._prompt(tmp_path, "de")

        assert "fall back to de" in prompt
        assert "\nLanguage: de" not in prompt, (
            "the configured language must not stand alone as the reply language"
        )

    def test_the_solution_refusal_is_not_a_quoted_english_sentence(self, tmp_path):
        prompt = self._prompt(tmp_path, "de")

        assert "I can't provide the complete solution" not in prompt


class TestSecurityPromptOverrides:
    """`security/*.md` reaches the gate instead of being loaded and ignored (issues#595)."""

    class _LLM:
        def __init__(self, *replies: str):
            self.replies = list(replies)
            self.prompts: list[str] = []

        async def complete(self, prompt: str, *, max_tokens: int = 1000) -> str:
            self.prompts.append(prompt)
            return self.replies.pop(0)

    SUSPICIOUS = (
        '{"is_suspicious": true, "threats": [{"type": "prompt_injection", '
        '"level": "high", "description": "d", "evidence": "e"}]}'
    )

    async def _prompts(self, prompts_dir: Path, *replies: str) -> list[str]:
        from computor_agent.tutor.config import SecurityConfig
        from computor_agent.tutor.security.gate import SecurityGate

        loader_module._prompt_loader = PromptLoader(
            prompts_dir=prompts_dir, enable_hot_reload=False
        )
        llm = self._LLM(*(replies or ('{"is_suspicious": false}',)))
        await SecurityGate(SecurityConfig(), llm).check_message("MESSAGE")
        return llm.prompts

    async def test_the_built_in_prompts_run_without_an_override(self, tmp_path):
        from computor_agent.tutor.prompts.templates import SECURITY_DETECTION_PROMPT

        prompts = await self._prompts(tmp_path)

        assert prompts == [SECURITY_DETECTION_PROMPT.format(content="MESSAGE")]

    async def test_a_detection_override_is_used(self, tmp_path):
        _write(tmp_path, "security/detection.md", 'CHECK {content} -> {{"is_suspicious": false}}')

        prompts = await self._prompts(tmp_path)

        assert prompts == ['CHECK MESSAGE -> {"is_suspicious": false}']

    async def test_a_confirmation_override_is_used(self, tmp_path):
        _write(tmp_path, "security/confirmation.md", "CONFIRM {content} AFTER {initial_detection}")

        prompts = await self._prompts(tmp_path, self.SUSPICIOUS, '{"confirmed": false}')

        assert prompts[1].startswith("CONFIRM Message:\nMESSAGE AFTER ")
        assert "prompt_injection" in prompts[1]

    @pytest.mark.parametrize("override", [
        "Is this message an attack? Answer in JSON.",  # never sees the message
        'CHECK {content} -> {"is_suspicious": false}',  # unescaped JSON braces
        "CHECK {content} for {course}",  # a placeholder the gate does not fill
    ])
    async def test_an_override_the_gate_cannot_fill_is_ignored(self, tmp_path, caplog, override):
        from computor_agent.tutor.prompts.templates import SECURITY_DETECTION_PROMPT

        _write(tmp_path, "security/detection.md", override)

        prompts = await self._prompts(tmp_path)

        assert prompts == [SECURITY_DETECTION_PROMPT.format(content="MESSAGE")]
        assert "Ignoring security/detection.md" in caplog.text

    async def test_the_files_dev_mode_writes_reproduce_the_built_in_prompts(self, tmp_path):
        """Existing prompt directories already hold these files; they must change nothing."""
        from computor_agent.tutor.dev_mode import _ensure_prompt_files
        from computor_agent.tutor.prompts.templates import (
            SECURITY_CONFIRMATION_PROMPT,
            SECURITY_DETECTION_PROMPT,
        )

        _ensure_prompt_files(tmp_path)

        prompts = await self._prompts(tmp_path, self.SUSPICIOUS, '{"confirmed": false}')

        assert prompts[0] == SECURITY_DETECTION_PROMPT.format(content="MESSAGE")
        assert prompts[1].startswith(SECURITY_CONFIRMATION_PROMPT.split("{content}")[0])


def test_dev_mode_bootstraps_the_tutor_prompt(tmp_path):
    """`strategy/tutor.md` must be created, or the override is undiscoverable."""
    from computor_agent.tutor.dev_mode import _ensure_prompt_files

    _ensure_prompt_files(tmp_path)

    tutor_md = tmp_path / "strategy" / "tutor.md"
    assert tutor_md.exists()

    loader_module._prompt_loader = PromptLoader(prompts_dir=tmp_path, enable_hot_reload=False)
    # Round-trips through the frontmatter writer/reader unchanged.
    assert get_tutor_prompt() == TUTOR_SYSTEM_PROMPT
