"""Tests for the figure review package."""

import json

import pytest

from computor_agent.llm import (
    DummyProvider,
    DummyProviderConfig,
    LLMConfig,
    Message,
    ProviderType,
)
from computor_agent.tutor.config import FigureReviewConfig, TutorConfig
from computor_agent.tutor.figures import (
    FigureFile,
    FigureReview,
    FigureReviewService,
    FigureReviewSummary,
    build_figure_reviewer,
    collect_images_from_dir,
    is_image_file,
    media_type_for,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png-data"


def make_dummy_provider(**dummy_kwargs) -> DummyProvider:
    config = LLMConfig(provider=ProviderType.DUMMY)
    dummy_kwargs.setdefault("delay_seconds", 0)
    return DummyProvider(config, DummyProviderConfig(**dummy_kwargs))


def review_json(assessment="Looks good", issues=None, score=0.9) -> str:
    return json.dumps(
        {"assessment": assessment, "issues": issues or [], "score": score}
    )


class TestDetection:
    """Tests for figure detection helpers."""

    def test_is_image_file(self):
        assert is_image_file("plot.png")
        assert is_image_file("dir/sub/figure.JPG")
        assert is_image_file("photo.jpeg")
        assert not is_image_file("script.py")
        assert not is_image_file("data.csv")
        assert not is_image_file("vector.svg")  # not raster, not reviewable

    def test_is_image_file_custom_extensions(self):
        assert is_image_file("plot.png", {".png"})
        assert not is_image_file("photo.jpg", {".png"})

    def test_media_type_for(self):
        assert media_type_for("plot.png") == "image/png"
        assert media_type_for("photo.JPG") == "image/jpeg"
        assert media_type_for("anim.gif") == "image/gif"
        assert media_type_for("unknown.xyz") == "application/octet-stream"

    def test_collect_images_from_dir(self, tmp_path):
        (tmp_path / "plot.png").write_bytes(PNG_BYTES)
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "figure.jpg").write_bytes(b"jpg-data")
        (tmp_path / "script.py").write_text("print('hi')")
        (tmp_path / ".hidden.png").write_bytes(PNG_BYTES)

        figures, skipped = collect_images_from_dir(tmp_path)

        assert [f.path for f in figures] == ["plot.png", "sub/figure.jpg"]
        assert figures[0].data == PNG_BYTES
        assert figures[0].media_type == "image/png"
        assert figures[1].media_type == "image/jpeg"
        assert skipped == []

    def test_collect_images_respects_max_figures(self, tmp_path):
        for i in range(4):
            (tmp_path / f"plot{i}.png").write_bytes(PNG_BYTES)

        figures, skipped = collect_images_from_dir(tmp_path, max_figures=2)

        assert len(figures) == 2
        assert skipped == ["plot2.png", "plot3.png"]

    def test_collect_images_respects_max_bytes(self, tmp_path):
        (tmp_path / "small.png").write_bytes(b"x" * 10)
        (tmp_path / "big.png").write_bytes(b"x" * 1000)

        figures, skipped = collect_images_from_dir(tmp_path, max_image_bytes=100)

        assert [f.path for f in figures] == ["small.png"]
        assert skipped == ["big.png"]

    def test_collect_images_skips_dirs(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "image.png").write_bytes(PNG_BYTES)
        (tmp_path / "plot.png").write_bytes(PNG_BYTES)

        figures, _ = collect_images_from_dir(tmp_path)

        assert [f.path for f in figures] == ["plot.png"]

    def test_collect_images_missing_dir(self, tmp_path):
        figures, skipped = collect_images_from_dir(tmp_path / "nope")
        assert figures == []
        assert skipped == []


