"""Typed error hierarchy for The Chronicler."""


class ChroniclerError(Exception):
    """Base error for all recoverable Chronicler failures."""


class LedgerError(ChroniclerError):
    """The EdgeRecord ledger could not be read."""


class OllamaError(ChroniclerError):
    """The local Ollama endpoint failed or returned unusable output."""


class UnsafePathError(ChroniclerError):
    """A proposed file path escapes the target repository root."""


class CommitError(ChroniclerError):
    """The local git commit/push step failed."""
