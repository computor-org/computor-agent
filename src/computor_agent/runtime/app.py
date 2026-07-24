"""Runtime orchestration for the tutor messaging agent.

Owns the lifecycle of a messaging run — LLM provider, optional dashboard,
backend client, WebSocket scheduler, signal handling, and teardown — so the
CLI command only parses options and delegates here.
"""

import asyncio
import logging
import signal
from typing import Optional

from rich.console import Console

from computor_agent.runtime.auth import get_ws_token, make_token_provider
from computor_agent.runtime.options import RuntimeOptions

logger = logging.getLogger(__name__)


class LateBoundSchedulerStats:
    """Lets the dashboard start before the scheduler exists.

    The dashboard captures one stats source at construction time. When that
    source is None, routes still need to render — so this holder returns a
    "scheduler not yet running" snapshot until ``target`` is attached.
    """

    def __init__(self) -> None:
        self.target = None

    def get_stats(self) -> dict:
        target = self.target
        if target is None:
            return {
                "running": False,
                "connected": False,
                "courses": 0,
                "tracked_groups": 0,
                "active_typing": 0,
            }
        return target.get_stats()


class AgentRuntime:
    """Runs the tutor messaging agent to completion.

    Usage:
        runtime = AgentRuntime(computor_config, RuntimeOptions(dry_run=True))
        exit_code = await runtime.run()

    run() returns a process exit code: 0 after a clean shutdown (signal),
    nonzero when the scheduler died on an unrecoverable error — so a
    container restart policy can relaunch the agent.
    """

    def __init__(
        self,
        config,
        options: Optional[RuntimeOptions] = None,
        console: Optional[Console] = None,
    ) -> None:
        self.config = config
        self.options = options or RuntimeOptions()
        self.console = console or Console()
        self.tutor_config = config.get_tutor_config()

        self.metrics = None
        self.llm_config = None
        self.llm_provider = None
        self.figure_reviewer = None
        self.scheduler_stats = LateBoundSchedulerStats()
        self._api_server = None
        self._api_task = None
        self._run_state = {"exit_code": 0}

    async def run(self) -> int:
        """Run the agent until shutdown; returns the process exit code."""
        from computor_client import ComputorClient

        from computor_agent.tutor import TutorLLMAdapter

        self._setup_prompts()

        if not self._build_llm():
            return 1
        if not self._build_vision_llm():
            return 1
        self._start_dashboard()
        await self._check_llm_health()
        await self._check_vision_llm_health()

        tutor_llm = TutorLLMAdapter(self.llm_provider)

        # Create Computor client with appropriate authentication
        client_kwargs = {"base_url": self.config.backend.url}
        if self.config.backend.auth_method == "api_token":
            # Use X-API-Token header for API token auth
            client_kwargs["headers"] = {
                "X-API-Token": self.config.backend.get_api_token()
            }
            logger.info("Using API token authentication")

        async with ComputorClient(**client_kwargs) as client:
            if not await self._login(client):
                return 1

            await self._resolve_agent_user_id(client)

            scheduler = await self._build_scheduler(client, tutor_llm)
            if scheduler is None:
                return 1

            # The dashboard (if started above) was holding a placeholder until
            # the scheduler existed. Wire the real one in now so /metrics, /,
            # and /health start showing live numbers.
            self.scheduler_stats.target = scheduler

            await self._run_until_shutdown(scheduler)

        await tutor_llm.close()
        if self.figure_reviewer:
            await self.figure_reviewer.close()
        if self._run_state["exit_code"]:
            self.console.print(
                "[bold red]Tutor agent stopped after an unrecoverable error.[/bold red]"
            )
        else:
            self.console.print("[green]Tutor agent stopped.[/green]")
        return self._run_state["exit_code"]

    def _setup_prompts(self) -> None:
        """Initialize the prompt loader if a prompts directory was given."""
        from computor_agent.tutor.prompts.loader import get_prompt_loader

        prompts_dir = self.options.prompts_dir
        if prompts_dir is None:
            # No prompts directory specified - will use hardcoded templates
            logger.info("Using built-in prompt templates")
            return

        prompts_dir = prompts_dir.expanduser().resolve()

        # Auto-initialize missing files when directory is explicitly specified
        from computor_agent.tutor.dev_mode import _ensure_prompt_files

        _ensure_prompt_files(prompts_dir)

        logger.info(f"Loading prompts from: {prompts_dir}")
        get_prompt_loader(
            prompts_dir=prompts_dir,
            enable_hot_reload=False,  # No hot reload in production
            force_reload=True,
        )

    def _build_llm(self) -> bool:
        """Create the LLM provider and shared metrics. False if unconfigured."""
        from computor_agent.api.metrics import MetricsCollector
        from computor_agent.llm.config import LLMConfig, ProviderType
        from computor_agent.llm.factory import get_provider

        if not self.config.llm:
            logger.error("LLM configuration is missing from config")
            self.console.print("[bold red]Error:[/bold red] LLM configuration is required")
            return False

        self.llm_config = LLMConfig(
            provider=ProviderType(self.config.llm.provider),
            model=self.config.llm.model,
            base_url=self.config.llm.base_url,
            api_key=self.config.llm.get_api_key(),
            temperature=self.config.llm.temperature,
            busy_retry_delay_seconds=self.config.llm.busy_retry_delay_seconds,
        )
        self.llm_provider = get_provider(self.llm_config)

        self.metrics = MetricsCollector()
        self.metrics.llm_metadata(
            provider=self.llm_config.provider.value,
            model=self.llm_config.model,
            base_url=self.llm_config.base_url,
        )
        return True

    def _build_vision_llm(self) -> bool:
        """Create the figure review service (vision LLM). False on misconfig.

        Fails fast when figure review is enabled without a usable LLM
        source (no vision_llm section and use_agent_llm not set).
        """
        from computor_agent.tutor.figures.service import build_figure_reviewer

        try:
            self.figure_reviewer = build_figure_reviewer(
                self.config,
                self.tutor_config,
                main_provider=self.llm_provider,
            )
        except ValueError as e:
            logger.error(f"Figure review configuration error: {e}")
            self.console.print(f"[bold red]Error:[/bold red] {e}")
            return False

        if self.figure_reviewer:
            fr = self.tutor_config.figure_review
            source = (
                "main agent LLM"
                if fr.use_agent_llm
                else f"{self.config.vision_llm.provider}/{self.config.vision_llm.model}"
            )
            logger.info(f"Figure review enabled (vision model: {source})")
        return True

    async def _check_vision_llm_health(self) -> None:
        """Soft-probe a dedicated vision provider.

        Non-fatal like _check_llm_health: figure review degrades
        gracefully per figure at runtime, and a text probe cannot verify
        vision capability anyway (that responsibility is the user's).
        Skipped when the main provider is reused (already probed).
        """
        if not self.figure_reviewer or self.tutor_config.figure_review.use_agent_llm:
            return

        settings = self.config.vision_llm
        self.console.print(
            f"[dim]Checking vision LLM connectivity ({settings.provider}/{settings.model})...[/dim]"
        )
        try:
            await self.figure_reviewer.provider.check_health()
            logger.info(f"Vision LLM health check passed ({settings.provider}/{settings.model})")
            self.console.print("[green]Vision LLM is ready.[/green]")
        except Exception as e:
            logger.warning(
                f"Vision LLM health check failed ({settings.provider}/{settings.model}): {e} "
                "— continuing; figure review will report per-figure errors",
                exc_info=True,
            )
            self.console.print(
                f"[yellow]Warning:[/yellow] vision LLM health check failed: {e}"
            )

    def _start_dashboard(self) -> None:
        """Bring up the optional dashboard *before* any blocking I/O.

        That way --api-port is reachable immediately and the dashboard is the
        place users go to see why the LLM or backend isn't ready, rather than
        the dashboard being held hostage to the very thing they want to debug.
        """
        if not self.options.api_port:
            return

        try:
            from computor_agent.api.log_buffer import get_log_buffer
            from computor_agent.api.server import APIServer, create_app

            app = create_app(
                metrics=self.metrics,
                scheduler=self.scheduler_stats,
                log_buffer=get_log_buffer(),
                log_file=self.options.log_file,
            )
            self._api_server = APIServer(
                app, host=self.options.api_host, port=self.options.api_port
            )
            self._api_task = asyncio.create_task(self._api_server.serve())
        except ImportError as e:
            logger.warning(
                f"Dashboard API requested but the 'api' extra is not installed "
                f"({e}); install it with: pip install -e \".[api]\""
            )
        except Exception as e:
            logger.warning(f"Failed to start dashboard API: {e}")

    async def _check_llm_health(self) -> None:
        """Verify the LLM model is reachable.

        Non-fatal: the periodic LLM probe and the dashboard already track
        availability, and we'd rather have the agent idle-but-running
        (dashboard up) than dead so users can diagnose.
        """
        llm = self.llm_config
        logger.info(
            f"Checking LLM connectivity ({llm.provider.value}/{llm.model}) "
            f"at {llm.base_url}"
        )
        self.console.print(
            f"[dim]Checking LLM connectivity ({llm.provider.value}/{llm.model})...[/dim]"
        )
        try:
            await self.llm_provider.check_health()
            logger.info(f"LLM health check passed ({llm.provider.value}/{llm.model})")
            self.console.print("[green]LLM is ready.[/green]")
            self.metrics.llm_probed(ok=True, latency_ms=0)
        except Exception as e:
            logger.warning(
                f"LLM health check failed ({llm.provider.value}/{llm.model} "
                f"at {llm.base_url}): {e} — continuing; periodic probe will retry",
                exc_info=True,
            )
            self.console.print(f"[yellow]Warning:[/yellow] LLM health check failed: {e}")
            self.console.print(
                "[dim]Continuing anyway — the periodic probe will retry and "
                "the dashboard reports state.[/dim]"
            )
            self.metrics.llm_probed(ok=False, latency_ms=0, error=str(e))

    async def _login(self, client) -> bool:
        """Authenticate with username/password if not using an API token."""
        if self.config.backend.auth_method == "api_token":
            return True
        try:
            await client.login(
                username=self.config.backend.username,
                password=self.config.backend.get_password(),
            )
            logger.info("Authenticated with username/password")
            return True
        except Exception as e:
            logger.error(f"Authentication failed: {e}", exc_info=True)
            self.console.print(f"[bold red]Authentication failed:[/bold red] {e}")
            return False

    async def _resolve_agent_user_id(self, client) -> None:
        """Resolve the agent's own backend user id.

        Lets the trigger checker self-exclude its messages and detect threads
        it participates in (replaces the legacy #ai-response title tag).
        """
        try:
            me = await client.user.list()
            self.tutor_config.triggers.agent_user_id = str(me.id)
            logger.info(f"Agent backend user id resolved: {me.id}")
        except Exception as e:
            logger.warning(
                f"Could not resolve agent user id; follow-up detection will be degraded: {e}"
            )

    def _scheduler_config(self):
        """Return the top-level scheduler config section (or defaults)."""
        from computor_agent.settings.config import SchedulerConfig

        if self.config.scheduler:
            scheduler_config = self.config.scheduler
            logger.info(
                f"Scheduler config: catchup={scheduler_config.poll_interval_seconds}s, "
                f"workers={scheduler_config.max_concurrent_processing}"
            )
        else:
            scheduler_config = SchedulerConfig()
            logger.info("Using default scheduler config")
        return scheduler_config

    def _make_trigger_callback(self, agent):
        """Build the message-trigger callback the scheduler invokes."""

        async def on_message_trigger(result, course_content, channel):
            """
            Handle message trigger from WebSocket scheduler.

            Args:
                result: TriggerCheckResult with message_trigger
                course_content: CourseContentStudentGet (may be None for WebSocket)
                channel: WebSocket channel (e.g., "submission_group:123")
            """
            logger.info(f"Processing message trigger (WebSocket): {result.reason}")
            if self.options.dry_run:
                logger.info(
                    f"[DRY RUN] Would process message: {result.message_trigger.message_id}"
                )
                return

            message = {
                "id": result.message_trigger.message_id,
                "content": result.message_trigger.content,
                "title": result.message_trigger.title,
                "author_id": result.message_trigger.author_id,
                "is_follow_up": result.message_trigger.is_follow_up,
                "thread_root_id": result.root_message_id,
            }

            processing_result = await agent.process_message(
                submission_group_id=result.message_trigger.submission_group_id,
                message=message,
                course_content=course_content,
                course_member_id=None,
            )

            if not processing_result.success:
                raise RuntimeError(
                    f"Message processing failed: {processing_result.error}"
                )

        return on_message_trigger

    async def _build_scheduler(self, client, tutor_llm):
        """Create the TutorAgent and WebSocket scheduler.

        Returns None (after printing the error) when no auth token can be
        resolved — the WebSocket is the only transport.
        """
        from computor_agent.tutor import TutorAgent
        from computor_agent.tutor.websocket import ComputorWebSocket, WebSocketScheduler

        agent = TutorAgent(
            config=self.tutor_config,
            llm=tutor_llm,
            client=client,
            figure_reviewer=self.figure_reviewer,
        )
        scheduler_config = self._scheduler_config()

        token = await get_ws_token(client, self.config.backend)
        if not token:
            logger.error(
                "No authentication token available for the WebSocket connection. "
                "Configure backend.api_token or username/password in the config file."
            )
            self.console.print(
                "[bold red]Error:[/bold red] no authentication token available "
                "for the WebSocket connection."
            )
            return None

        ws = ComputorWebSocket(
            base_url=self.config.backend.url,
            token=token,
        )

        scheduler = WebSocketScheduler(
            client=client,
            ws=ws,
            trigger_config=self.tutor_config.triggers,
            on_message_trigger=self._make_trigger_callback(agent),
            cooldown_seconds=scheduler_config.cooldown_seconds,
            max_concurrent_processing=scheduler_config.max_concurrent_processing,
            periodic_catchup_seconds=scheduler_config.poll_interval_seconds,
            token_provider=make_token_provider(client, self.config.backend),
            metrics=self.metrics,
        )
        logger.info("Using WebSocket for real-time events")
        return scheduler

    async def _run_until_shutdown(self, scheduler) -> None:
        """Run scheduler + LLM probe + dashboard until a signal or failure."""
        shutdown_event = asyncio.Event()

        def signal_handler():
            logger.info("Shutdown signal received")
            shutdown_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        # Start scheduler in background task
        scheduler_task = asyncio.create_task(
            self._run_scheduler(scheduler, shutdown_event)
        )

        # Periodic LLM liveness probe. Off when interval == 0.
        llm_monitor = None
        if self.options.llm_probe_interval > 0:
            from computor_agent.api.llm_health import LLMHealthMonitor

            llm_monitor = LLMHealthMonitor(
                provider=self.llm_provider,
                metrics=self.metrics,
                interval_seconds=self.options.llm_probe_interval,
            )
            await llm_monitor.start()
            logger.info(
                f"LLM probe enabled (every {self.options.llm_probe_interval:g}s)"
            )

        wait_tasks = [scheduler_task, asyncio.create_task(shutdown_event.wait())]
        if self._api_task is not None:
            wait_tasks.append(self._api_task)

        # Wait for shutdown signal or scheduler completion
        done, pending = await asyncio.wait(
            wait_tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Stop the LLM probe first; it may be mid-request and we want to
        # avoid trailing log lines after "stopped".
        if llm_monitor is not None:
            await llm_monitor.stop()

        # Stop the API server next so its socket releases before we tear down the loop
        if self._api_server is not None:
            await self._api_server.stop()
        if self._api_task is not None and not self._api_task.done():
            try:
                await asyncio.wait_for(self._api_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._api_task.cancel()

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Stop scheduler
        await scheduler.stop()
        logger.info("Tutor scheduler stopped")

    async def _run_scheduler(self, scheduler, shutdown_event) -> None:
        """Run the scheduler; on unrecoverable failure record a nonzero exit
        code and signal shutdown so the process exits (and a container restart
        policy can relaunch it).

        start() blocks until stopped. Recoverable connection losses are
        retried internally forever; only unrecoverable failures (auth
        exhaustion, attempt limit, unexpected errors) raise.
        """
        from computor_agent.tutor.errors import is_auth_error

        try:
            await scheduler.start()
            # Scheduler exited normally (clean stop)
            logger.info("WebSocket scheduler exited")
        except Exception as e:
            self._run_state["exit_code"] = 1
            if is_auth_error(e):
                logger.error(
                    "Authentication failed. Please check your credentials and try again."
                )
                logger.error("Run 'computor-agent login' to re-authenticate.")
            else:
                logger.error(f"WebSocket scheduler error: {e}")
        finally:
            # Only signal shutdown if we're not already shutting down
            if not shutdown_event.is_set():
                logger.info("Signaling shutdown after scheduler exit")
                shutdown_event.set()