class TestFigureReviewSummary:
    """Tests for the prompt formatting of review results."""

    def test_format_for_prompt(self):
        summary = FigureReviewSummary(
            reviews=[
                FigureReview(
                    path="plot.png",
                    success=True,
                    assessment="Good plot",
                    issues=["Missing x-axis unit"],
                    score=0.8,
                ),
                FigureReview(path="broken.png", success=False, error="timeout"),
            ],
            skipped=["huge.png"],
        )

        text = summary.format_for_prompt()

        assert "plot.png" in text
        assert "Good plot" in text
        assert "Missing x-axis unit" in text
        assert "0.80" in text
        assert "(Could not be reviewed: timeout)" in text
        assert "huge.png" in text
        assert summary.reviewed_count == 1

    def test_no_issues_marked_as_none(self):
        summary = FigureReviewSummary(
            reviews=[
                FigureReview(path="ok.png", success=True, assessment="Fine")
            ]
        )
        assert "Issues: none" in summary.format_for_prompt()


class TestFigureReviewService:
    """Tests for FigureReviewService with the dummy provider."""

    @pytest.mark.asyncio
    async def test_review_all_one_call_per_figure(self):
        provider = make_dummy_provider(
            response_queue=[review_json("First"), review_json("Second", ["bad axis"])]
        )
        service = FigureReviewService(provider, FigureReviewConfig(enabled=True))
        figures = [
            FigureFile(path="a.png", data=PNG_BYTES, media_type="image/png"),
            FigureFile(path="b.png", data=b"more", media_type="image/png"),
        ]

        summary = await service.review_all(
            figures, assignment_section="Assignment: plot a sine", language="en"
        )

        assert provider.call_count == 2
        assert summary.reviewed_count == 2
        assert summary.reviews[0].assessment == "First"
        assert summary.reviews[1].issues == ["bad axis"]

        # Each call carried exactly one image and the figure path in the system prompt
        for i, prompt in enumerate(provider.prompt_history):
            assert isinstance(prompt, list)
            assert isinstance(prompt[0], Message)
            assert len(prompt[0].images) == 1
        assert "b.png" in provider.last_kwargs["system_prompt"]
        assert "Assignment: plot a sine" in provider.last_kwargs["system_prompt"]

    @pytest.mark.asyncio
    async def test_malformed_json_degrades_to_raw_text(self):
        provider = make_dummy_provider(response_text="Just plain text feedback")
        service = FigureReviewService(provider, FigureReviewConfig(enabled=True))

        review = await service.review_figure(
            FigureFile(path="a.png", data=PNG_BYTES, media_type="image/png")
        )

        assert review.success is True
        assert review.assessment == "Just plain text feedback"
        assert review.issues == []
        assert review.score is None

    @pytest.mark.asyncio
    async def test_provider_failure_never_raises(self):
        provider = make_dummy_provider(should_fail=True, error_message="vision down")
        service = FigureReviewService(provider, FigureReviewConfig(enabled=True))

        summary = await service.review_all(
            [FigureFile(path="a.png", data=PNG_BYTES, media_type="image/png")]
        )

        assert len(summary.reviews) == 1
        assert summary.reviews[0].success is False
        assert "vision down" in summary.reviews[0].error
        # The summary still formats without raising
        assert "Could not be reviewed" in summary.format_for_prompt()

    @pytest.mark.asyncio
    async def test_caps_enforced(self):
        provider = make_dummy_provider(response_text=review_json())
        config = FigureReviewConfig(enabled=True, max_figures=1, max_image_bytes=1024)
        service = FigureReviewService(provider, config)
        figures = [
            FigureFile(path="big.png", data=b"x" * 2048, media_type="image/png"),
            FigureFile(path="a.png", data=b"ok", media_type="image/png"),
            FigureFile(path="b.png", data=b"ok", media_type="image/png"),
        ]

        summary = await service.review_all(figures)

        assert provider.call_count == 1
        assert [r.path for r in summary.reviews] == ["a.png"]
        assert summary.skipped == ["big.png", "b.png"]

    @pytest.mark.asyncio
    async def test_score_clamped(self):
        provider = make_dummy_provider(response_text=review_json(score=1.7))
        service = FigureReviewService(provider, FigureReviewConfig(enabled=True))

        review = await service.review_figure(
            FigureFile(path="a.png", data=PNG_BYTES, media_type="image/png")
        )

        assert review.score == 1.0

    @pytest.mark.asyncio
    async def test_close_respects_ownership(self):
        provider = make_dummy_provider()
        shared = FigureReviewService(
            provider, FigureReviewConfig(enabled=True), owns_provider=False
        )
        await shared.close()  # must not close the shared provider

        owned = FigureReviewService(
            provider, FigureReviewConfig(enabled=True), owns_provider=True
        )
        await owned.close()


