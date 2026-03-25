#!/usr/bin/env python3
"""
Batch-run the tutor agent against pre-defined scenarios.

Evaluates LLM response quality across models and prompts by processing
each prompt file through the full tutor pipeline (context building,
security checks, response generation).

Usage:
    python scripts/run_scenarios.py ./examples/scenarios/
    python scripts/run_scenarios.py ./examples/scenarios/ --model mistral:7b
    python scripts/run_scenarios.py ./examples/scenarios/ -s python-basics
    python scripts/run_scenarios.py ./examples/scenarios/ -o ./results/
    python scripts/run_scenarios.py ./examples/scenarios/ -v
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class PromptResult:
    """Result of processing a single prompt file."""
    file: str
    success: bool
    processing_time_ms: float = 0.0
    response_chars: int = 0
    blocked: bool = False
    error: Optional[str] = None
    response_content: Optional[str] = None  # actual LLM text (not serialized to summary)


@dataclass
class ScenarioResult:
    """Result of running all prompts for a scenario."""
    name: str
    assignment: str
    total_time_s: float = 0.0
    prompts: list[PromptResult] = field(default_factory=list)


@dataclass
class RunSummary:
    """Overall run summary, serialized to summary.json."""
    model: str
    provider: str
    timestamp: str
    total_scenarios: int = 0
    total_prompts: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_time_s: float = 0.0
    avg_processing_time_ms: float = 0.0
    scenarios: list[ScenarioResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "provider": self.provider,
            "timestamp": self.timestamp,
            "total_scenarios": self.total_scenarios,
            "total_prompts": self.total_prompts,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "total_time_s": round(self.total_time_s, 2),
            "avg_processing_time_ms": round(self.avg_processing_time_ms, 1),
            "scenarios": [
                {
                    "name": s.name,
                    "assignment": s.assignment,
                    "total_time_s": round(s.total_time_s, 2),
                    "prompts": [
                        {
                            "file": p.file,
                            "success": p.success,
                            "processing_time_ms": round(p.processing_time_ms, 1),
                            "response_chars": p.response_chars,
                            "blocked": p.blocked,
                            "error": p.error,
                        }
                        for p in s.prompts
                    ],
                }
                for s in self.scenarios
            ],
        }


# ---------------------------------------------------------------------------
# Silent mock client (suppresses Rich console output from dev_mode)
# ---------------------------------------------------------------------------

class SilentMockMessagesEndpoint:
    """MockMessagesEndpoint that stores messages without printing to console."""

    def __init__(self, simulator):
        self.simulator = simulator

    async def list(self, **kwargs):
        from computor_agent.tutor.dev_mode import MockMessagesEndpoint
        return await MockMessagesEndpoint(self.simulator).list(**kwargs)

    async def get(self, id: str):
        from computor_agent.tutor.dev_mode import MockMessagesEndpoint
        return await MockMessagesEndpoint(self.simulator).get(id=id)

    async def create(self, data: dict):
        from computor_agent.tutor.dev_mode import MockMessage, MockMessageResponse
        message = MockMessage(
            content=data.get("content", ""),
            title=data.get("title", ""),
            parent_id=data.get("parent_id"),
            submission_group_id=data.get(
                "submission_group_id",
                self.simulator.current_submission_group_id,
            ),
        )
        self.simulator.messages[message.id] = message
        return MockMessageResponse(
            id=message.id,
            content=message.content,
            title=message.title,
            parent_id=message.parent_id,
        )

    async def reads(self, id: str):
        if id in self.simulator.messages:
            self.simulator.messages[id].unread = False


class SilentMockComputorClient:
    """MockComputorClient with silent messages endpoint."""

    def __init__(self, simulator, scenario=None):
        from computor_agent.tutor.dev_mode import (
            MockTutorsEndpoint,
            MockCourseMembersEndpoint,
            MockSubmissionGroupsEndpoint,
            MockSubmissionsEndpoint,
        )
        self.simulator = simulator
        self.messages = SilentMockMessagesEndpoint(simulator)
        self.tutors = MockTutorsEndpoint()
        self.course_members = MockCourseMembersEndpoint()
        self.submission_groups = MockSubmissionGroupsEndpoint()
        self.submissions = MockSubmissionsEndpoint(scenario=scenario)

    async def login(self, username: str, password: str):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# Scenario discovery
# ---------------------------------------------------------------------------

def discover_scenarios(
    scenarios_dir: Path,
    name_filter: Optional[str] = None,
) -> list[Path]:
    """Find valid scenario subdirectories (must have scenario.yaml + prompts/*.md)."""
    scenarios = []
    for child in sorted(scenarios_dir.iterdir()):
        if not child.is_dir():
            continue
        if not (child / "scenario.yaml").exists():
            logger.debug(f"Skipping {child.name}: no scenario.yaml")
            continue
        prompts_dir = child / "prompts"
        if not prompts_dir.is_dir() or not list(prompts_dir.glob("*.md")):
            logger.debug(f"Skipping {child.name}: no prompts/*.md files")
            continue
        if name_filter and name_filter.lower() not in child.name.lower():
            logger.debug(f"Skipping {child.name}: does not match filter '{name_filter}'")
            continue
        scenarios.append(child)
    return scenarios


def get_prompt_files(scenario_dir: Path) -> list[Path]:
    """Get sorted prompt .md files from a scenario's prompts/ directory."""
    return sorted((scenario_dir / "prompts").glob("*.md"))


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

async def process_prompt(
    prompt_file: Path,
    scenario,
    tutor_config,
    tutor_llm,
) -> PromptResult:
    """Process a single prompt file through a fresh tutor agent instance."""
    from computor_agent.tutor.dev_mode import (
        MessageSimulator,
        MockCourseContent,
        MockSubmissionGroup,
        MockSubmissionGroupMember,
    )
    from computor_agent.tutor.agent import TutorAgent
    from computor_agent.tutor.assignment_loader import AssignmentContext

    prompt_content = prompt_file.read_text(encoding="utf-8").strip()
    if not prompt_content:
        return PromptResult(file=prompt_file.name, success=False, error="Empty prompt file")

    # Fresh simulator and agent per prompt (clean conversation state)
    simulator = MessageSimulator()
    mock_client = SilentMockComputorClient(simulator, scenario=scenario)
    agent = TutorAgent(
        config=tutor_config,
        llm=tutor_llm,
        client=mock_client,
    )

    # Build assignment context from scenario
    assignment_context = AssignmentContext(
        identifier="scenario",
        title=scenario.assignment.title,
        description="",
        language=scenario.assignment.language,
        readme_content=scenario.description or "(No description)",
        files=[],
        slug="scenario",
    )

    # Create mock message
    message = simulator.create_message(content=prompt_content, add_request_tag=True)

    # Build mock course content (mirrors DevelopmentScheduler._process_message)
    sg_member = MockSubmissionGroupMember(full_name=scenario.student.name)
    sg = MockSubmissionGroup(
        id=message.submission_group_id or "scenario_sg",
        members=[sg_member],
    )
    course_content = MockCourseContent(
        submission_group_id=message.submission_group_id,
        unread_message_count=1,
        title=assignment_context.title,
        description=assignment_context.readme_content,
        directory=assignment_context.identifier,
        submission_group=sg,
    )

    start_time = time.perf_counter()
    try:
        result = await agent.process_message(
            submission_group_id=message.submission_group_id,
            message=message.to_dict(),
            repository_path=None,
            reference_path=None,
            send_response=True,
            reply_to_message_id=message.id,
            course_content=course_content,
            course_member_id="scenario_member",
            assignment_context=assignment_context,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        if result.success:
            response_content = ""
            if result.response and result.response.message_content:
                response_content = result.response.message_content
            return PromptResult(
                file=prompt_file.name,
                success=True,
                processing_time_ms=elapsed_ms,
                response_chars=len(response_content),
                blocked=result.blocked_by_security,
                response_content=response_content,
            )
        else:
            return PromptResult(
                file=prompt_file.name,
                success=False,
                processing_time_ms=elapsed_ms,
                error=result.error,
            )

    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(f"Error processing prompt {prompt_file.name}")
        return PromptResult(
            file=prompt_file.name,
            success=False,
            processing_time_ms=elapsed_ms,
            error=str(e),
        )


async def run_scenario(
    scenario_dir: Path,
    output_dir: Path,
    tutor_config,
    tutor_llm,
) -> ScenarioResult:
    """Run all prompts for a single scenario and write output files."""
    from computor_agent.tutor.scenario_loader import load_scenario

    scenario_name = scenario_dir.name
    logger.info(f"Running scenario: {scenario_name}")

    scenario = load_scenario(scenario_dir)

    scenario_output = output_dir / scenario_name
    scenario_output.mkdir(parents=True, exist_ok=True)

    prompt_files = get_prompt_files(scenario_dir)
    logger.info(f"  {len(prompt_files)} prompt(s)")

    scenario_result = ScenarioResult(
        name=scenario_name,
        assignment=scenario.assignment.title,
    )

    scenario_start = time.perf_counter()

    for prompt_file in prompt_files:
        logger.info(f"  Processing: {prompt_file.name}")

        prompt_result = await process_prompt(
            prompt_file=prompt_file,
            scenario=scenario,
            tutor_config=tutor_config,
            tutor_llm=tutor_llm,
        )

        stem = prompt_file.stem
        if prompt_result.success:
            out_file = scenario_output / f"{stem}_response.md"
            out_file.write_text(prompt_result.response_content or "", encoding="utf-8")
            logger.info(
                f"    OK ({prompt_result.processing_time_ms:.0f}ms, "
                f"{prompt_result.response_chars} chars)"
            )
        else:
            out_file = scenario_output / f"{stem}_error.log"
            out_file.write_text(
                f"Error processing prompt: {prompt_file.name}\n"
                f"Time: {datetime.now().isoformat()}\n"
                f"Error: {prompt_result.error}\n",
                encoding="utf-8",
            )
            logger.warning(f"    FAILED: {prompt_result.error}")

        scenario_result.prompts.append(prompt_result)

    scenario_result.total_time_s = time.perf_counter() - scenario_start
    return scenario_result


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def warmup_model(llm_provider) -> None:
    """Send a short throwaway prompt to force model loading before benchmarking.

    Local providers (Ollama, LM Studio) load the model into memory on the first
    request.  Without a warmup the first timed prompt would include that cold-start
    latency, skewing the statistics.
    """
    logger.info("Warming up model (loading into memory)...")
    warmup_start = time.perf_counter()
    await llm_provider.complete("Say OK.")
    warmup_ms = (time.perf_counter() - warmup_start) * 1000
    logger.info(f"Warmup done ({warmup_ms:.0f}ms)")


async def run_model(
    model_name: str,
    llm_settings,
    tutor_config,
    scenario_dirs: list[Path],
    output_base: Path,
    timestamp: str,
) -> RunSummary:
    """Run all scenarios for a single model and return the summary."""
    from computor_agent.settings.config import LLMSettings
    from computor_agent.llm.config import LLMConfig, ProviderType
    from computor_agent.llm.factory import get_provider
    from computor_agent.tutor import TutorLLMAdapter

    model_llm_settings = LLMSettings(
        provider=llm_settings.provider,
        model=model_name,
        base_url=llm_settings.base_url,
        api_key=getattr(llm_settings, "api_key", None),
        temperature=llm_settings.temperature,
    )

    llm_config = LLMConfig(
        provider=ProviderType(model_llm_settings.provider),
        model=model_llm_settings.model,
        base_url=model_llm_settings.base_url,
        api_key=model_llm_settings.get_api_key(),
        temperature=model_llm_settings.temperature,
    )
    llm_provider = get_provider(llm_config)

    try:
        logger.info(f"Checking LLM connectivity ({llm_config.provider.value}/{llm_config.model})...")
        await llm_provider.check_health()
        logger.info(f"LLM ready: {llm_config.provider.value}/{llm_config.model} @ {llm_config.base_url}")
    except Exception as e:
        logger.error(f"Cannot connect to LLM ({model_name}): {e}")
        await llm_provider.close()
        return None

    # Warmup: force model loading so first timed prompt isn't penalized
    try:
        await warmup_model(llm_provider)
    except Exception as e:
        logger.warning(f"Warmup failed for {model_name} (continuing anyway): {e}")

    tutor_llm = TutorLLMAdapter(llm_provider)

    model_slug = model_name.replace(":", "-").replace("/", "-")
    run_dir = output_base / f"run_{timestamp}_{model_slug}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output: {run_dir}")

    summary = RunSummary(
        model=llm_config.model,
        provider=llm_config.provider.value,
        timestamp=timestamp,
    )

    run_start = time.perf_counter()

    for scenario_dir in scenario_dirs:
        scenario_result = await run_scenario(
            scenario_dir=scenario_dir,
            output_dir=run_dir,
            tutor_config=tutor_config,
            tutor_llm=tutor_llm,
        )
        summary.scenarios.append(scenario_result)

    total_time = time.perf_counter() - run_start

    # Compute summary
    all_prompts = [p for s in summary.scenarios for p in s.prompts]
    summary.total_scenarios = len(summary.scenarios)
    summary.total_prompts = len(all_prompts)
    summary.total_successes = sum(1 for p in all_prompts if p.success)
    summary.total_failures = sum(1 for p in all_prompts if not p.success)
    summary.total_time_s = total_time
    if all_prompts:
        summary.avg_processing_time_ms = (
            sum(p.processing_time_ms for p in all_prompts) / len(all_prompts)
        )

    # Write summary.json
    summary_path = run_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Report
    logger.info(f"{'=' * 60}")
    logger.info(
        f"[{model_name}] Run complete: {summary.total_prompts} prompt(s) across "
        f"{summary.total_scenarios} scenario(s)"
    )
    logger.info(f"  Successes: {summary.total_successes}")
    logger.info(f"  Failures:  {summary.total_failures}")
    logger.info(f"  Total time: {summary.total_time_s:.1f}s")
    if all_prompts:
        logger.info(f"  Avg time/prompt: {summary.avg_processing_time_ms:.0f}ms")
    logger.info(f"  Output: {run_dir}")
    logger.info(f"  Summary: {summary_path}")

    await llm_provider.close()
    return summary


async def run_all_scenarios(args: argparse.Namespace) -> None:
    """Initialize config, then run all scenarios for each model sequentially."""
    from computor_agent.settings import ComputorConfig
    from computor_agent.settings.config import BackendConfig, LLMSettings
    from computor_agent.tutor.prompts.loader import get_prompt_loader
    from computor_agent.tutor.dev_mode import _ensure_prompt_files

    scenarios_dir = Path(args.scenarios_dir).resolve()
    if not scenarios_dir.is_dir():
        logger.error(f"Scenarios directory does not exist: {scenarios_dir}")
        sys.exit(1)

    # --- Configuration ---
    config_path = Path(args.config)
    if config_path.exists():
        computor_config = ComputorConfig.from_file(config_path)
    else:
        computor_config = ComputorConfig(
            backend=BackendConfig(url="http://localhost:8000", api_token="unused"),
            llm=LLMSettings(
                provider="ollama",
                model="devstral-small",
                base_url="http://localhost:11434/v1",
            ),
        )
        logger.warning(f"Config file '{args.config}' not found, using defaults")

    tutor_config = computor_config.get_tutor_config()

    if not computor_config.llm:
        logger.error("LLM configuration is required")
        sys.exit(1)

    llm_settings = computor_config.llm

    # --- Build model list ---
    if args.model:
        models = [m.strip() for m in args.model.split(",") if m.strip()]
    else:
        models = [llm_settings.model]

    # --- Prompts ---
    prompts_dir = Path.home() / ".computor" / "prompts"
    _ensure_prompt_files(prompts_dir)
    get_prompt_loader(
        prompts_dir=prompts_dir,
        enable_hot_reload=False,
        force_reload=True,
    )

    # --- Discover scenarios ---
    scenario_dirs = discover_scenarios(scenarios_dir, name_filter=args.scenario)
    if not scenario_dirs:
        logger.error(f"No scenarios found in {scenarios_dir}")
        if args.scenario:
            logger.error(f"  (filter: '{args.scenario}')")
        sys.exit(1)

    logger.info(f"Found {len(scenario_dirs)} scenario(s), {len(models)} model(s)")

    # --- Output base ---
    if args.output:
        output_base = Path(args.output).resolve()
    else:
        output_base = scenarios_dir.parent / "results"

    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

    # --- Run each model: all scenarios, then next model ---
    summaries: list[RunSummary] = []
    for i, model_name in enumerate(models, 1):
        logger.info(f"\n{'#' * 60}")
        logger.info(f"Model {i}/{len(models)}: {model_name}")
        logger.info(f"{'#' * 60}")

        summary = await run_model(
            model_name=model_name,
            llm_settings=llm_settings,
            tutor_config=tutor_config,
            scenario_dirs=scenario_dirs,
            output_base=output_base,
            timestamp=timestamp,
        )
        if summary:
            summaries.append(summary)

    # --- Final report (multi-model) ---
    if len(models) > 1:
        logger.info(f"\n{'=' * 60}")
        logger.info(f"All models complete ({len(summaries)}/{len(models)} succeeded)")
        for s in summaries:
            logger.info(
                f"  {s.model}: {s.total_successes}/{s.total_prompts} OK, "
                f"avg {s.avg_processing_time_ms:.0f}ms, total {s.total_time_s:.1f}s"
            )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Batch-run tutor agent against pre-defined scenarios",
    )
    parser.add_argument(
        "scenarios_dir",
        help="Directory containing scenario subdirectories",
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Config file path (default: config.yaml)",
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        help="Override LLM model(s) from config. Comma-separated for multiple: -m 'mistral:7b,qwen2.5-coder:7b'",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output directory (default: <scenarios_dir>/../results/)",
    )
    parser.add_argument(
        "--scenario", "-s",
        default=None,
        help="Filter: only run scenarios matching this name",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("watchdog").setLevel(logging.WARNING)

    asyncio.run(run_all_scenarios(args))


if __name__ == "__main__":
    main()
