"""Tests for fuzzy keyword matching."""

import pytest

from mcp_sync.config.models import ClientDefinitions, MCPClientConfig
from mcp_sync.fuzzy_match import FuzzyClientMatcher, resolve_client_by_keyword


class TestFuzzyClientMatcher:
    """Tests for FuzzyClientMatcher class."""

    @pytest.fixture
    def matcher(self):
        """Create a matcher with default keywords."""
        return FuzzyClientMatcher()

    @pytest.fixture
    def matcher_with_definitions(self):
        """Create a matcher with client definitions."""
        definitions = ClientDefinitions(
            clients={
                "claude-code": MCPClientConfig(
                    name="Claude Code",
                    description="Claude CLI",
                ),
                "vscode": MCPClientConfig(
                    name="VS Code",
                    description="Visual Studio Code",
                ),
            }
        )
        return FuzzyClientMatcher(definitions)

    def test_exact_match_client_id(self, matcher):
        """Test exact match on client ID."""
        client_id, score = matcher.find_client("codex")
        assert client_id == "codex"
        assert score == 100

    def test_exact_match_keyword(self, matcher):
        """Test exact match on keyword."""
        client_id, score = matcher.find_client("claude")
        assert client_id == "claude-code"
        assert score == 100

    def test_fuzzy_match(self, matcher):
        """Test fuzzy matching - accept any reasonable match."""
        client_id, score = matcher.find_client("claud")  # Typo
        # Should match claude-code with decent score
        assert client_id is not None
        assert score > 0

    def test_case_insensitive(self, matcher):
        """Test case-insensitive matching."""
        client_id, score = matcher.find_client("CLAUDE")
        assert client_id == "claude-code"
        assert score == 100

    def test_no_match(self, matcher):
        """Test no match found - very different query."""
        client_id, score = matcher.find_client("xyznonexistent12345")
        # Should not find anything for completely different string
        assert client_id is None or score < 60

    def test_empty_query(self, matcher):
        """Test empty query."""
        client_id, score = matcher.find_client("")
        assert client_id is None
        assert score == 0

    def test_vscode_keywords(self, matcher):
        """Test VS Code keyword variations."""
        for keyword in ["vscode", "vs code", "vs-code", "code"]:
            client_id, score = matcher.find_client(keyword)
            assert client_id == "vscode-user", f"Failed for keyword: {keyword}"
            assert score == 100

    def test_cursor_keywords(self, matcher):
        """Test Cursor keyword variations."""
        for keyword in ["cursor", "cursor ide"]:
            client_id, score = matcher.find_client(keyword)
            assert client_id == "cursor"
            assert score == 100

    def test_find_multiple_clients(self, matcher):
        """Test finding multiple matching clients."""
        results = matcher.find_clients("code", limit=5)

        # Should return some results for "code"
        assert len(results) > 0
        # All results should have valid client IDs
        for client_id, _keyword, score in results:
            assert client_id is not None
            assert score > 0

    def test_find_clients_with_threshold(self, matcher):
        """Test find_clients with threshold."""
        results = matcher.find_clients("xyz", threshold=90)
        # No high-confidence matches for "xyz"
        assert len(results) == 0

    def test_get_keywords(self, matcher):
        """Test getting keywords for a client."""
        keywords = matcher.get_keywords("claude-code")
        assert "claude" in keywords
        assert "claude-code" in keywords
        assert "anthropic" in keywords

    def test_definitions_add_keywords(self, matcher_with_definitions):
        """Test that client definitions add keywords."""
        # The name variations should be added as keywords
        keywords = matcher_with_definitions.get_keywords("claude-code")
        assert "claude code" in keywords  # Name with space
        assert "claude-code" in keywords  # Name with hyphen


class TestResolveClientByKeyword:
    """Tests for resolve_client_by_keyword function."""

    @pytest.fixture
    def definitions(self):
        """Create client definitions."""
        return ClientDefinitions(
            clients={
                "claude-code": MCPClientConfig(name="Claude Code"),
                "vscode": MCPClientConfig(name="VS Code"),
            }
        )

    def test_resolve_exact_match(self, definitions):
        """Test resolving exact match."""
        result = resolve_client_by_keyword("claude", definitions)
        assert result == "claude-code"

    def test_resolve_fuzzy_match(self, definitions):
        """Test resolving fuzzy match - should find something."""
        result = resolve_client_by_keyword("claud", definitions)
        # Should find claude-code even with typo
        assert result is not None

    def test_resolve_no_match(self, definitions):
        """Test resolving no match for completely different string."""
        result = resolve_client_by_keyword("xyznonexistent12345", definitions)
        assert result is None

    def test_resolve_with_threshold(self, definitions):
        """Test resolving with custom threshold."""
        # With high threshold, fuzzy match might fail
        result = resolve_client_by_keyword("claud", definitions, threshold=95)
        # Result depends on fuzzy score, just check it doesn't crash
        assert result is None or result == "claude-code"
