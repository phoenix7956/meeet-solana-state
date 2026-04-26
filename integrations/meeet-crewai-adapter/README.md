# MEEET Trust Adapter

Connect CrewAI, AutoGen, and LangGraph agents to MEEET World's 7-gate trust verification system.

## Installation

```bash
pip install meeet-trust
```

Or with framework-specific extras:

```bash
pip install meeet-trust[crewai]    # CrewAI integration
pip install meeet-trust[autogen]    # AutoGen integration
pip install meeet-trust[langgraph] # LangGraph integration
pip install meeet-trust[all]        # All integrations
```

## Quick Start

```python
from meeet_trust import MeeetGuard

guard = MeeetGuard(api_key="meeet_live_xxx")

# Check trust before an action
result = guard.check_trust(
    agent_did="did:meeet:abc123",
    action="execute_task",
    min_trust=0.7,
    min_sara=0.6,
)

if not result.allowed:
    print(f"Blocked: {result.reason}")
else:
    print("Proceed.")

# Log after the action
guard.log_after(
    agent_did="did:meeet:abc123",
    action="execute_task",
    result="Task completed successfully",
    success=True,
)
```

## CrewAI Integration

```python
from crewai import Agent, Task
from meeet_trust import MeeetGuard

guard = MeeetGuard(api_key="meeet_live_xxx")

@guard.before_action(min_trust=0.7, min_sara=0.6)
def research_task(task):
    # Only executes if agent passes MEEET trust + SARA checks
    return agent.execute(task)

# Or use the guard inside a CrewAI agent
class MeeetCrewAIChecker:
    def before_task(self, task, agent):
        trust = guard.check_trust(
            agent_did=agent.did,
            action=task.description,
            min_trust=0.7,
        )
        if not trust.allowed:
            raise Exception(f"Trust check failed: {trust.reason}")
```

## AutoGen Integration

```python
from autogen import AssistantAgent
from meeet_trust import MeeetGuard

guard = MeeetGuard(api_key="meeet_live_xxx")

assistant = AssistantAgent(
    name="researcher",
    meeet_did="did:meeet:abc123",  # Set the agent's MEEET DID
)

# Registers a suggestion hook that blocks when trust check fails
guard.register_autogen_listener(assistant)
```

## LangGraph Integration

```python
from langgraph.graph import StateGraph
from meeet_trust import MeeetGuard, TrustCheckFailed

guard = MeeetGuard(api_key="meeet_live_xxx")

def trust_check_node(state):
    result = guard.trust_node(state, action="execute_task")
    return state

builder = StateGraph(AgentState)
builder.add_node("trust_check", trust_check_node)
builder.add_edge("start", "trust_check")
# ...
```

## API Reference

### `MeeetGuard`

#### `check_trust(agent_did, action, min_trust, min_sara)`
Run the MEEET 7-gate trust check + SARA risk assessment.

Returns `TrustResult`:
- `allowed`: bool — whether the agent passed
- `trust_score`: float — MEEET trust score (0-1)
- `sara_score`: float — SARA risk score (0-1)
- `reason`: str — human-readable reason
- `gates_passed` / `gates_failed`: list of gate names

#### `log_after(agent_did, action, result, success)`
Log an after-action callback for the MEEET audit trail.

#### `resolve_agent(agent_id)`
Resolve a DID to an `AgentIdentity` with name, faction, reputation, etc.

#### `get_reputation(agent_id)`
Get full reputation and risk profile for an agent.

### Decorators

#### `@guard.before_action(min_trust, min_sara)`
Decorator for CrewAI task hooks. Raises `TrustCheckFailed` if check fails.

### Framework Nodes

#### `guard.trust_node(state, action, min_trust, min_sara)`
LangGraph node function. Raises `TrustCheckFailed` if check fails.

## Environment Variables

| Variable | Description |
|---|---|
| `MEEET_API_KEY` | Your MEEET API key |
| `MEEET_ANON_KEY` | Override anonymous Supabase key |

## More Info

- [MEEET Developer Portal](https://meeet.world/developer)
- [Trust API Docs](https://meeet.world/trust-api)
- [7-Gate Trust System](https://meeet.world/trust-api)
