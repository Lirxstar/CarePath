# Agents

Shared CarePath agent workflow package boundary.

The executable bounded state graph lives in `backend/agents/workflow.py`.

CP-009 implements Safety Triage, Context Builder, Tool Router, Analytics Tools, Personal Context Retriever, External Evidence Retriever, Planner, Verifier, Composer, and Feedback Update with serialisable state, bounded retries, and controlled failure handling.

See `docs/cp009_agent_state_graph.md` for the state contract and acceptance mapping.
