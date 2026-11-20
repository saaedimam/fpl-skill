from unittest.mock import patch

import pytest

from fpl_skill.approval_gate import ExecutionDenied
from fpl_skill.execution import execute_account_mutation


def test_execution_denied_is_the_single_canonical_exception():
    from fpl_skill.live_state import ExecutionDenied as LiveStateExecutionDenied

    assert LiveStateExecutionDenied is ExecutionDenied


def test_account_mutation_refuses_without_transport_or_session_egress():
    with patch("urllib.request.urlopen", side_effect=AssertionError("egress attempted")) as urlopen:
        with pytest.raises(ExecutionDenied):
            execute_account_mutation(
                team_id="synthetic-test-team",
                endpoint="/api/test/",
                payload={},
                mode="advisory",
                session=object(),
                transport=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("transport called")),
            )
        urlopen.assert_not_called()
