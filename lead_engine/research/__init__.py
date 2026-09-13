"""Agentic research subsystem (R2+): persistent jobs, scoped tools, and the
orchestrator loop that turns objectives into verified facts."""
from .manager import DEFAULT_BUDGETS, ResearchJobManager

__all__ = ["DEFAULT_BUDGETS", "ResearchJobManager"]
