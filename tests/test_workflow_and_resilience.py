"""
Tests for:
1. Stateful workflow engine (LangGraph-style StateGraph pattern)
2. State transitions, conditional routing & checkpoints
3. Workflow pause and resume capabilities
4. Recursion limits and loop guards
5. Exponential backoff retry mechanism with jitter
6. Rate limiting and concurrency controls
"""

import time
import pytest
from app.schemas import MasterOrchestrationRequest, SubTask, EvidenceItem, ClaimStatus
from app.services.resilience import (
    retry_with_backoff,
    RateLimiter,
    ConcurrencyLimiter
)
from app.services.workflow_engine import (
    WorkflowState,
    StatefulWorkflowEngine,
    execute_workflow,
    END
)
from app.services.task_store import get_task, save_task, _MEMORY_CACHE


# ===========================================================================
# 1. Stateful Workflow Engine & Node Transitions
# ===========================================================================

class TestStatefulWorkflowEngine:
    def test_workflow_executes_all_nodes_in_order(self):
        """Validates that state transitions through security, decomposition, subagents, verification, synthesis, and pdf."""
        initial_state = WorkflowState(
            task_id="test-wf-order-001",
            query="Analyze global solar PV generation efficiency in 2024",
            include_web=False,
            include_knowledge_base=False,
            generate_pdf=True
        )
        engine = StatefulWorkflowEngine()
        final_state = engine.run(initial_state)

        assert final_state.status == "completed"
        assert final_state.progress == 100
        # Check node history
        assert "security" in final_state.node_history
        assert "decomposition" in final_state.node_history
        assert "subagents" in final_state.node_history
        assert "verification" in final_state.node_history
        assert "synthesis" in final_state.node_history
        assert "pdf" in final_state.node_history
        assert final_state.report_id is not None
        assert final_state.pdf_download_url is not None

    def test_workflow_checkpoints_at_every_step(self):
        """Every node transition must save a state checkpoint to disk."""
        task_id = "test-wf-checkpoint-002"
        initial_state = WorkflowState(
            task_id=task_id,
            query="Assess advanced packaging for 3nm semiconductor chips",
            include_web=False,
            include_knowledge_base=False,
            generate_pdf=False
        )
        engine = StatefulWorkflowEngine()
        final_state = engine.run(initial_state)

        assert len(final_state.checkpoints) >= 5
        # Verify checkpoints are persisted on disk
        persisted = get_task(task_id)
        assert persisted is not None
        assert len(persisted["checkpoints"]) == len(final_state.checkpoints)
        assert persisted["checkpoints"][0]["node"] == "security"

    def test_conditional_edge_clarification_gate(self):
        """When query is ambiguous, workflow routes to END with status='clarification_needed'."""
        ambiguous_state = WorkflowState(
            task_id="test-wf-clarify-003",
            query="tell me about it",  # Under-specified vague query
            include_web=False,
            include_knowledge_base=False
        )
        engine = StatefulWorkflowEngine()
        final_state = engine.run(ambiguous_state)

        assert final_state.status == "clarification_needed"
        assert "clarification" in final_state.executive_summary.lower()
        # Should NOT have executed subagents or pdf
        assert "subagents" not in final_state.node_history
        assert "pdf" not in final_state.node_history

    def test_resume_interrupted_workflow_from_checkpoint(self):
        """Workflow can be resumed from an intermediate checkpoint."""
        task_id = "test-wf-resume-004"
        # Simulate an interrupted state after decomposition
        mid_state = WorkflowState(
            task_id=task_id,
            query="Evaluate utility-scale battery efficiency in Texas",
            effective_query="Evaluate utility-scale battery efficiency in Texas",
            current_node="subagents",  # Paused before subagents
            step_count=2,
            node_history=["security", "decomposition"],
            generate_pdf=False
        )
        save_task(task_id, mid_state.model_dump())

        # Wipe memory cache
        _MEMORY_CACHE.pop(task_id, None)

        # Resume from disk
        resumed_data = get_task(task_id)
        state_to_resume = WorkflowState(**resumed_data)

        engine = StatefulWorkflowEngine()
        final_state = engine.run(state_to_resume)

        assert final_state.status == "completed"
        assert "subagents" in final_state.node_history
        assert "verification" in final_state.node_history
        assert "synthesis" in final_state.node_history


# ===========================================================================
# 2. Limits (Recursion, Rate Limiting, Concurrency)
# ===========================================================================

class TestLimits:
    def test_recursion_limit_halts_infinite_loops(self):
        """Workflow terminates cleanly when recursion_limit is exceeded."""
        state = WorkflowState(
            task_id="test-wf-recursion-005",
            query="Test query with recursion guard",
            current_node="security",
            step_count=0,
            generate_pdf=False
        )
        # Set artificially small recursion limit
        engine = StatefulWorkflowEngine(recursion_limit=3)
        final_state = engine.run(state)

        assert final_state.step_count <= 4
        assert any("recursion step limit" in lim.lower() for lim in final_state.limitations)
        assert final_state.status == "completed"

    def test_rate_limiter_allows_and_throttles(self):
        """Rate limiter allows requests within limit and throttles when exceeded."""
        limiter = RateLimiter(default_limit=3, window_seconds=60)
        client_key = "client-test-ip-1"

        assert limiter.is_allowed(client_key) is True
        assert limiter.is_allowed(client_key) is True
        assert limiter.is_allowed(client_key) is True
        # 4th request exceeds limit of 3
        assert limiter.is_allowed(client_key) is False

        # Reset
        limiter.reset(client_key)
        assert limiter.is_allowed(client_key) is True

    def test_concurrency_limiter_semaphore(self):
        """Concurrency limiter controls parallel access."""
        limiter = ConcurrencyLimiter(max_concurrency=2)
        with limiter:
            # 1 slot active
            assert limiter.semaphore._value == 1
            with limiter:
                # 2 slots active
                assert limiter.semaphore._value == 0
        # Released
        assert limiter.semaphore._value == 2


# ===========================================================================
# 3. Retries (Exponential Backoff & Resilience)
# ===========================================================================

class TestRetries:
    def test_retry_succeeds_on_transient_failure(self):
        """Operation retries after transient exceptions and succeeds on subsequent try."""
        attempts = 0

        @retry_with_backoff(max_retries=3, initial_delay=0.02, backoff_factor=1.5)
        def transient_function():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionError("Network blip")
            return "SUCCESS"

        result = transient_function()
        assert result == "SUCCESS"
        assert attempts == 3

    def test_retry_raises_after_max_retries_exhausted(self):
        """Operation raises exception when max_retries limit is reached."""
        attempts = 0

        @retry_with_backoff(max_retries=2, initial_delay=0.01, backoff_factor=1.5)
        def always_failing_function():
            nonlocal attempts
            attempts += 1
            raise TimeoutError("Service timeout")

        with pytest.raises(TimeoutError):
            always_failing_function()

        assert attempts == 3  # Initial try + 2 retries = 3 attempts total

    def test_retry_does_not_retry_unlisted_exceptions(self):
        """Non-retryable exceptions fail immediately without retrying."""
        attempts = 0

        @retry_with_backoff(max_retries=3, initial_delay=0.01, retryable_exceptions=(ConnectionError,))
        def wrong_exception_function():
            nonlocal attempts
            attempts += 1
            raise ValueError("Input invalid")

        with pytest.raises(ValueError):
            wrong_exception_function()

        assert attempts == 1  # No retries on ValueError
