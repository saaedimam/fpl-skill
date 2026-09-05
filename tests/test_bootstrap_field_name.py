import pytest
from unittest.mock import Mock, patch
from fpl_skill.direct_api import DirectFPLClient, FieldNotFoundError


class TestBootstrapFieldName:
    """Validate bootstrap-static field-name variance handling."""

    def test_bootstrap_static_field_name_events(self):
        """When 'events' field present, use it (live API field)."""
        client = DirectFPLClient()

        mock_response = {
            "events": [{"id": 1, "name": "GW1"}, {"id": 2, "name": "GW2"}],
            "elements": [{"id": 1, "name": "Player A"}],
            "teams": [{"id": 1, "name": "Arsenal"}],
            "game_settings": {"transfers_per_gameweek": 1}
        }

        with patch.object(client, "_get", return_value=mock_response):
            result = client.fetch_master()

        assert result["field_used"] == "events"
        assert len(result["gameweeks"]) == 2
        assert result["gameweeks"][0]["name"] == "GW1"

    def test_bootstrap_static_field_name_gameweeks_fallback(self):
        """When only 'gameweeks' present (no 'events'), use fallback."""
        client = DirectFPLClient()

        mock_response = {
            "gameweeks": [{"id": 1, "name": "GW1"}],  # Old field name
            "elements": [],
            "teams": [],
            "game_settings": {}
        }

        with patch.object(client, "_get", return_value=mock_response):
            result = client.fetch_master()

        assert result["field_used"] == "gameweeks"
        assert len(result["gameweeks"]) == 1

    def test_bootstrap_static_field_name_missing_raises(self):
        """When neither field present, raise FieldNotFoundError."""
        client = DirectFPLClient()

        mock_response = {
            "elements": [],
            "teams": [],
            # No 'events' or 'gameweeks' — error case
        }

        with patch.object(client, "_get", return_value=mock_response):
            with pytest.raises(FieldNotFoundError) as exc_info:
                client.fetch_master()

        assert "events" in str(exc_info.value)
        assert "gameweeks" in str(exc_info.value)
