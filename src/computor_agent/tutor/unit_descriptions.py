"""Unit description drafts for lecturers (computor-org/issues#559).

A lecturer asks for a draft of a unit's description; the backend queues a job
with the unit's title and the student-visible text of its assignments. This
worker claims jobs as the tutor agent, writes one Markdown draft per requested
language and posts them back. The lecturer reviews and saves the draft; nothing
here writes to the course.

No prompt, assignment text or draft is logged: only job ids, counts and
outcome codes.
"""

import asyncio
import logging
import re
from typing import Any, Optional
from uuid import UUID

from computor_agent.llm.base import LLMProvider
from computor_agent.tutor.config import UnitDescriptionConfig
from computor_agent.tutor.prompts.loader import get_unit_description_prompt

logger = logging.getLogger(__name__)

CLAIM_PATH = "/course-contents/description-drafts/worker/claim"
COMPLETE_PATH = "/course-contents/description-drafts/worker/complete/{job_id}"

# The backend's unit description column is String(4096).
MAX_DESCRIPTION_CHARS = 4096
# Ask the model for less than the hard limit so a slightly long answer fits.
TARGET_DESCRIPTION_CHARS = 3000

# A backend without this feature, or a token that is not the tutor agent's:
# check again much later instead of every few seconds.
UNSUPPORTED_BACKOFF_SECONDS = 600.0
ERROR_BACKOFF_SECONDS = 15.0

LANGUAGE_NAMES = {
    "de": "German",
    "en": "English",
    "fr": "French",
    "it": "Italian",
    "es": "Spanish",
}

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^```(?:markdown|md)?[ \t]*\n(?P<body>.*?)\n```$", re.DOTALL)


class DraftFailed(Exception):
    """A draft could not be written; ``code`` is the backend error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)


def build_user_message(request: dict[str, Any], language: str) -> str:
    """The job input as one user message for the model."""
    parts = []
    if request.get("course_title"):
        parts.append(f"Course: {request['course_title']}")
    parts.append(f"Unit: {request['unit_title']}")
    current = (request.get("unit_description") or "").strip()
    parts.append(
        "Current unit description (may be outdated):\n" + current
        if current
        else "Current unit description: none"
    )
    parts.append(f"Write the description in: {language_name(language)}")
    instruction = (request.get("instruction") or "").strip()
    parts.append(f"Lecturer's extra instruction: {instruction}" if instruction else "Lecturer's extra instruction: none")

    assignments = request.get("assignments") or []
    lines = [f"Assignments in this unit, in course order ({len(assignments)}):"]
    for index, assignment in enumerate(assignments, start=1):
        heading = f"### {index}. {assignment.get('title') or 'Untitled'}"
        if assignment.get("content_type"):
            heading += f" ({assignment['content_type']})"
        lines.append(heading)
        text = (assignment.get("text") or "").strip()
        lines.append(text if text else "(no assignment text available)")
    parts.append("\n\n".join(lines))
    return "\n\n".join(parts)


def clean_draft(content: Optional[str]) -> str:
    """The model's answer without reasoning blocks or a wrapping code fence."""
    if not isinstance(content, str):
        return ""
    content = _THINK_BLOCK.sub("", content)
    if "</think>" in content:
        content = content.rsplit("</think>", 1)[1]
    if "<think>" in content:
        content = content.split("<think>", 1)[0]
    content = content.strip()
    fenced = _FENCE.match(content)
    if fenced:
        content = fenced.group("body").strip()
    return content


class UnitDescriptionWriter:
    """Writes the drafts for one claimed job."""

    def __init__(self, llm: LLMProvider, config: UnitDescriptionConfig):
        self.llm = llm
        self.config = config

    async def _complete(
        self, system_prompt: str, message: str, max_tokens: Optional[int] = None
    ) -> str:
        max_tokens = max_tokens or self.config.max_response_tokens
        try:
            response = await self.llm.complete(
                message,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=self.config.temperature,
            )
        except Exception as e:
            # Exception text can echo request content; log its type only.
            logger.warning(f"Unit description draft: model call failed ({type(e).__name__})")
            raise DraftFailed("model_error") from None
        if response.finish_reason == "length":
            draft = clean_draft(response.content)
            if len(draft) > MAX_DESCRIPTION_CHARS:
                # Really too long: write() asks for a shorter one.
                return draft
            # A reasoning model can spend the budget before it answers; that
            # is not a long draft. One retry with twice the budget.
            if max_tokens > self.config.max_response_tokens:
                raise DraftFailed("model_error")
            return await self._complete(system_prompt, message, max_tokens * 2)
        if response.finish_reason not in (None, "stop"):
            raise DraftFailed("invalid_output")
        return clean_draft(response.content)

    async def write(self, request: dict[str, Any], language: str) -> str:
        # Plain replacement, not str.format: an operator's override may hold
        # other braces (a JSON example) or leave the placeholders out.
        system_prompt = (
            get_unit_description_prompt()
            .replace("{language_name}", language_name(language))
            .replace("{max_chars}", str(TARGET_DESCRIPTION_CHARS))
        )
        message = build_user_message(request, language)
        draft = await self._complete(system_prompt, message)
        if len(draft) > MAX_DESCRIPTION_CHARS:
            # One retry, asking for a shorter text. Never cut it off: a
            # truncated description would end mid-sentence or mid-list.
            draft = await self._complete(
                system_prompt,
                message
                + f"\n\nYour previous answer was {len(draft)} characters long. "
                f"Write a shorter description of at most {TARGET_DESCRIPTION_CHARS} characters.",
            )
            if len(draft) > MAX_DESCRIPTION_CHARS:
                raise DraftFailed("too_long")
        if not draft:
            raise DraftFailed("invalid_output")
        return draft

    async def _drafts(self, request: dict[str, Any]) -> list[dict[str, str]]:
        return [
            {"language": language, "description": await self.write(request, language)}
            for language in request["languages"]
        ]

    async def completion(self, claim: dict[str, Any]) -> dict[str, Any]:
        """The completion body for a claimed job."""
        try:
            # The whole job ends before the backend's lease does; otherwise
            # the backend hands it out again and it is written twice.
            drafts = await asyncio.wait_for(
                self._drafts(claim["request"]), timeout=self.config.job_timeout_seconds
            )
        except DraftFailed as failure:
            return {"lease": claim["lease"], "state": "failed", "error": failure.code}
        except asyncio.TimeoutError:
            logger.warning(
                f"Unit description draft: no result within {self.config.job_timeout_seconds:.0f}s"
            )
            return {"lease": claim["lease"], "state": "failed", "error": "model_error"}
        return {"lease": claim["lease"], "state": "done", "drafts": drafts}


