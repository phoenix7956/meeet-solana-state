"""Tests for MeeetGuard."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from unittest.mock import patch, MagicMock


class TestMeeetGuardBasic:
    """Basic unit tests without network calls."""

    def test_trust_result_dataclass(self):
        from meeet_trust import TrustResult

        r = TrustResult(
            allowed=True,
            trust_score=0.85,
            sara_score=0.3,
            reason="All gates passed",
            agent_did="did:meeet:abc123",
            gates_passed=["trust_score", "sara_risk", "reputation"],
            gates_failed=[],
        )
        assert r.allowed is True
        assert r.trust_score == 0.85
        assert r.sara_score == 0.3
        assert "trust_score" in r.gates_passed

    def test_agent_identity_dataclass(self):
        from meeet_trust import AgentIdentity

        ai = AgentIdentity(
            did="did:meeet:test",
            name="Test Agent",
            faction="oraclers",
            reputation=750.0,
            trust_score=0.92,
            role="scientist",
            domains=["ai", "biotech"],
            raw={"extra": "data"},
        )
        assert ai.name == "Test Agent"
        assert ai.trust_score == 0.92
        assert ai.raw["extra"] == "data"

    def test_trust_check_failed_gate(self):
        from meeet_trust import TrustResult

        r = TrustResult(
            allowed=False,
            trust_score=0.3,
            sara_score=0.8,
            reason="Gates failed: trust_score, sara_risk",
            agent_did="did:meeet:badagent",
            gates_passed=["reputation"],
            gates_failed=["trust_score", "sara_risk"],
        )
        assert r.allowed is False
        assert "trust_score" in r.gates_failed
        assert "sara_risk" in r.gates_failed

    def test_meeet_guard_init_defaults(self):
        from meeet_trust import MeeetGuard

        guard = MeeetGuard()
        assert guard._base_url == "https://meeet.world/api"
        assert guard._sdk_base == "https://zujrmifaabkletgnpoyw.supabase.co/functions/v1/agent-api"
        assert guard._log.name == "meeet_trust"

    def test_meeet_guard_init_custom(self):
        from meeet_trust import MeeetGuard

        guard = MeeetGuard(
            api_key="test_key",
            base_url="https://test.meeet.world/api",
        )
        assert guard._api_key == "test_key"
        assert guard._base_url == "https://test.meeet.world/api"


class TestMeeetGuardAPI:
    """Tests with mocked HTTP responses."""

    @patch("meeet_trust.meeet_guard.requests.get")
    def test_resolve_agent_success(self, mock_get):
        from meeet_trust import MeeetGuard

        mock_get.return_value = MagicMock(
            ok=True,
            json=lambda: {
                "did": "did:meeet:abc123",
                "name": "TestBot",
                "faction": "oraclers",
                "reputation": 500.0,
                "trust_score": 0.88,
                "role": "oracle",
                "domains": ["ai"],
            },
        )

        guard = MeeetGuard()
        identity = guard.resolve_agent("did:meeet:abc123")

        assert identity.did == "did:meeet:abc123"
        assert identity.name == "TestBot"
        assert identity.trust_score == 0.88
        assert identity.reputation == 500.0
        mock_get.assert_called_once()

    @patch("meeet_trust.meeet_guard.requests.get")
    def test_resolve_agent_plain_id(self, mock_get):
        from meeet_trust import MeeetGuard

        mock_get.return_value = MagicMock(
            ok=True,
            json=lambda: {"did": "did:meeet:xyz789", "name": "AnotherBot", "trust_score": 0.7},
        )

        guard = MeeetGuard()
        identity = guard.resolve_agent("xyz789")

        called_url = mock_get.call_args[0][0]
        assert "xyz789" in called_url
        assert identity.did == "did:meeet:xyz789"

    @patch("meeet_trust.meeet_guard.requests.post")
    @patch("meeet_trust.meeet_guard.requests.get")
    def test_check_trust_allowed(self, mock_get, mock_post):
        from meeet_trust import MeeetGuard

        mock_get.return_value = MagicMock(
            ok=True,
            json=lambda: {
                "did": "did:meeet:goodagent",
                "trust_score": 0.9,
                "reputation": 800.0,
                "name": "GoodAgent",
            },
        )
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {"risk_score": 0.2},
        )

        guard = MeeetGuard()
        result = guard.check_trust(
            agent_did="did:meeet:goodagent",
            action="run_task",
            min_trust=0.5,
            min_sara=0.7,
        )

        assert result.allowed is True
        assert result.trust_score == 0.9
        assert result.sara_score == 0.2
        assert "trust_score" in result.gates_passed
        assert "sara_risk" in result.gates_passed

    @patch("meeet_trust.meeet_guard.requests.post")
    @patch("meeet_trust.meeet_guard.requests.get")
    def test_check_trust_blocked_low_trust(self, mock_get, mock_post):
        from meeet_trust import MeeetGuard

        mock_get.return_value = MagicMock(
            ok=True,
            json=lambda: {
                "did": "did:meeet:badagent",
                "trust_score": 0.2,
                "reputation": 10.0,
                "name": "BadAgent",
            },
        )
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {"risk_score": 0.1},
        )

        guard = MeeetGuard()
        result = guard.check_trust(
            agent_did="did:meeet:badagent",
            action="run_task",
            min_trust=0.5,
            min_sara=0.7,
        )

        assert result.allowed is False
        assert "trust_score" in result.gates_failed
        assert "sara_risk" in result.gates_passed

    @patch("meeet_trust.meeet_guard.requests.post")
    @patch("meeet_trust.meeet_guard.requests.get")
    def test_check_trust_blocked_high_sara(self, mock_get, mock_post):
        from meeet_trust import MeeetGuard

        mock_get.return_value = MagicMock(
            ok=True,
            json=lambda: {
                "did": "did:meeet:riskyagent",
                "trust_score": 0.8,
                "reputation": 600.0,
                "name": "RiskyAgent",
            },
        )
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {"risk_score": 0.9},
        )

        guard = MeeetGuard()
        result = guard.check_trust(
            agent_did="did:meeet:riskyagent",
            action="dangerous_task",
            min_trust=0.5,
            min_sara=0.7,
        )

        assert result.allowed is False
        assert "sara_risk" in result.gates_failed

    @patch("meeet_trust.meeet_guard.requests.post")
    def test_log_after_success(self, mock_post):
        from meeet_trust import MeeetGuard

        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {"status": "logged"},
        )

        guard = MeeetGuard()
        resp = guard.log_after(
            agent_did="did:meeet:abc123",
            action="run_task",
            result="42 discoveries found",
            success=True,
        )

        assert resp["status"] == "logged"
        call_args = mock_post.call_args
        assert call_args[1]["json"]["agentId"] == "did:meeet:abc123"
        assert call_args[1]["json"]["success"] is True

    @patch("meeet_trust.meeet_guard.requests.post")
    @patch("meeet_trust.meeet_guard.requests.get")
    def test_check_trust_caching(self, mock_get, mock_post):
        from meeet_trust import MeeetGuard

        mock_get.return_value = MagicMock(
            ok=True,
            json=lambda: {
                "did": "did:meeet:cached",
                "trust_score": 0.95,
                "reputation": 999.0,
            },
        )
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {"risk_score": 0.05},
        )

        guard = MeeetGuard()

        guard.check_trust("did:meeet:cached", action="task1")
        guard.check_trust("did:meeet:cached", action="task2")

        assert mock_get.call_count == 1  # cache hit on second call

    def test_before_action_decorator_extracts_did_from_arg(self):
        from meeet_trust import MeeetGuard

        guard = MeeetGuard()

        @guard.before_action(min_trust=0.5)
        def dummy_task(context):
            return "executed"

        class FakeContext:
            agent_did = "did:meeet:test123"

        with patch.object(guard, "check_trust") as mock_check:
            mock_check.return_value = MagicMock(
                allowed=True,
                trust_score=0.9,
                sara_score=0.2,
                reason="ok",
                agent_did="did:meeet:test123",
                gates_passed=["trust_score"],
                gates_failed=[],
            )
            result = dummy_task(FakeContext())

        assert result == "executed"
        mock_check.assert_called_once()

    def test_before_action_decorator_raises_on_blocked(self):
        from meeet_trust import MeeetGuard, TrustCheckFailed

        guard = MeeetGuard()

        @guard.before_action(min_trust=0.5)
        def dummy_task(context):
            return "executed"

        class FakeContext:
            agent_did = "did:meeet:blocked"

        with patch.object(guard, "check_trust") as mock_check:
            mock_check.return_value = MagicMock(
                allowed=False,
                trust_score=0.1,
                sara_score=0.9,
                reason="Gates failed: trust_score, sara_risk",
                agent_did="did:meeet:blocked",
                gates_passed=[],
                gates_failed=["trust_score", "sara_risk"],
            )
            with pytest.raises(TrustCheckFailed):
                dummy_task(FakeContext())


class TestLangGraphIntegration:
    def test_trust_node_passes_state_through(self):
        from meeet_trust import MeeetGuard

        guard = MeeetGuard()

        with patch.object(guard, "check_trust") as mock_check:
            mock_check.return_value = MagicMock(
                allowed=True,
                trust_score=0.9,
                sara_score=0.2,
                reason="ok",
                agent_did="did:meeet:langgraph_test",
                gates_passed=["trust_score", "sara_risk"],
                gates_failed=[],
            )

            state = {"agent_did": "did:meeet:langgraph_test", "action": "test_action"}
            result = guard.trust_node(state, action="test_action")

        assert "agent_did" in result
        assert "_meeet_trust" in result
        assert result["_meeet_trust"].allowed is True

    def test_trust_node_raises_on_blocked(self):
        from meeet_trust import MeeetGuard, TrustCheckFailed

        guard = MeeetGuard()

        with patch.object(guard, "check_trust") as mock_check:
            mock_check.return_value = MagicMock(
                allowed=False,
                trust_score=0.1,
                sara_score=0.95,
                reason="Gates failed: sara_risk",
                agent_did="did:meeet:risky",
                gates_passed=["trust_score"],
                gates_failed=["sara_risk"],
            )

            state = {"agent_did": "did:meeet:risky", "action": "dangerous"}

            with pytest.raises(TrustCheckFailed):
                guard.trust_node(state, action="dangerous")

    def test_trust_node_raises_without_agent_did(self):
        from meeet_trust import MeeetGuard, MeeetGuardError

        guard = MeeetGuard()

        with pytest.raises(MeeetGuardError, match="must contain agent_did"):
            guard.trust_node({}, action="test")
