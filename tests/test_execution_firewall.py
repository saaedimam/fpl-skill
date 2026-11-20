import pytest
from fpl_skill.execution_sandbox import ExecutionSandbox
from fpl_skill.live_state import ExecutionDenied

def test_simulation_is_non_mutating_and_account_write_methods_refuse():
    sandbox = ExecutionSandbox.__new__(ExecutionSandbox)
    sandbox.team_id = "123"
    # The RC adapter's network capability must be absent when a mutation is attempted.
    for name in ("execute_transfer", "submit_lineup", "use_chip", "mutate_account"):
        method = getattr(sandbox, name, None)
        assert callable(method), f"missing fail-closed RC mutation entrypoint: {name}"
        with pytest.raises(ExecutionDenied):
            method()