def _status_code(error: Exception) -> Optional[int]:
    return getattr(error, "status_code", None)


class UnitDescriptionWorker:
    """Claims description draft jobs from the backend until stopped."""

    def __init__(self, client, llm: LLMProvider, config: UnitDescriptionConfig):
        self.client = client
        self.writer = UnitDescriptionWriter(llm, config)
        self.config = config
        self._unsupported_logged = False

    async def poll_once(self) -> float:
        """Claim and finish at most one job; returns seconds to wait next."""
        try:
            claim = await self.client.post(CLAIM_PATH)
        except Exception as e:
            status = _status_code(e)
            if status in (403, 404, 405):
                if not self._unsupported_logged:
                    logger.info(
                        "Unit description drafts unavailable on this backend "
                        f"(HTTP {status}); checking again in {UNSUPPORTED_BACKOFF_SECONDS:.0f}s"
                    )
                    self._unsupported_logged = True
                return UNSUPPORTED_BACKOFF_SECONDS
            logger.warning(f"Unit description claim failed ({type(e).__name__})")
            return ERROR_BACKOFF_SECONDS
        self._unsupported_logged = False

        if not isinstance(claim, dict) or claim.get("state") != "claimed":
            return self.config.poll_interval_seconds
        # The id goes into a URL: only a well-formed UUID.
        try:
            job_id = str(UUID(str(claim.get("id"))))
        except ValueError:
            logger.warning("Unit description claim with an invalid job id; skipped")
            return ERROR_BACKOFF_SECONDS
        request = claim.get("request") or {}
        logger.info(
            f"Unit description draft {job_id}: {len(request.get('assignments') or [])} assignments, "
            f"languages {request.get('languages')}"
        )
        body = await self.writer.completion(claim)
        try:
            await self.client.post(COMPLETE_PATH.format(job_id=job_id), json_data=body)
        except Exception as e:
            status = _status_code(e)
            if status == 409:
                # The lecturer cancelled, or the lease ran out: nothing to do.
                logger.info(f"Unit description draft {job_id}: dropped, the job is gone")
                return 0.0
            if status in (400, 422) and body["state"] == "done":
                # The backend refused the drafts. Fail the job so the lecturer
                # is not left waiting until the lease runs out.
                return await self._fail(job_id, body["lease"], status)
            # The lease expires and the backend hands the job out again.
            logger.warning(f"Unit description draft {job_id}: completion failed ({type(e).__name__})")
            return ERROR_BACKOFF_SECONDS
        logger.info(f"Unit description draft {job_id}: {body['state']}{' ' + body['error'] if body.get('error') else ''}")
        # A job was waiting; there may be another.
        return 0.0

    async def _fail(self, job_id: str, lease: str, status: int) -> float:
        body = {"lease": lease, "state": "failed", "error": "invalid_output"}
        try:
            await self.client.post(COMPLETE_PATH.format(job_id=job_id), json_data=body)
        except Exception as e:
            logger.warning(
                f"Unit description draft {job_id}: failing the job failed ({type(e).__name__})"
            )
            return ERROR_BACKOFF_SECONDS
        logger.info(
            f"Unit description draft {job_id}: drafts refused (HTTP {status}), job failed"
        )
        return 0.0

    async def run(self, stop: asyncio.Event) -> None:
        logger.info("Unit description drafts enabled")
        while not stop.is_set():
            try:
                delay = await self.poll_once()
            except Exception as e:  # never let a bad job end the agent
                logger.warning(f"Unit description worker error ({type(e).__name__})")
                delay = ERROR_BACKOFF_SECONDS
            if delay:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
