"""
Custom detection rules — operator-defined regex patterns stored in SQLite.
Loaded into memory at startup and hot-reloaded after any CRUD operation.
match_custom_rules() is sync and safe to call from the classification hot-path.
"""

import logging
import re

logger = logging.getLogger(__name__)

# In-memory cache: list of (compiled_re, flag_name, risk_level)
_rules: list[tuple] = []


def reload_rules(rows: list[dict]) -> None:
    """Replace in-memory cache from a list of DB rows."""
    global _rules
    compiled = []
    for r in rows:
        if not r.get("enabled", True):
            continue
        try:
            compiled.append((
                re.compile(r["pattern"], re.IGNORECASE),
                r["flag_name"],
                r["risk_level"].upper(),
            ))
        except re.error as exc:
            logger.warning("Invalid custom rule %r: %s", r["pattern"], exc)
    _rules = compiled
    logger.info("Custom rules loaded — %d active", len(_rules))


def match_custom_rules(text: str) -> list[tuple[str, str]]:
    """
    Return list of (flag_name, risk_level) for every custom rule that matches text.
    Highest risk wins if called from classify_request.
    """
    hits: list[tuple[str, str]] = []
    for compiled_re, flag_name, risk_level in _rules:
        try:
            if compiled_re.search(text):
                hits.append((flag_name, risk_level))
        except Exception:
            pass
    return hits
