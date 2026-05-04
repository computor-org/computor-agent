"""HTTP dashboard and health-check API for the running tutor agent.

Off by default; opted in via the `--api-port` flag on `tutor messaging`.
Runs in the same asyncio event loop as the scheduler, so metrics and
scheduler state are read directly without IPC.
"""

from computor_agent.api.metrics import MetricsCollector

__all__ = ["MetricsCollector"]
