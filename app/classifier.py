"""
Request risk classification engine.
Runs synchronously (no I/O) — fast enough to call inline without create_task.
Returns (category, risk_level, flagged_patterns).
"""

import re
from typing import Optional

# ── Known legitimate Ollama/OpenAI paths ──────────────────────────────────────
KNOWN_PATHS = {
    "/",
    "/api/tags", "/api/generate", "/api/chat", "/api/pull",
    "/api/push", "/api/delete", "/api/embeddings", "/api/show",
    "/api/ps", "/api/copy", "/api/blobs",
    "/v1/models", "/v1/chat/completions", "/v1/completions", "/v1/embeddings",
}

# ── Scanner user-agents ───────────────────────────────────────────────────────
SCANNER_UA_PATTERNS = re.compile(
    r"nikto|sqlmap|nmap|masscan|zgrab|dirbuster|gobuster|nuclei|"
    r"metasploit|burpsuite|zap|wfuzz|ffuf|hydra|medusa|shodan",
    re.IGNORECASE,
)

# ── CRITICAL: jailbreak / prompt injection ────────────────────────────────────
JAILBREAK_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(all\s+)?previous\s+instructions?",
        r"ignore\s+your\s+instructions?",
        r"you\s+are\s+now\s+(?:a|an|the)\s+",
        r"\bact\s+as\s+(?:a|an|the)\s+",
        r"\bDAN\b",
        r"\bjailbreak\b",
        r"bypass\s+(?:your\s+)?(?:safety|filter|restriction|guideline|policy)",
        r"override\s+(?:your\s+)?system\s+prompt",
        r"forget\s+(?:all\s+)?(?:your\s+)?(?:previous\s+)?(?:instructions?|training)",
        r"pretend\s+(?:you\s+(?:have\s+no|are\s+not)|there\s+(?:are\s+no|is\s+no))",
        r"hypothetically[,\s]+if\s+you\s+(?:could|were\s+(?:a|an))",
        r"do\s+anything\s+now",
        r"\[INST\]|\[\/INST\]",       # llama instruction injection
        r"<\|(?:system|user|assistant)\|>",  # Phi/Zephyr token injection
        r"<<SYS>>|<</SYS>>",
    ]
]

# ── CRITICAL: code / command execution ───────────────────────────────────────
CODE_EXEC_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"__import__\s*\(",
        r"\beval\s*\(",
        r"\bexec\s*\(",
        r"os\.system\s*\(",
        r"subprocess\.(run|call|Popen|check_output)",
        r"shell\s*=\s*True",
        r"\brm\s+-rf\b",
        r"\bwget\s+https?://",
        r"\bcurl\s+https?://",
        r"/etc/passwd",
        r"/etc/shadow",
        r"\.\.\/\.\.\/",         # path traversal
        r"\bpowershell\b",
        r"\bcmd\.exe\b",
        r"net\s+user\s+",
    ]
]

# ── CRITICAL: SQL injection ───────────────────────────────────────────────────
SQL_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"'\s+OR\s+'",
        r"UNION\s+(?:ALL\s+)?SELECT",
        r"DROP\s+TABLE",
        r"INSERT\s+INTO\s+\w+\s+VALUES",
        r"--\s*$",                   # SQL comment terminator
        r";\s*SELECT\b",
    ]
]

# ── HIGH-risk path segments ───────────────────────────────────────────────────
HIGH_RISK_PATH_SEGMENTS = re.compile(
    r"admin|config|env|secret|key|token|password|passwd|credential|backup|\.git|wp-",
    re.IGNORECASE,
)

HIGH_RISK_PATHS = {"/api/pull", "/api/push", "/api/delete"}

