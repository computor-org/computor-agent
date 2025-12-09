"""
Security Gate for the Tutor AI Agent.

Implements two-phase threat detection:
1. Detection: First LLM pass to identify potential threats
2. Confirmation: Second LLM pass to confirm/reject the detection

If both passes agree a threat exists, it's logged and the response is blocked.

Also validates filesystem access requests from LLMs.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Protocol

from computor_agent.tutor.prompts.templates import (
    SECURITY_CONFIRMATION_PROMPT,
    SECURITY_DETECTION_PROMPT,
)
from computor_agent.tutor.security.types import (
    SecurityCheckResult,
    ThreatDetection,
    ThreatLevel,
    ThreatType,
)

if TYPE_CHECKING:
    from computor_agent.tutor.config import SecurityConfig
    from computor_agent.tutor.context import ConversationContext

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Protocol for LLM client used by SecurityGate."""

    async def complete(self, prompt: str, *, max_tokens: int = 1000) -> str:
        """Generate a completion for the given prompt."""
        ...


class SecurityGate:
    """
    Two-phase security gate for detecting malicious content.

    Checks both student messages and repository code for:
    - Prompt injection attempts
    - Credential/secret extraction
    - System prompt extraction
    - Role manipulation
    - Malicious code patterns
    - Data exfiltration
    - Harassment

    Usage:
        gate = SecurityGate(config=config, llm=llm_client)
        result = await gate.check(context)
        if not result.is_safe:
            # Handle blocked content
    """

    def __init__(
        self,
        config: "SecurityConfig",
        llm: LLMClient,
        threat_log_path: Optional[Path] = None,
    ) -> None:
        """
        Initialize the security gate.

        Args:
            config: Security configuration
            llm: LLM client for threat detection
            threat_log_path: Optional path to threat log file (overrides config)
        """
        self.config = config
        self.llm = llm
        self.threat_log_path = threat_log_path or config.threat_log_path

    async def check(self, context: "ConversationContext") -> SecurityCheckResult:
        """
        Perform full security check on the context.

        Checks message and/or code based on configuration.
        Uses two-phase detection if require_confirmation is enabled.

        Args:
            context: The conversation context to check

        Returns:
            SecurityCheckResult with threats and final decision
        """
        if not self.config.enabled:
            return SecurityCheckResult(is_safe=True)

        start_time = time.perf_counter()
        all_threats: list[ThreatDetection] = []

        # Check message content
        if self.config.check_messages and context.trigger_message:
            message_threats = await self._detect_threats(
                content=context.trigger_message.content,
                source="message",
            )
            all_threats.extend(message_threats)

        # Check code content
        if self.config.check_code and context.has_code:
            code_content = context.get_formatted_code()
            code_threats = await self._detect_threats(
                content=code_content,
                source="code",
            )
            all_threats.extend(code_threats)

        # No threats detected
        if not all_threats:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return SecurityCheckResult(
                is_safe=True,
                threats=[],
                was_confirmed=False,
                check_duration_ms=elapsed_ms,
                submission_group_id=context.submission_group_id,
                user_id=context.primary_user_id,
                message_id=context.trigger_message.id if context.trigger_message else None,
            )

        # Run confirmation if configured
        was_confirmed = False
        confirmation_agreed = None

        if self.config.require_confirmation:
            was_confirmed = True
            # Prepare initial detection summary for confirmation
            initial_detection = self._format_detection_for_confirmation(all_threats)

            # Build content for confirmation
            content_parts = []
            if context.trigger_message:
                content_parts.append(f"Message:\n{context.trigger_message.content}")
            if context.has_code:
                content_parts.append(f"Code:\n{context.get_formatted_code(max_lines=500)}")

            content = "\n\n".join(content_parts)

            confirmation_agreed = await self._confirm_threats(
                content=content,
                initial_detection=initial_detection,
            )

        # Determine if safe
        is_safe = True
        if all_threats:
            if self.config.require_confirmation:
                # Only block if confirmation agrees
                is_safe = not confirmation_agreed
            else:
                # Block based on threat level
                result = SecurityCheckResult(
                    is_safe=True,
                    threats=all_threats,
                )
                is_safe = not result.should_block

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        result = SecurityCheckResult(
            is_safe=is_safe,
            threats=all_threats,
            was_confirmed=was_confirmed,
            confirmation_agreed=confirmation_agreed,
            check_duration_ms=elapsed_ms,
            submission_group_id=context.submission_group_id,
            user_id=context.primary_user_id,
            message_id=context.trigger_message.id if context.trigger_message else None,
        )

        # Log threats if detected and confirmed
        if not is_safe:
            await self._log_threat(result, context)

        return result

    async def check_message(self, message: str) -> SecurityCheckResult:
        """
        Check a single message for threats.

        Convenience method for checking just a message without full context.

        Args:
            message: The message content to check

        Returns:
            SecurityCheckResult
        """
        if not self.config.enabled or not self.config.check_messages:
            return SecurityCheckResult(is_safe=True)

        start_time = time.perf_counter()

        threats = await self._detect_threats(content=message, source="message")

        if not threats:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return SecurityCheckResult(
                is_safe=True,
                check_duration_ms=elapsed_ms,
            )

        # Confirm if needed
        was_confirmed = False
        confirmation_agreed = None

        if self.config.require_confirmation and threats:
            was_confirmed = True
            initial_detection = self._format_detection_for_confirmation(threats)
            confirmation_agreed = await self._confirm_threats(
                content=f"Message:\n{message}",
                initial_detection=initial_detection,
            )

        is_safe = True
        if threats:
            if self.config.require_confirmation:
                is_safe = not confirmation_agreed
            else:
                temp_result = SecurityCheckResult(is_safe=True, threats=threats)
                is_safe = not temp_result.should_block

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return SecurityCheckResult(
            is_safe=is_safe,
            threats=threats,
            was_confirmed=was_confirmed,
            confirmation_agreed=confirmation_agreed,
            check_duration_ms=elapsed_ms,
        )

    async def check_code(
        self,
        code: str,
        file_path: Optional[str] = None,
    ) -> SecurityCheckResult:
        """
        Check code content for threats.

        Convenience method for checking just code without full context.

        Args:
            code: The code content to check
            file_path: Optional file path for logging

        Returns:
            SecurityCheckResult
        """
        if not self.config.enabled or not self.config.check_code:
            return SecurityCheckResult(is_safe=True)

        start_time = time.perf_counter()

        threats = await self._detect_threats(
            content=code,
            source="code",
            file_path=file_path,
        )

        if not threats:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return SecurityCheckResult(
                is_safe=True,
                check_duration_ms=elapsed_ms,
            )

        # Confirm if needed
        was_confirmed = False
        confirmation_agreed = None

        if self.config.require_confirmation and threats:
            was_confirmed = True
            initial_detection = self._format_detection_for_confirmation(threats)
            content = f"Code from {file_path or 'unknown'}:\n{code}"
            confirmation_agreed = await self._confirm_threats(
                content=content,
                initial_detection=initial_detection,
            )

        is_safe = True
        if threats:
            if self.config.require_confirmation:
                is_safe = not confirmation_agreed
            else:
                temp_result = SecurityCheckResult(is_safe=True, threats=threats)
                is_safe = not temp_result.should_block

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return SecurityCheckResult(
            is_safe=is_safe,
            threats=threats,
            was_confirmed=was_confirmed,
            confirmation_agreed=confirmation_agreed,
            check_duration_ms=elapsed_ms,
        )

    async def _detect_threats(
        self,
        content: str,
        source: str,
        file_path: Optional[str] = None,
    ) -> list[ThreatDetection]:
        """
        Run first-pass threat detection.

        Args:
            content: Content to analyze
            source: Source type ('message' or 'code')
            file_path: Optional file path if from code

        Returns:
            List of detected threats
        """
        prompt = SECURITY_DETECTION_PROMPT.format(content=content)

        try:
            response = await self.llm.complete(prompt, max_tokens=1000)
            return self._parse_detection_response(response, source, file_path)
        except Exception as e:
            logger.warning(f"Security detection failed: {e}")
            # Fail open - if detection fails, don't block
            return []

    async def _confirm_threats(
        self,
        content: str,
        initial_detection: str,
    ) -> bool:
        """
        Run second-pass threat confirmation.

        Args:
            content: Original content
            initial_detection: Summary of initial detection

        Returns:
            True if confirmation agrees with detection
        """
        prompt = SECURITY_CONFIRMATION_PROMPT.format(
            content=content,
            initial_detection=initial_detection,
        )

        try:
            response = await self.llm.complete(prompt, max_tokens=500)
            return self._parse_confirmation_response(response)
        except Exception as e:
            logger.warning(f"Security confirmation failed: {e}")
            # Fail safe - if confirmation fails, treat as confirmed
            return True

    def _parse_detection_response(
        self,
        response: str,
        source: str,
        file_path: Optional[str],
    ) -> list[ThreatDetection]:
        """Parse the detection LLM response into ThreatDetection objects."""
        threats = []

        try:
            # Extract JSON from response (may have text around it)
            json_str = self._extract_json(response)
            data = json.loads(json_str)

            if not data.get("is_suspicious", False):
                return []

            for threat_data in data.get("threats", []):
                threat_type = self._parse_threat_type(threat_data.get("type", "other"))
                level = self._parse_threat_level(threat_data.get("level", "low"))

                threats.append(
                    ThreatDetection(
                        threat_type=threat_type,
                        level=level,
                        description=threat_data.get("description", "No description"),
                        evidence=threat_data.get("evidence"),
                        source=source,
                        file_path=file_path,
                    )
                )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse detection response: {e}")

        return threats

    def _parse_confirmation_response(self, response: str) -> bool:
        """Parse the confirmation LLM response."""
        try:
            json_str = self._extract_json(response)
            data = json.loads(json_str)
            return data.get("confirmed", False)
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("Failed to parse confirmation response, defaulting to confirmed")
            return True

    def _extract_json(self, text: str) -> str:
        """Extract JSON object from text that may contain other content."""
        # Find the first { and last } to extract JSON
        start = text.find("{")
        end = text.rfind("}") + 1

        if start == -1 or end == 0:
            raise ValueError("No JSON object found in response")

        return text[start:end]

    def _parse_threat_type(self, type_str: str) -> ThreatType:
        """Parse threat type string to enum."""
        type_map = {
            "prompt_injection": ThreatType.PROMPT_INJECTION,
            "credential_extraction": ThreatType.CREDENTIAL_EXTRACTION,
            "system_prompt_extraction": ThreatType.SYSTEM_PROMPT_EXTRACTION,
            "role_manipulation": ThreatType.ROLE_MANIPULATION,
            "malicious_code": ThreatType.MALICIOUS_CODE,
            "data_exfiltration": ThreatType.DATA_EXFILTRATION,
            "obfuscated_payload": ThreatType.OBFUSCATED_PAYLOAD,
            "harassment": ThreatType.HARASSMENT,
            "academic_dishonesty": ThreatType.ACADEMIC_DISHONESTY,
        }
        return type_map.get(type_str.lower(), ThreatType.OTHER)

    def _parse_threat_level(self, level_str: str) -> ThreatLevel:
        """Parse threat level string to enum."""
        level_map = {
            "none": ThreatLevel.NONE,
            "low": ThreatLevel.LOW,
            "medium": ThreatLevel.MEDIUM,
            "high": ThreatLevel.HIGH,
            "critical": ThreatLevel.CRITICAL,
        }
        return level_map.get(level_str.lower(), ThreatLevel.LOW)

    def _format_detection_for_confirmation(
        self,
        threats: list[ThreatDetection],
    ) -> str:
        """Format detected threats for the confirmation prompt."""
        lines = ["Detected threats:"]
        for i, threat in enumerate(threats, 1):
            lines.append(
                f"{i}. {threat.threat_type.value} ({threat.level.value}): "
                f"{threat.description}"
            )
            if threat.evidence:
                lines.append(f"   Evidence: {threat.evidence[:200]}")
        return "\n".join(lines)

    async def _log_threat(
        self,
        result: SecurityCheckResult,
        context: "ConversationContext",
    ) -> None:
        """Log a confirmed threat to the threat log file."""
        if not self.threat_log_path:
            # Just use standard logging
            logger.warning(
                f"Security threat detected: "
                f"user={result.user_id}, "
                f"group={result.submission_group_id}, "
                f"threats={len(result.threats)}"
            )
            return

        # Append to threat log file
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "submission_group_id": result.submission_group_id,
            "user_id": result.user_id,
            "message_id": result.message_id,
            "highest_level": result.highest_threat_level.value,
            "threat_count": len(result.threats),
            "was_confirmed": result.was_confirmed,
            "threats": [
                {
                    "type": t.threat_type.value,
                    "level": t.level.value,
                    "description": t.description,
                    "source": t.source,
                    "evidence": t.evidence[:500] if t.evidence else None,
                }
                for t in result.threats
            ],
        }

        try:
            self.threat_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.threat_log_path, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write to threat log: {e}")

    def check_file_access(self, requested_path: Path, context: "ConversationContext") -> tuple[bool, str]:
        """
        Check if LLM can access a file path.

        Validates that the requested path:
        - Is within repository boundaries
        - Is not a sensitive file (credentials, keys, etc.)
        - Passes all security checks

        Args:
            requested_path: Path the LLM wants to access
            context: Current conversation context

        Returns:
            Tuple of (is_allowed, reason)
        """
        try:
            resolved_path = requested_path.expanduser().resolve()
        except (OSError, RuntimeError) as e:
            return False, f"Invalid path: {e}"

        # Check if path is within student repository
        if context.student_code and context.student_code.repository_path:
            allowed_root = context.student_code.repository_path.resolve()
            try:
                resolved_path.relative_to(allowed_root)
            except ValueError:
                return False, "Path is outside student repository"

        # Check if path is within reference repository (if available)
        elif context.reference_code and context.reference_code.repository_path:
            allowed_root = context.reference_code.repository_path.resolve()
            try:
                resolved_path.relative_to(allowed_root)
            except ValueError:
                return False, "Path is outside reference repository"
        else:
            return False, "No repository context available"

        # Check for sensitive files
        sensitive_patterns = [
            ".env",
            "credentials",
            "secrets",
            ".ssh",
            ".git/config",
            "id_rsa",
            "id_ed25519",
            ".password",
            "token",
            ".key",
            "private",
        ]

        path_lower = str(resolved_path).lower()
        for pattern in sensitive_patterns:
            if pattern in path_lower:
                logger.warning(f"Blocked access to sensitive file: {resolved_path}")
                return False, f"Access denied: file matches sensitive pattern '{pattern}'"

        return True, "Access allowed"

    def validate_search_directory(
        self, directory: Path, context: "ConversationContext"
    ) -> tuple[bool, str]:
        """
        Validate that a search directory is within allowed boundaries.

        Args:
            directory: Directory to search in
            context: Current conversation context

        Returns:
            Tuple of (is_allowed, reason)
        """
        try:
            resolved_dir = directory.expanduser().resolve()
        except (OSError, RuntimeError) as e:
            return False, f"Invalid directory: {e}"

        # Must be within student or reference repository
        allowed_roots = []
        if context.student_code and context.student_code.repository_path:
            allowed_roots.append(context.student_code.repository_path.resolve())
        if context.reference_code and context.reference_code.repository_path:
            allowed_roots.append(context.reference_code.repository_path.resolve())

        if not allowed_roots:
            return False, "No repository context available"

        for allowed_root in allowed_roots:
            try:
                resolved_dir.relative_to(allowed_root)
                return True, "Directory is within allowed repository"
            except ValueError:
                continue

        return False, "Directory is outside allowed repositories"
