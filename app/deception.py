"""
Deception token tracking.

When DECEPTION_ENABLED=true, a unique per-session URL is shown in the Intelligence
panel. If an attacker follows that URL the callback is logged as a CRITICAL event
with flag "deception_callback".

Tokens are also generated per-IP on demand for the /api/tags response header so
automated scanners that replay headers can be tracked individually.
"""

import logging
import secrets

logger = logging.getLogger(__name__)

# token -> original_ip (memory only — tokens reset on restart, that's fine)
_tokens: dict[str, str] = {}

# The one session-level token shown in the dashboard Intelligence panel
_session_token: str = secrets.token_urlsafe(20)


def get_session_token() -> str:
    return _session_token


def generate_token(ip: str) -> str:
    """Create a unique tracking token for a given attacker IP."""
    token = secrets.token_urlsafe(16)
    _tokens[token] = ip
    return token


def lookup_token(token: str) -> str | None:
    """Return the original attacker IP for a token, or None if unknown."""
    return _tokens.get(token, "unknown")


def register_session_token() -> None:
    """Bind the session token to 'operator' so it shows up nicely if followed."""
    _tokens[_session_token] = "operator"
