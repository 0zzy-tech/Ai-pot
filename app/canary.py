"""
Canary token module.

Generates a single session-stable fake API key at startup. This token is
embedded in certain fake responses (e.g., the /v1/models listing). If an
attacker copies the token and re-submits it in a request body, the classifier
detects it and flags the request as CRITICAL with pattern "canary_token_reuse".

A new token is generated on each server restart — acceptable for a honeypot.
"""

import secrets

_CANARY_TOKEN: str = "sk-pot-" + secrets.token_hex(8)


def get_canary_token() -> str:
    return _CANARY_TOKEN


def contains_canary(text: str) -> bool:
    return _CANARY_TOKEN in text