class TestBuildFigureReviewer:
    """Tests for the shared wiring helper."""

    def _computor_config(self, vision_llm=None):
        from computor_agent.settings.config import ComputorConfig

        data = {
            "backend": {
                "url": "https://api.example.com",
                "username": "u",
                "password": "p",
            },
        }
        if vision_llm:
            data["vision_llm"] = vision_llm
        return ComputorConfig.from_dict(data)

    def test_disabled_returns_none(self):
        config = self._computor_config()
        tutor_config = TutorConfig()

        assert (
            build_figure_reviewer(config, tutor_config, main_provider=None) is None
        )

    def test_use_agent_llm_shares_provider(self):
        config = self._computor_config()
        tutor_config = TutorConfig.from_dict(
            {"figure_review": {"enabled": True, "use_agent_llm": True}}
        )
        main_provider = make_dummy_provider()

        service = build_figure_reviewer(
            config, tutor_config, main_provider=main_provider
        )

        assert service.provider is main_provider
        assert service._owns_provider is False

    def test_dedicated_vision_provider(self):
        config = self._computor_config(
            vision_llm={"provider": "dummy", "model": "vision-model"}
        )
        tutor_config = TutorConfig.from_dict({"figure_review": {"enabled": True}})
        main_provider = make_dummy_provider()

        service = build_figure_reviewer(
            config, tutor_config, main_provider=main_provider
        )

        assert service.provider is not main_provider
        assert service.provider.model_name == "vision-model"
        assert service._owns_provider is True

    def test_enabled_without_source_fails_fast(self):
        config = self._computor_config()
        tutor_config = TutorConfig.from_dict({"figure_review": {"enabled": True}})

        with pytest.raises(ValueError, match="vision_llm"):
            build_figure_reviewer(
                config, tutor_config, main_provider=make_dummy_provider()
            )

    def test_use_agent_llm_without_provider_fails(self):
        config = self._computor_config()
        tutor_config = TutorConfig.from_dict(
            {"figure_review": {"enabled": True, "use_agent_llm": True}}
        )

        with pytest.raises(ValueError, match="main LLM"):
            build_figure_reviewer(config, tutor_config, main_provider=None)


class TestZipImageExtraction:
    """Tests for image collection in ArtifactsService._extract_zip."""

    def _make_zip(self, entries: dict[str, bytes]) -> bytes:
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, data in entries.items():
                zf.writestr(name, data)
        return buf.getvalue()

    def _artifact_meta(self):
        from datetime import datetime

        from computor_types.artifacts import SubmissionArtifactGet

        return SubmissionArtifactGet(
            id="test",
            submission_group_id="group",
            file_size=0,
            bucket_name="bucket",
            object_key="key",
            uploaded_at=datetime.now(),
        )

    def _service(self):
        from computor_agent.tutor.services.artifacts import ArtifactsService

        return ArtifactsService(client=None)

    def test_images_stay_binary_by_default(self):
        """Without collect_images, behavior is unchanged (regression)."""
        buffer = self._make_zip({"main.py": b"print('hi')", "plot.png": PNG_BYTES})

        content = self._service()._extract_zip(buffer, self._artifact_meta())

        assert list(content.files) == ["main.py"]
        assert content.binary_files == ["plot.png"]
        assert content.image_files == []

    def test_collect_images(self):
        buffer = self._make_zip(
            {"main.py": b"print('hi')", "plot.png": PNG_BYTES, "data.bin": b"\x00\x01"}
        )

        content = self._service()._extract_zip(
            buffer, self._artifact_meta(), collect_images=True
        )

        assert list(content.files) == ["main.py"]
        assert content.binary_files == ["data.bin"]
        assert [f.path for f in content.image_files] == ["plot.png"]
        assert content.image_files[0].data == PNG_BYTES
        assert content.image_files[0].media_type == "image/png"
        assert content.total_files == 3
        assert "Figures (reviewed separately): plot.png" in content.format_for_prompt()

    def test_collect_images_caps(self):
        buffer = self._make_zip(
            {
                "big.png": b"x" * 2048,
                "plot1.png": PNG_BYTES,
                "plot2.png": PNG_BYTES,
            }
        )

        content = self._service()._extract_zip(
            buffer,
            self._artifact_meta(),
            collect_images=True,
            max_figures=1,
            max_image_bytes=1024,
        )

        assert [f.path for f in content.image_files] == ["plot1.png"]
        # Oversized and over-count images fall back to the binary list
        assert set(content.binary_files) == {"big.png", "plot2.png"}


