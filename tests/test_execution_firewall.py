import pytest
from fpl_skill.execution_sandbox import ExecutionDenied, ExecutionSandbox

def test_all_account_writes_refused_without_transport():
    sandbox=ExecutionSandbox.__new__(ExecutionSandbox)
    sandbox.team_id="123"
    for method,args in [
       ("execute_transfer",()),("submit_lineup",()),("use_chip",()),("mutate_account",())
    ]:
       with pytest.raises(ExecutionDenied): getattr(sandbox,method)(*args)
