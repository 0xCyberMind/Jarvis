"""Agents package: lightweight adapter layer for evolving JARVIS into an agent-based core.

This package contains a minimal AgentManager and thin adapters that wrap
existing modules (memory, planner, actions) without replacing them.
"""

from .manager import AgentManager
from .base import BaseAgent

__all__ = ["AgentManager", "BaseAgent"]