class TestScenarioLoaderImages:
    """Tests for figure loading in the dev-mode scenario loader."""

    def _make_scenario(self, tmp_path):
        (tmp_path / "scenario.yaml").write_text(
            "student:\n  name: Test\nassignment:\n  title: Plots\n"
        )
        sub_dir = tmp_path / "submission"
        sub_dir.mkdir()
        (sub_dir / "main.py").write_text("print('hi')")
        (sub_dir / "plot.png").write_bytes(PNG_BYTES)
        return tmp_path

    def test_scenario_collects_images(self, tmp_path):
        from computor_agent.tutor.scenario_loader import load_scenario

        scenario = load_scenario(self._make_scenario(tmp_path))

        assert list(scenario.submission_files) == ["main.py"]
        assert [f.path for f in scenario.submission_images] == ["plot.png"]
        assert scenario.submission_images[0].data == PNG_BYTES

    @pytest.mark.asyncio
    async def test_mock_endpoint_zips_images(self, tmp_path):
        import io
        import zipfile

        from computor_agent.tutor.dev_mode import MockSubmissionsEndpoint
        from computor_agent.tutor.scenario_loader import load_scenario

        scenario = load_scenario(self._make_scenario(tmp_path))
        endpoint = MockSubmissionsEndpoint(scenario=scenario)

        buffer = await endpoint.artifacts_download()

        with zipfile.ZipFile(io.BytesIO(buffer)) as zf:
            assert set(zf.namelist()) == {"main.py", "plot.png"}
            assert zf.read("plot.png") == PNG_BYTES


class TestGradingSubmissionImages:
    """Tests for figure loading in the grading dev-mode loader."""

    def test_load_student_submission_scans_images(self, tmp_path):
        from computor_agent.tutor.assignment_loader import AssignmentFile
        from computor_agent.tutor.grading.dev_mode import load_student_submission

        (tmp_path / "main.py").write_text("print('hi')")
        (tmp_path / "output.png").write_bytes(PNG_BYTES)
        reference = [
            AssignmentFile(path="main.py", content="ref", is_submission_file=True)
        ]

        # Disabled (default): no images collected
        submission = load_student_submission(tmp_path, reference)
        assert submission.images == []

        # Enabled: images scanned independently of the reference file list
        config = FigureReviewConfig(enabled=True)
        submission = load_student_submission(tmp_path, reference, figure_config=config)
        assert [f.path for f in submission.images] == ["output.png"]
        assert [f.path for f in submission.files] == ["main.py"]


