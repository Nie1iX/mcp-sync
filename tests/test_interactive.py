"""Tests for interactive wizard."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_sync.interactive import InteractiveWizard


class TestInteractiveWizard:
    """Tests for InteractiveWizard class."""

    @pytest.fixture
    def wizard(self):
        """Create an InteractiveWizard with mocked dependencies."""
        with (
            patch("mcp_sync.interactive.get_settings") as mock_settings,
            patch("mcp_sync.interactive.ClientRepository") as mock_repo,
            patch("mcp_sync.interactive.FuzzyClientMatcher") as mock_matcher,
            patch("mcp_sync.interactive.DirectSyncEngine") as mock_engine,
        ):
            mock_settings.return_value = MagicMock()
            mock_repo.return_value = MagicMock()
            mock_matcher.return_value = MagicMock()
            mock_engine.return_value = MagicMock()

            wizard = InteractiveWizard()
            yield wizard

    def test_init(self, wizard):
        """Test wizard initialization."""
        assert wizard.settings is not None
        assert wizard.repository is not None
        assert wizard.matcher is not None
        assert wizard.direct_engine is not None

    @patch("mcp_sync.interactive.Prompt")
    @patch("mcp_sync.interactive.console")
    def test_run_exit(self, mock_console, mock_prompt, wizard):
        """Test running wizard and exiting."""
        mock_prompt.ask.return_value = "5"  # Exit option

        wizard.run()

        # Should print goodbye message
        assert mock_console.print.called

    @patch("mcp_sync.interactive.Prompt")
    @patch("mcp_sync.interactive.Confirm")
    @patch("mcp_sync.interactive.console")
    def test_direct_sync_flow_no_clients(self, mock_console, mock_confirm, mock_prompt, wizard):
        """Test direct sync flow when no clients found."""
        wizard.repository.discover_clients.return_value = []
        mock_prompt.ask.side_effect = ["1", "5"]  # Direct sync, then exit

        wizard.run()

        # Should show "no clients found" message
        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("no mcp clients" in c.lower() for c in calls)

    @patch("mcp_sync.interactive.Prompt")
    @patch("mcp_sync.interactive.Confirm")
    @patch("mcp_sync.interactive.console")
    def test_direct_sync_flow_with_clients(self, mock_console, mock_confirm, mock_prompt, wizard):
        """Test direct sync flow with discovered clients."""
        wizard.repository.discover_clients.return_value = [
            {"name": "vscode", "path": "/path/to/vscode", "client_name": "VS Code"},
            {"name": "cursor", "path": "/path/to/cursor", "client_name": "Cursor"},
        ]

        # Need enough side_effects for all Prompt.ask calls
        # Main menu, source choice, target choice, main menu again, exit
        mock_prompt.ask.side_effect = ["1", "1", "1", "5"]
        mock_confirm.ask.return_value = False  # Don't confirm sync

        wizard.direct_engine.sync_by_path.return_value = {
            "success": True,
            "total_changes": 1,
        }

        wizard.run()

        # Should have discovered clients
        assert wizard.repository.discover_clients.called

    @patch("mcp_sync.interactive.Prompt")
    @patch("mcp_sync.interactive.console")
    def test_view_status_flow(self, mock_console, mock_prompt, wizard):
        """Test view status flow."""
        # Mock SyncEngine inside the method
        with patch("mcp_sync.interactive.SyncEngine") as mock_sync_engine_class:
            mock_instance = MagicMock()
            mock_instance.get_server_status.return_value = {
                "global_servers": {"server1": {"command": "npx"}},
                "project_servers": {},
                "location_servers": {},
            }
            mock_sync_engine_class.return_value = mock_instance

            # Create a generator that yields values indefinitely
            def side_effect_generator():
                values = ["4", "5"]  # View status, then exit
                yield from values
                # After exhausting values, keep returning "5" (exit)
                while True:
                    yield "5"

            mock_prompt.ask.side_effect = side_effect_generator()

            wizard.run()

            # SyncEngine should have been created
            assert mock_sync_engine_class.called

    @patch("mcp_sync.interactive.Prompt")
    @patch("mcp_sync.interactive.console")
    def test_manage_servers_flow(self, mock_console, mock_prompt, wizard):
        """Test manage servers flow."""
        with patch("mcp_sync.interactive.SyncEngine") as mock_sync_engine_class:
            mock_instance = MagicMock()
            mock_instance.get_server_status.return_value = {
                "global_servers": {},
                "project_servers": {},
                "location_servers": {},
            }
            mock_sync_engine_class.return_value = mock_instance

            # Manage servers (3), back (3), exit (5)
            mock_prompt.ask.side_effect = ["3", "3", "5"]

            wizard.run()

            # Should show manage servers menu
            calls = [str(call) for call in mock_console.print.call_args_list]
            assert any("manage" in c.lower() for c in calls)

    @patch("mcp_sync.interactive.Prompt")
    @patch("mcp_sync.interactive.Confirm")
    @patch("mcp_sync.interactive.console")
    def test_add_server_flow(self, mock_console, mock_confirm, mock_prompt, wizard):
        """Test add server flow."""
        with patch("mcp_sync.interactive.SyncEngine") as mock_sync_engine_class:
            mock_instance = MagicMock()
            mock_instance.get_server_status.return_value = {
                "global_servers": {},
                "project_servers": {},
                "location_servers": {},
            }
            mock_sync_engine_class.return_value = mock_instance

            # Manage servers, add server, enter details, back, exit
            # Need to account for all Prompt.ask calls including nested ones
            def prompt_generator():
                values = [
                    "3",  # Manage servers
                    "1",  # Add server
                    "test-server",  # Server name
                    "global",  # Scope
                    "npx",  # Command
                    "",  # Args (empty)
                    "",  # Env (empty)
                    "5",  # Exit
                ]
                yield from values
                while True:
                    yield "5"  # Keep exiting

            mock_prompt.ask.side_effect = prompt_generator()
            # Confirm for overwrite check and any other confirms
            mock_confirm.ask.side_effect = [False, True]  # Overwrite? No. Others yes.

            wizard.run()

            # Should have called add_server_to_global
            assert mock_instance.add_server_to_global.called

    @patch("mcp_sync.interactive.Prompt")
    @patch("mcp_sync.interactive.Confirm")
    @patch("mcp_sync.interactive.console")
    def test_remove_server_flow(self, mock_console, mock_confirm, mock_prompt, wizard):
        """Test remove server flow."""
        with patch("mcp_sync.interactive.SyncEngine") as mock_sync_engine_class:
            mock_instance = MagicMock()
            mock_instance.get_server_status.return_value = {
                "global_servers": {"test-server": {"command": "npx"}},
                "project_servers": {},
                "location_servers": {},
            }
            mock_instance.remove_server_from_global.return_value = True
            mock_sync_engine_class.return_value = mock_instance

            # Manage servers, remove server, enter name, confirm, back, exit
            def prompt_generator():
                values = [
                    "3",  # Manage servers
                    "2",  # Remove server
                    "test-server",  # Server name
                    "5",  # Exit
                ]
                yield from values
                while True:
                    yield "5"  # Keep exiting

            mock_prompt.ask.side_effect = prompt_generator()
            # Confirm for remove confirmation
            mock_confirm.ask.return_value = True

            wizard.run()

            # Should have called remove_server_from_global
            mock_instance.remove_server_from_global.assert_called_with("test-server")

    @patch("mcp_sync.interactive.Prompt")
    @patch("mcp_sync.interactive.Confirm")
    @patch("mcp_sync.interactive.console")
    def test_full_sync_flow(self, mock_console, mock_confirm, mock_prompt, wizard):
        """Test full sync flow."""
        with patch("mcp_sync.interactive.SyncEngine") as mock_sync_engine_class:
            mock_instance = MagicMock()
            mock_instance.sync_all.return_value = MagicMock(
                updated_locations=["location1"],
                conflicts=[],
            )
            mock_sync_engine_class.return_value = mock_instance

            # Full sync (2), exit (5)
            mock_prompt.ask.side_effect = ["2", "5"]
            mock_confirm.ask.return_value = True

            wizard.run()

            # Should have called sync_all
            assert mock_instance.sync_all.called
