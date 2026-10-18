"""
Sudarshana Chakra service layer.

Long-running, multi-step capabilities that combine the browser mesh, the LLM
tiers and local storage. Services are synchronous facades over background
asyncio loops so the Qt UI thread never blocks. They are wired into the agent
executor and the Gemini tool declarations like every other action.
"""

from __future__ import annotations

__all__ = ["browser_worker", "job_hunter"]