# ── Category mapping from path ────────────────────────────────────────────────
PATH_CATEGORY = {
    "/api/generate":           "inference",
    "/api/chat":               "inference",
    "/api/pull":               "model_management",
    "/api/push":               "model_management",
    "/api/delete":             "model_management",
    "/api/copy":               "model_management",
    "/api/embeddings":         "embeddings",
    "/api/tags":               "enumeration",
    "/api/ps":                 "enumeration",
    "/api/show":               "model_info",
    "/api/blobs":              "model_management",
    "/v1/models":              "enumeration",
    "/v1/chat/completions":    "openai_compat",
    "/v1/completions":         "openai_compat",
    "/v1/embeddings":          "embeddings",
    "/":                       "enumeration",
}


def classify_request(
    method: str,
    path: str,
    headers: dict,
    body_text: str,
    body_json: dict,
    recent_count_60s: int = 0,
    recent_count_600s: int = 0,
) -> tuple[str, str, list[str]]:
    """
    Returns (category, risk_level, flagged_patterns).
    risk_level is one of: LOW, MEDIUM, HIGH, CRITICAL.
    """
    flagged: list[str] = []

    # ── Step 1: determine base category from path ─────────────────────────
    category = PATH_CATEGORY.get(path, "scanning")

    # ── Step 2: check CRITICAL patterns ───────────────────────────────────
    for pattern in JAILBREAK_PATTERNS:
        if pattern.search(body_text):
            flagged.append(f"jailbreak:{pattern.pattern[:40]}")

    for pattern in CODE_EXEC_PATTERNS:
        if pattern.search(body_text):
            flagged.append(f"code_exec:{pattern.pattern[:40]}")

    for pattern in SQL_INJECTION_PATTERNS:
        if pattern.search(body_text):
            flagged.append(f"sql_injection:{pattern.pattern[:40]}")

    if recent_count_60s >= 20:
        flagged.append(f"mass_scan:{recent_count_60s}_reqs_in_60s")

    if flagged:
        return "attack", "CRITICAL", flagged

    # ── Step 3: check HIGH patterns ────────────────────────────────────────
    ua = headers.get("user-agent", "")
    if SCANNER_UA_PATTERNS.search(ua):
        flagged.append(f"scanner_ua:{ua[:60]}")
        return category, "HIGH", flagged

    if path in HIGH_RISK_PATHS:
        flagged.append(f"high_risk_path:{path}")
        return category, "HIGH", flagged

    if HIGH_RISK_PATH_SEGMENTS.search(path):
        flagged.append(f"sensitive_path_segment:{path}")
        return category, "HIGH", flagged

    # ── Step 4: check MEDIUM patterns ─────────────────────────────────────
    if path in ("/api/embeddings", "/v1/embeddings"):
        return "embeddings", "MEDIUM", flagged

    if recent_count_600s >= 5:
        flagged.append(f"repeat_ip:{recent_count_600s}_reqs_in_10min")
        return category, "MEDIUM", flagged

    if len(body_text) > 5000:
        flagged.append(f"large_body:{len(body_text)}_bytes")
        return category, "MEDIUM", flagged

    # Check for unknown model name in request
    model = _extract_model(body_json)
    if model and not _is_known_model(model):
        flagged.append(f"unknown_model:{model[:40]}")
        return category, "MEDIUM", flagged

    # ── Step 5: unknown path (not in our known set) ───────────────────────
    if path not in KNOWN_PATHS and not path.startswith("/api/blobs/"):
        return "scanning", "MEDIUM", flagged

    return category, "LOW", flagged


def _extract_model(body_json: dict) -> Optional[str]:
    return body_json.get("model") or body_json.get("name")


# Known models that shouldn't trigger MEDIUM risk
_KNOWN_MODEL_PREFIXES = (
    "llama", "mistral", "codellama", "phi", "gemma", "qwen",
    "deepseek", "vicuna", "orca", "wizard", "falcon", "mpt",
    "stablelm", "solar", "neural", "openchat", "tinyllama",
    "dolphin", "hermes", "nous", "mixtral", "yi", "zephyr",
)


def _is_known_model(model: str) -> bool:
    model_lower = model.lower()
    return any(model_lower.startswith(p) for p in _KNOWN_MODEL_PREFIXES)