class TestAgentFigureReviewFlow:
    """End-to-end messaging flow with figure review (dev-mode mocks)."""

    def _make_scenario_dir(self, tmp_path):
        (tmp_path / "scenario.yaml").write_text(
            "student:\n  name: Test\nassignment:\n  title: Plots\n"
        )
        sub_dir = tmp_path / "submission"
        sub_dir.mkdir()
        (sub_dir / "main.py").write_text("import matplotlib\n")
        (sub_dir / "plot.png").write_bytes(PNG_BYTES)
        return tmp_path

    def _make_agent(self, tmp_path, figure_review_config, vision_provider):
        from computor_agent.tutor import TutorAgent, TutorLLMAdapter
        from computor_agent.tutor.dev_mode import MessageSimulator, MockComputorClient
        from computor_agent.tutor.scenario_loader import load_scenario

        scenario = load_scenario(self._make_scenario_dir(tmp_path))
        tutor_config = TutorConfig.from_dict(
            {
                "security": {"enabled": False},
                "figure_review": figure_review_config,
            }
        )
        main_provider = make_dummy_provider(response_text="Tutor reply about the plot")
        reviewer = None
        if vision_provider is not None:
            reviewer = FigureReviewService(
                vision_provider, tutor_config.figure_review, owns_provider=True
            )

        simulator = MessageSimulator()
        client = MockComputorClient(simulator, scenario=scenario)
        agent = TutorAgent(
            config=tutor_config,
            llm=TutorLLMAdapter(main_provider),
            client=client,
            figure_reviewer=reviewer,
        )
        return agent, simulator, main_provider

    @pytest.mark.asyncio
    async def test_figure_review_injected_into_system_prompt(self, tmp_path):
        vision_provider = make_dummy_provider(
            response_queue=[review_json("Nice plot", ["missing legend"], 0.7)]
        )
        agent, simulator, main_provider = self._make_agent(
            tmp_path, {"enabled": True, "use_agent_llm": True}, vision_provider
        )

        message = simulator.create_message(content="How is my plot?", mention_agent=True)
        result = await agent.process_message(
            submission_group_id="dev-group",
            message=message.to_dict(),
            send_response=False,
        )

        assert result.success
        # One vision call for the one figure in the submission ZIP
        assert vision_provider.call_count == 1
        system_prompt = main_provider.last_kwargs["system_prompt"]
        assert "Figure Review:" in system_prompt
        assert "missing legend" in system_prompt

    @pytest.mark.asyncio
    async def test_disabled_figure_review_makes_no_vision_calls(self, tmp_path):
        vision_provider = make_dummy_provider()
        agent, simulator, main_provider = self._make_agent(
            tmp_path, {"enabled": False}, vision_provider
        )

        message = simulator.create_message(content="Help me", mention_agent=True)
        result = await agent.process_message(
            submission_group_id="dev-group",
            message=message.to_dict(),
            send_response=False,
        )

        assert result.success
        assert vision_provider.call_count == 0
        assert "Figure Review:" not in main_provider.last_kwargs["system_prompt"]

    @pytest.mark.asyncio
    async def test_vision_failure_does_not_break_messaging(self, tmp_path):
        vision_provider = make_dummy_provider(
            should_fail=True, error_message="vision offline"
        )
        agent, simulator, main_provider = self._make_agent(
            tmp_path, {"enabled": True, "use_agent_llm": True}, vision_provider
        )

        message = simulator.create_message(content="How is my plot?", mention_agent=True)
        result = await agent.process_message(
            submission_group_id="dev-group",
            message=message.to_dict(),
            send_response=False,
        )

        assert result.success
        # The failed review is still reported to the main LLM
        system_prompt = main_provider.last_kwargs["system_prompt"]
        assert "Could not be reviewed" in system_prompt


class TestFigureReviewPrompt:
    """Tests for the figure review prompt template."""

    def test_template_formats(self):
        from computor_agent.tutor.prompts.templates import FIGURE_REVIEW_SYSTEM_PROMPT

        text = FIGURE_REVIEW_SYSTEM_PROMPT.format(
            assignment_section="Assignment:\n---\nPlot a sine\n---",
            figure_path="plots/sine.png",
            language="de",
        )
        assert "plots/sine.png" in text
        assert "Plot a sine" in text
        assert "de" in text
        # JSON example survives formatting (escaped braces)
        assert '"assessment"' in text
