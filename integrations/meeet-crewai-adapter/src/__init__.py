"""MEEET Trust Adapter — connect CrewAI, AutoGen, LangGraph to MEEET World."""

from meeet_trust.meeet_guard import (
    MeeetGuard,
    MeeetGuardError,
    TrustResult,
    TrustCheckFailed,
    AgentIdentity,
)

__version__ = "0.1.0"

__all__ = [
    "MeeetGuard",
    "MeeetGuardError",
    "TrustResult",
    "TrustCheckFailed",
    "AgentIdentity",
]
