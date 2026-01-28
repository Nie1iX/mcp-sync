"""Fuzzy keyword matching for MCP client identification."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from thefuzz import fuzz, process

if TYPE_CHECKING:
    from .config.models import ClientDefinitions

logger = logging.getLogger(__name__)


class FuzzyClientMatcher:
    """Fuzzy matcher for finding clients by keywords."""

    # Default keywords for built-in clients
    DEFAULT_KEYWORDS: dict[str, list[str]] = {
        "codex": ["codex", "openai", "codex cli"],
        "claude-code": ["claude", "claude-code", "claude code", "anthropic"],
        "claude-desktop": ["claude-desktop", "claude desktop", "anthropic desktop"],
        "cursor": ["cursor", "cursor ide"],
        "gemini-cli": ["gemini", "gemini cli", "google", "gcloud"],
        "copilot-cli": ["copilot", "copilot cli", "github", "gh"],
        "vscode-user": ["vscode", "vs code", "vs-code", "code", "visual studio code"],
        "cline": ["cline"],
        "roo": ["roo", "roo-cline"],
        "kilocode-cli": ["kilocode", "kilo", "kilocode cli"],
        "continue": ["continue"],
    }

    def __init__(self, client_definitions: ClientDefinitions | None = None):
        self.logger = logging.getLogger(__name__)
        self._client_definitions = client_definitions
        self._keywords: dict[str, list[str]] = {}
        self._build_keyword_index()

    def _build_keyword_index(self):
        """Build the keyword index from client definitions."""
        self._keywords = {}

        # Start with default keywords
        for client_id, keywords in self.DEFAULT_KEYWORDS.items():
            self._keywords[client_id] = list(keywords)

        # Add keywords from client definitions if available
        if self._client_definitions:
            for client_id, config in self._client_definitions.clients.items():
                # Add the client ID itself as a keyword
                if client_id not in self._keywords:
                    self._keywords[client_id] = []

                # Add name variations
                name = config.name.lower()
                if name not in self._keywords[client_id]:
                    self._keywords[client_id].append(name)

                # Add name without spaces
                name_no_spaces = name.replace(" ", "")
                if name_no_spaces not in self._keywords[client_id]:
                    self._keywords[client_id].append(name_no_spaces)

                # Add name with hyphens instead of spaces
                name_hyphens = name.replace(" ", "-")
                if name_hyphens not in self._keywords[client_id]:
                    self._keywords[client_id].append(name_hyphens)

    def find_client(self, query: str, threshold: int = 60) -> tuple[str | None, int]:
        """Find a client by fuzzy matching the query against keywords.

        Args:
            query: The search query (e.g., "claude", "vscode")
            threshold: Minimum match score (0-100) to consider a match

        Returns:
            Tuple of (client_id, score) or (None, 0) if no match
        """
        if not query:
            return None, 0

        query = query.lower().strip()

        # Exact match on client ID first
        if query in self._keywords:
            return query, 100

        # Build a flat list of all keywords with their client IDs
        all_keywords: list[tuple[str, str]] = []
        for client_id, keywords in self._keywords.items():
            for keyword in keywords:
                all_keywords.append((keyword, client_id))

        # Try exact match on keywords first
        for keyword, client_id in all_keywords:
            if query == keyword.lower():
                return client_id, 100

        # Fuzzy match
        keyword_list = [k for k, _ in all_keywords]
        matches = process.extract(query, keyword_list, scorer=fuzz.WRatio, limit=5)

        if not matches:
            return None, 0

        # Find the best match that meets threshold
        best_score = 0
        best_client = None

        for match in matches:
            # Handle both (keyword, score) and (keyword, score, index) formats
            if len(match) == 2:
                matched_keyword, score = match
            else:
                matched_keyword, score, *_ = match

            if score >= threshold and score > best_score:
                # Find client ID for this keyword
                for keyword, client_id in all_keywords:
                    if keyword == matched_keyword:
                        best_score = score
                        best_client = client_id
                        break

        return best_client, best_score

    def find_clients(
        self, query: str, limit: int = 5, threshold: int = 50
    ) -> list[tuple[str, str, int]]:
        """Find multiple matching clients sorted by relevance.

        Args:
            query: The search query
            limit: Maximum number of results
            threshold: Minimum match score

        Returns:
            List of tuples (client_id, matched_keyword, score)
        """
        if not query:
            return []

        query = query.lower().strip()
        all_keywords: list[tuple[str, str]] = []
        for client_id, keywords in self._keywords.items():
            for keyword in keywords:
                all_keywords.append((keyword, client_id))

        keyword_list = [k for k, _ in all_keywords]
        matches = process.extract(query, keyword_list, scorer=fuzz.WRatio, limit=limit * 2)

        results = []
        seen_clients: set[str] = set()

        for match in matches:
            # Handle both (keyword, score) and (keyword, score, index) formats
            if len(match) == 2:
                matched_keyword, score = match
            else:
                matched_keyword, score, *_ = match

            if score < threshold:
                continue

            # Find client ID for this keyword
            for keyword, client_id in all_keywords:
                if keyword == matched_keyword and client_id not in seen_clients:
                    results.append((client_id, matched_keyword, score))
                    seen_clients.add(client_id)
                    break

            if len(results) >= limit:
                break

        return results

    def get_keywords(self, client_id: str) -> list[str]:
        """Get all keywords for a specific client.

        Args:
            client_id: The client identifier

        Returns:
            List of keywords for the client
        """
        return self._keywords.get(client_id, [])


def resolve_client_by_keyword(
    query: str,
    client_definitions: ClientDefinitions,
    threshold: int = 60,
) -> str | None:
    """Resolve a client ID from a keyword query.

    This is the main entry point for fuzzy client matching.

    Args:
        query: The search query (e.g., "claude", "vscode")
        client_definitions: Client definitions to search against
        threshold: Minimum match score

    Returns:
        Client ID if found, None otherwise
    """
    matcher = FuzzyClientMatcher(client_definitions)
    client_id, score = matcher.find_client(query, threshold)

    if client_id:
        logger.debug(f"Matched '{query}' to '{client_id}' with score {score}")
    else:
        logger.debug(f"No match found for '{query}'")

    return client_id
