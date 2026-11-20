import pytest
from unittest.mock import patch

from fpl_skill.live_state import ExecutionDenied
from fpl_skill.execution_sandbox import ExecutionSandbox

class FakeAdapter:
    def __init__(self):
        self.session = object()
        self.transport = object()

def test_every_live_mutation_is_denied_and_transport_is_discarded():
    sandbox = ExecutionSandbox("123", adapter=FakeAdapter())
    for method in ("execute_transfer","submit_lineup","use_chip","mutate_account","post_transfer","save_lineup"):
        sandbox.adapter = FakeAdapter()
        with pytest.raises(ExecutionDenied):
            getattr(sandbox,method)()
        assert sandbox.adapter is None

def test_execution_refusal_performs_no_network_operation():
    sandbox = ExecutionSandbox("123", adapter=FakeAdapter())
    with patch("urllib.request.urlopen", side_effect=AssertionError("egress attempted")) as urlopen:
        with pytest.raises(ExecutionDenied):
            sandbox.execute_transfer({"player_out":1,"player_in":2})
        urlopen.assert_not_called()
