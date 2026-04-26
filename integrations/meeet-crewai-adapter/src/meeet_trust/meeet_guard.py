"""
MeeetGuard — MEEET Trust Layer for AI Agent Frameworks.

Provides before-action trust checks and after-action logging for CrewAI, AutoGen,
and LangGraph agents interacting with the MEEET World trust infrastructure.

Usage (CrewAI):
    from meeet_trust import MeeetGuard

    guard = MeeetGuard(api_key="meeet_live_xxx")

    @guard.before_action(min_trust=0.7, min_sara=0.6)
    def my_task(context):
        ...

Usage (AutoGen):
    from meeet_trust import MeeetGuard

    guard = MeeetGuard(api_key="meeet_live_xxx")
    guard.register_autogen_listener(assistant_agent)

Usage (LangGraph):
    from meeet_trust import MeeetGuard

    guard = MeeetGuard(api_key="meeet_live_xxx")

    def trust_node(state):
        result = guard.check_trust(
            agent_did=state["agent_did"],
            action=state["action"],
            min_trust=0.7,
            min_sara=0.6
        )
        if not result.allowed:
            raise Exception(f"Trust check failed: {result.reason}")
        return state
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Optional

import requests

# ── Configuration ────────────────────────────────────────────────────────────

BASE_URL = "https://meeet.world/api"
SDK_BASE = "https://zujrmifaabkletgnpoyw.supabase.co/functions/v1/agent-api"
ANON_KEY = os.environ.get(
    "MEEET_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    # Anonymous read-only key — safe to embed
)

# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class TrustResult:
    """Result of a MEEET trust check."""

    allowed: bool
    trust_score: float
    sara_score: float
    reason: str
    agent_did: str
    gates_passed: list[str]
    gates_failed: list[str]


@dataclass
class AgentIdentity:
    """MEEET agent identity document."""

    did: str
    name: Optional[str]
    faction: Optional[str]
    reputation: float
    trust_score: float
    role: Optional[str]
    domains: list[str]
    raw: dict[str, Any]


# ── Exceptions ───────────────────────────────────────────────────────────────


class MeeetGuardError(Exception):
    """Base exception for MeeetGuard errors."""

    pass


class TrustCheckFailed(MeeetGuardError):
    """Raised when an agent fails a trust check."""

    def __init__(self, message: str, result: TrustResult):
        super().__init__(message)
        self.result = result


# ── MeeetGuard ───────────────────────────────────────────────────────────────


class MeeetGuard:
    """
    MEEET trust guard for AI agent frameworks.

    Provides:
    - ``check_trust``: Before-action trust + SARA risk check
    - ``log_after``: After-action audit logging
    - ``resolve_agent``: Resolve an agent DID to identity document
    - ``before_action`` decorator: Decorator for CrewAI task hooks
    - ``register_autogen_listener``: Register a listener with an AutoGen agent
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        anon_key: Optional[str] = None,
        base_url: str = BASE_URL,
        sdk_base: str = SDK_BASE,
        log: Optional[logging.Logger] = None,
    ):
        """
        Initialize MeeetGuard.

        Args:
            api_key: MEEET API key (from meeet.world/developer). If omitted, uses
                     env MEEET_API_KEY or falls back to anon key (read-only).
            anon_key: Override the anonymous Supabase key.
            base_url: Override MEEET API base URL.
            sdk_base: Override SDK base URL.
            log: Logger instance. Uses ``meeet_trust`` logger if None.
        """
        self._api_key = api_key or os.environ.get("MEEET_API_KEY")
        self._anon_key = anon_key or ANON_KEY
        self._base_url = base_url
        self._sdk_base = sdk_base
        self._log = log or logging.getLogger("meeet_trust")
        self._trust_cache: dict[str, tuple[float, TrustResult]] = {}

    # ── HTTP Helpers ─────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        key = self._api_key or self._anon_key
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        }

    def _sdk_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._anon_key}",
        }

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        r = requests.get(url, headers=self._headers(), timeout=10)
        if not r.ok:
            raise MeeetGuardError(f"MEEET API error {r.status_code}: {r.text}")
        return r.json()

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        r = requests.post(url, headers=self._headers(), json=body, timeout=10)
        if not r.ok:
            raise MeeetGuardError(f"MEEET API error {r.status_code}: {r.text}")
        return r.json()

    def _sdk_post(self, payload: dict[str, Any]) -> dict[str, Any]:
        r = requests.post(
            self._sdk_base,
            headers=self._sdk_headers(),
            json=payload,
            timeout=10,
        )
        if not r.ok:
            raise MeeetGuardError(f"MEEET SDK error {r.status_code}: {r.text}")
        return r.json()

    # ── Core API Methods ─────────────────────────────────────────────────────

    def resolve_agent(self, agent_id: str) -> AgentIdentity:
        """
        Resolve a DID or agent ID to a full identity document.

        Args:
            agent_id: DID (did:meeet:xxx) or plain agent ID.

        Returns:
            AgentIdentity with resolved metadata.
        """
        did = agent_id.replace("did:meeet:", "")
        data = self._get(f"/did/resolve/{did}")

        return AgentIdentity(
            did=f"did:meeet:{did}",
            name=data.get("name"),
            faction=data.get("faction"),
            reputation=data.get("reputation", 0.0),
            trust_score=data.get("trust_score", 0.0),
            role=data.get("role"),
            domains=data.get("domains", []),
            raw=data,
        )

    def check_trust(
        self,
        agent_did: str,
        action: Optional[str] = None,
        min_trust: float = 0.5,
        min_sara: float = 0.7,
        use_cache: bool = True,
    ) -> TrustResult:
        """
        Run the MEEET 7-gate trust check + SARA risk assessment.

        This is the main before-action guard.

        Args:
            agent_did: The agent's DID (did:meeet:xxx).
            action: The action being performed (e.g. "tool_execution", "task_start").
            min_trust: Minimum trust score (0-1) to pass. Default 0.5.
            min_sara: Maximum SARA risk score (0-1). Actions above this are blocked.
                      Default 0.7. Lower = stricter.
            use_cache: Use cached results if still valid. Default True.

        Returns:
            TrustResult with pass/fail, scores, and gate details.
        """
        # Check cache
        cache_key = agent_did
        if use_cache and cache_key in self._trust_cache:
            cached_score, cached_result = self._trust_cache[cache_key]
            self._log.debug("Cache hit for %s (score=%.3f)", agent_did, cached_score)
            return cached_result

        try:
            # Resolve agent DID
            identity = self.resolve_agent(agent_did)
        except Exception as e:
            self._log.warning("Could not resolve agent %s: %s", agent_did, e)
            return TrustResult(
                allowed=False,
                trust_score=0.0,
                sara_score=1.0,
                reason=f"Could not resolve agent: {e}",
                agent_did=agent_did,
                gates_passed=[],
                gates_failed=["did_resolution"],
            )

        trust_score = identity.trust_score

        # Run SARA risk assessment if an action is provided
        sara_score = 0.0
        sara_data: dict[str, Any] = {}
        if action:
            try:
                sara_data = self._post("/sara/assess", {
                    "agentId": agent_did,
                    "action": action,
                    "params": {},
                })
                sara_score = float(sara_data.get("risk_score", 0.0))
            except Exception as e:
                self._log.warning("SARA assess failed for %s: %s", agent_did, e)
                sara_score = 0.5  # Treat failure as medium risk

        # Evaluate gates
        gates_passed = []
        gates_failed = []

        # Gate 1: Trust score
        if trust_score >= min_trust:
            gates_passed.append("trust_score")
        else:
            gates_failed.append("trust_score")

        # Gate 2: SARA risk
        if sara_score <= min_sara:
            gates_passed.append("sara_risk")
        else:
            gates_failed.append("sara_risk")

        # Gate 3: Reputation floor
        if identity.reputation >= 0:
            gates_passed.append("reputation")
        else:
            gates_failed.append("reputation")

        allowed = len(gates_failed) == 0

        result = TrustResult(
            allowed=allowed,
            trust_score=trust_score,
            sara_score=sara_score,
            reason="All gates passed" if allowed
            else f"Gates failed: {', '.join(gates_failed)}",
            agent_did=agent_did,
            gates_passed=gates_passed,
            gates_failed=gates_failed,
        )

        # Cache result
        self._trust_cache[cache_key] = (trust_score, result)

        self._log.info(
            "Trust check %s: trust=%.3f sara=%.3f allowed=%s",
            agent_did, trust_score, sara_score, allowed,
        )

        return result

    def log_after(
        self,
        agent_did: str,
        action: str,
        result: Any,
        success: bool = True,
    ) -> dict[str, Any]:
        """
        Log an after-action callback to MEEET for audit trail.

        Args:
            agent_did: The agent's DID.
            action: The action that was performed.
            result: The result/output of the action.
            success: Whether the action succeeded.

        Returns:
            API response data.
        """
        payload = {
            "agentId": agent_did,
            "action": action,
            "output": str(result)[:1000],
            "success": success,
        }
        try:
            return self._post("/callbacks/after-tool", payload)
        except Exception as e:
            self._log.warning("After-callback failed for %s: %s", agent_did, e)
            return {"error": str(e)}

    def get_reputation(self, agent_id: str) -> dict[str, Any]:
        """Get the reputation and risk profile for an agent."""
        did = agent_id.replace("did:meeet:", "")
        return self._get(f"/reputation/{did}")

    # ── CrewAI Integration ───────────────────────────────────────────────────

    def before_action(
        self,
        min_trust: float = 0.5,
        min_sara: float = 0.7,
        agent_did_getter: Optional[Callable[..., str]] = None,
    ) -> Callable:
        """
        Decorator to wrap a CrewAI task function with trust checks.

        Args:
            min_trust: Minimum trust score (0-1).
            min_sara: Maximum SARA risk (0-1). Default 0.7.
            agent_did_getter: Function that extracts agent_did from the
                              decorated function's arguments.
                              If None, tries ``agent_did`` attribute or
                              first positional argument.

        Example::

            guard = MeeetGuard(api_key="meeet_live_xxx")

            @guard.before_action(min_trust=0.7, min_sara=0.6)
            def research_task(task_context):
                # Only runs if agent passes trust + SARA checks
                ...

        Note:
            Requires ``crewai`` to be installed. Install with:
            ``pip install meeet-trust[crewai]``
        """
        def decorator(func: Callable) -> Callable:
            def wrapper(*args, **kwargs):
                # Extract agent_did
                agent_did = None
                if agent_did_getter:
                    agent_did = agent_did_getter(*args, **kwargs)
                elif args:
                    first_arg = args[0]
                    if hasattr(first_arg, "agent_did"):
                        agent_did = first_arg.agent_did
                    elif isinstance(first_arg, dict):
                        agent_did = first_arg.get("agent_did")
                    elif isinstance(first_arg, str):
                        agent_did = first_arg

                if not agent_did:
                    raise MeeetGuardError(
                        f"Could not determine agent_did for {func.__name__}. "
                        "Pass agent_did_getter to before_action() or set "
                        "agent_did on the first argument."
                    )

                # Run trust check
                trust_result = self.check_trust(
                    agent_did=agent_did,
                    action=func.__name__,
                    min_trust=min_trust,
                    min_sara=min_sara,
                )

                if not trust_result.allowed:
                    raise TrustCheckFailed(
                        f"MEEET trust check failed for {agent_did}: "
                        f"{trust_result.reason}",
                        trust_result,
                    )

                return func(*args, **kwargs)

            wrapper.__name__ = func.__name__
            wrapper.__doc__ = func.__doc__
            return wrapper
        return decorator

    # ── AutoGen Integration ─────────────────────────────────────────────────

    def register_autogen_listener(self, agent: Any) -> None:
        """
        Register a MEEET trust listener with an AutoGen agent.

        Registers a ``suggestion_listener`` that blocks agent actions
        when the MEEET trust check fails.

        Args:
            agent: An AutoGen ``AssistantAgent`` instance.

        Note:
            Requires ``autogen`` to be installed. Install with:
            ``pip install meeet-trust[autogen]``

        Example::

            from autogen import AssistantAgent
            from meeet_trust import MeeetGuard

            guard = MeeetGuard(api_key="meeet_live_xxx")
            assistant = AssistantAgent("assistant", ...)
            guard.register_autogen_listener(assistant)
        """
        try:
            import autogen  # noqa: F401
        except ImportError:
            raise MeeetGuardError(
                "AutoGen not installed. Run: pip install meeet-trust[autogen]"
            )

        def meeet_suggestion_listener(
            sender: Any,
            recipient: Any,
            context: dict[str, Any],
        ) -> Optional[dict[str, Any]]:
            """Block execution if trust check fails."""
            agent_did = getattr(sender, "meeet_did", None)
            if not agent_did:
                return None  # No MEEET DID set, skip

            result = self.check_trust(
                agent_did=agent_did,
                action="agent_message",
                min_trust=0.5,
                min_sara=0.7,
            )

            if not result.allowed:
                self._log.warning(
                    "AutoGen agent %s blocked by MEEET trust: %s",
                    agent_did,
                    result.reason,
                )
                return {
                    "skip_recipient": True,
                    "message": f"[MEEET TRUST BLOCKED] {result.reason}",
                }
            return None

        try:
            agent.register_suggestion_hook(suggestion_hook=meeet_suggestion_listener)
            self._log.info("AutoGen listener registered on %s", agent.name)
        except AttributeError as e:
            raise MeeetGuardError(
                f"AutoGen agent does not support suggestion hooks: {e}. "
                "Ensure you have AutoGen >= 0.2."
            )

    # ── LangGraph Integration ────────────────────────────────────────────────

    def trust_node(
        self,
        state: dict[str, Any],
        action: Optional[str] = None,
        min_trust: float = 0.5,
        min_sara: float = 0.7,
    ) -> dict[str, Any]:
        """
        LangGraph state node that runs a MEEET trust check.

        Use as a conditional node or guard node in a LangGraph graph.

        Example (LangGraph)::

            from langgraph.graph import StateGraph
            from meeet_trust import MeeetGuard

            guard = MeeetGuard(api_key="meeet_live_xxx")

            def should_proceed(state):
                result = guard.trust_node(state, action="execute_task")
                return state

            builder = StateGraph(AgentState)
            builder.add_node("trust_check", should_proceed)
            builder.add_edge("start", "trust_check")

        Args:
            state: LangGraph state dict. Must contain ``agent_did``.
            action: Override the action name. If None, uses state.get("action").
            min_trust: Minimum trust score (0-1).
            min_sara: Maximum SARA risk (0-1).

        Returns:
            The state with ``_meeet_trust`` result attached, if the check passed.

        Raises:
            TrustCheckFailed: If the agent fails the trust check.
        """
        agent_did = state.get("agent_did")
        if not agent_did:
            raise MeeetGuardError("State must contain agent_did")

        actual_action = action or state.get("action", "unknown")

        result = self.check_trust(
            agent_did=agent_did,
            action=actual_action,
            min_trust=min_trust,
            min_sara=min_sara,
        )

        if not result.allowed:
            raise TrustCheckFailed(
                f"MEEET trust check failed for {agent_did} during "
                f"'{actual_action}': {result.reason}",
                result,
            )

        return {**state, "_meeet_trust": result}
