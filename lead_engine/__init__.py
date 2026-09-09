"""Lead Engine — quota-aware multi-provider lead generation.

Fallback chain design: cloud providers first, local Ollama as the real
fallback, and PAUSED (not FAILED) when nothing is available.
"""

__version__ = "0.1.0"
