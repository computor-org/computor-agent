"""
Figure review service.

Reviews figures (plots/images) from student submissions with a
vision-capable LLM — one call per figure. This is the single shared
implementation used by both the tutor messaging flow and the grading
flow (production and dev modes).
"""

import json
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from computor_agent.llm.base import LLMProvider
from computor_agent.llm.config import ImageContent, Message
from computor_agent.tutor.figures.models import (
    FigureFile,
    FigureReview,
    FigureReviewSummary,
)
from computor_agent.tutor.json_utils import extract_json

if TYPE_CHECKING:
    from computor_agent.settings.config import ComputorConfig
    from computor_agent.tutor.config import FigureReviewConfig, TutorConfig

logger = logging.getLogger(__name__)


class FigureReviewService:
    """
    Reviews submission figures with a vision-capable LLM.

    The service never raises from review calls: a failed vision call
    yields a FigureReview with success=False so the surrounding flow
    (messaging or grading) degrades gracefully.

    Usage:
        service = FigureReviewService(vision_provider, config, owns_provider=True)
        summary = await service.review_all(figures, assignment_section=..., language="en")
        prompt_section = summary.format_for_prompt()
    """

    def __init__(
        self,
        provider: LLMProvider,
        config: "FigureReviewConfig",
        *,
        owns_provider: bool = False,
    ) -> None:
        """
        Initialize the service.

        Args:
            provider: Vision-capable LLM provider (may be the agent's main
                provider when use_agent_llm is configured)
            config: Figure review configuration
            owns_provider: Whether close() should close the provider
                (True only for a dedicated vision provider)
        """
        self.provider = provider
        self.config = config
        self._owns_provider = owns_provider

    def _get_system_prompt(self) -> str:
        """Get the figure review system prompt (loader override or built-in)."""
        try:
            from computor_agent.tutor.prompts.loader import get_figure_review_prompt

            return get_figure_review_prompt()
        except Exception:
            from computor_agent.tutor.prompts.templates import (
                FIGURE_REVIEW_SYSTEM_PROMPT,
            )

            return FIGURE_REVIEW_SYSTEM_PROMPT

    async def review_figure(
        self,
        figure: FigureFile,
        *,
        assignment_section: str = "",
        language: str = "en",
    ) -> FigureReview:
        """
        Review a single figure. Never raises.

        Args:
            figure: The figure to review
            assignment_section: Assignment context text (may be empty)
            language: Response language (ISO 639-1)

        Returns:
            FigureReview (success=False with error text on any failure)
        """
        try:
            system_prompt = self._get_system_prompt().format(
                assignment_section=assignment_section or "(No assignment context available)",
                figure_path=figure.path,
                language=language,
            )
            message = Message.user_with_images(
                f"Review the attached figure '{figure.path}'.",
                [ImageContent(data=figure.data, media_type=figure.media_type)],
            )
            response = await self.provider.complete(
                [message],
                system_prompt=system_prompt,
                max_tokens=self.config.max_response_tokens,
                temperature=self.config.temperature,
            )
            return self._parse_review(figure.path, response.content)
        except Exception as e:
            logger.warning(f"Figure review failed for {figure.path}: {e}")
            return FigureReview(path=figure.path, success=False, error=str(e))

    async def review_all(
        self,
        figures: Sequence[FigureFile],
        *,
        assignment_section: str = "",
        language: str = "en",
    ) -> FigureReviewSummary:
        """
        Review all figures sequentially, one LLM call per figure.

        Figures beyond max_figures or over max_image_bytes are reported
        as skipped (belt-and-braces; collectors already enforce caps).

        Args:
            figures: Figures to review
            assignment_section: Assignment context text (may be empty)
            language: Response language (ISO 639-1)

        Returns:
            FigureReviewSummary with per-figure results
        """
        summary = FigureReviewSummary()

        for figure in figures:
            if figure.size > self.config.max_image_bytes:
                logger.warning(
                    f"Skipping oversized figure {figure.path} "
                    f"({figure.size} > {self.config.max_image_bytes} bytes)"
                )
                summary.skipped.append(figure.path)
                continue
            if len(summary.reviews) >= self.config.max_figures:
                summary.skipped.append(figure.path)
                continue

            logger.info(f"Reviewing figure: {figure.path}")
            summary.reviews.append(
                await self.review_figure(
                    figure,
                    assignment_section=assignment_section,
                    language=language,
                )
            )

        return summary

    def _parse_review(self, path: str, response_text: str) -> FigureReview:
        """Parse the LLM's JSON response, degrading to raw text."""
        try:
            data = json.loads(extract_json(response_text))
        except (ValueError, json.JSONDecodeError):
            # Not JSON — treat the whole response as the assessment
            return FigureReview(
                path=path,
                success=True,
                assessment=response_text.strip(),
            )

        issues = data.get("issues") or []
        if not isinstance(issues, list):
            issues = [str(issues)]

        score = data.get("score")
        if score is not None:
            try:
                score = min(1.0, max(0.0, float(score)))
            except (TypeError, ValueError):
                score = None

        return FigureReview(
            path=path,
            success=True,
            assessment=str(data.get("assessment", "")).strip(),
            issues=[str(i) for i in issues],
            score=score,
        )

    async def close(self) -> None:
        """Close the provider if this service owns it."""
        if self._owns_provider:
            await self.provider.close()


def build_figure_reviewer(
    computor_config: "ComputorConfig",
    tutor_config: "TutorConfig",
    *,
    main_provider: LLMProvider | None,
) -> FigureReviewService | None:
    """
    Build a FigureReviewService from configuration.

    Shared wiring for the production runtime, messaging dev mode, and
    grading dev mode.

    Args:
        computor_config: Root config (provides vision_llm)
        tutor_config: Tutor config (provides figure_review)
        main_provider: The agent's main LLM provider (reused when
            figure_review.use_agent_llm is set)

    Returns:
        FigureReviewService, or None when figure review is disabled

    Raises:
        ValueError: If figure review is enabled but no usable LLM source
            is configured (fail fast at startup)
    """
    fr = tutor_config.figure_review
    if not fr.enabled:
        return None

    if fr.use_agent_llm:
        if main_provider is None:
            raise ValueError(
                "tutor.figure_review.use_agent_llm is set but no main LLM "
                "provider is available"
            )
        return FigureReviewService(main_provider, fr, owns_provider=False)

    if computor_config.vision_llm is None:
        raise ValueError(
            "tutor.figure_review is enabled but no vision_llm is configured; "
            "add a vision_llm section to the config or set "
            "tutor.figure_review.use_agent_llm: true"
        )

    from computor_agent.llm.config import LLMConfig, ProviderType
    from computor_agent.llm.factory import get_provider

    settings = computor_config.vision_llm
    kwargs: dict = {
        "provider": ProviderType(settings.provider),
        "model": settings.model,
        "api_key": settings.get_api_key(),
        "temperature": settings.temperature,
        "busy_retry_delay_seconds": settings.busy_retry_delay_seconds,
    }
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    vision_config = LLMConfig(**kwargs)
    provider = get_provider(vision_config)
    logger.info(
        f"Figure review using dedicated vision LLM "
        f"({settings.provider}/{settings.model})"
    )
    return FigureReviewService(provider, fr, owns_provider=True)
