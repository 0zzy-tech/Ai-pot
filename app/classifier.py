"""
Request risk classification engine.
Runs synchronously (no I/O) — fast enough to call inline without create_task.
Returns (category, risk_level, flagged_patterns).
"""

import re
from typing import Optional

# ── Known legitimate AI-tool paths ───────────────────────────────────────────
KNOWN_PATHS = {
    # ── Ollama ──────────────────────────────────────────────────────────────
    "/",
    "/api/tags", "/api/generate", "/api/chat", "/api/pull",
    "/api/push", "/api/delete", "/api/embeddings", "/api/show",
    "/api/ps", "/api/copy", "/api/blobs",

    # ── OpenAI-compatible (Ollama, LocalAI, vLLM, LM Studio…) ───────────────
    "/v1/models", "/v1/chat/completions", "/v1/completions", "/v1/embeddings",
    "/v1/audio/transcriptions", "/v1/audio/translations", "/v1/audio/speech",
    "/v1/images/generations", "/v1/images/edits", "/v1/images/variations",

    # ── Anthropic Claude ─────────────────────────────────────────────────────
    "/v1/messages", "/v1/complete",

    # ── Hugging Face TGI ─────────────────────────────────────────────────────
    "/health", "/info", "/metrics",
    "/generate", "/generate_stream",
    "/tokenize", "/decode",

    # ── llama.cpp server ─────────────────────────────────────────────────────
    "/completion", "/embedding", "/detokenize",
    "/slots", "/props", "/infill",

    # ── Text Generation WebUI (oobabooga) ────────────────────────────────────
    "/api/v1/model", "/api/v1/generate", "/api/v1/chat",
    "/api/v1/token-count", "/api/v1/stop-stream", "/api/v1/info",

    # ── Cohere ───────────────────────────────────────────────────────────────
    "/v1/chat", "/v1/generate", "/v1/embed",
    "/v1/rerank", "/v1/classify", "/v1/tokenize", "/v1/detokenize",

    # ── Mistral AI ────────────────────────────────────────────────────────────
    "/v1/fim/completions", "/v1/agents", "/v1/agents/completions",

    # ── Google Gemini / Vertex AI (prefixes handled via startswith below) ────
    # (dynamic paths like /v1beta/models/{model}:generateContent)

    # ── Stable Diffusion WebUI ────────────────────────────────────────────────
    "/sdapi/v1/sd-models", "/sdapi/v1/sd-vae", "/sdapi/v1/samplers",
    "/sdapi/v1/schedulers", "/sdapi/v1/upscalers", "/sdapi/v1/loras",
    "/sdapi/v1/options", "/sdapi/v1/memory", "/sdapi/v1/progress",
    "/sdapi/v1/txt2img", "/sdapi/v1/img2img",
    "/sdapi/v1/interrogate", "/sdapi/v1/interrupt", "/sdapi/v1/skip",
    "/info",

    # ── ComfyUI ───────────────────────────────────────────────────────────────
    "/system_stats", "/object_info", "/queue",
    "/prompt", "/interrupt", "/free", "/view",
    "/history",

    # ── LocalAI extensions ────────────────────────────────────────────────────
    "/readyz", "/healthz", "/tts",
    "/v1/backends", "/v1/backend/monitor", "/v1/backend/shutdown",
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

HIGH_RISK_PATHS = {
    # Ollama
    "/api/pull", "/api/push", "/api/delete",
    # SD WebUI — model loading & interruption
    "/sdapi/v1/interrupt",
}

# ── Dynamic path prefixes that are considered known (bypass "scanning" default)
KNOWN_PATH_PREFIXES = (
    "/api/blobs/",
    "/history/",
    "/object_info/",
    "/v1beta/models/",
    "/v1/models/",
    "/sdapi/v1/",
)

# ── Category mapping from path ────────────────────────────────────────────────
PATH_CATEGORY = {
    # ── Ollama ──────────────────────────────────────────────────────────────
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
    "/":                       "enumeration",

    # ── OpenAI-compatible ────────────────────────────────────────────────────
    "/v1/models":              "enumeration",
    "/v1/chat/completions":    "openai_compat",
    "/v1/completions":         "openai_compat",
    "/v1/embeddings":          "embeddings",

    # ── Anthropic Claude ─────────────────────────────────────────────────────
    "/v1/messages":            "anthropic",
    "/v1/complete":            "anthropic",

    # ── HuggingFace TGI ──────────────────────────────────────────────────────
    "/generate":               "inference",
    "/generate_stream":        "inference",
    "/info":                   "enumeration",
    "/health":                 "enumeration",
    "/healthz":                "enumeration",
    "/readyz":                 "enumeration",
    "/metrics":                "enumeration",
    "/tokenize":               "model_info",
    "/decode":                 "model_info",
    "/detokenize":             "model_info",

    # ── llama.cpp ────────────────────────────────────────────────────────────
    "/completion":             "inference",
    "/embedding":              "embeddings",
    "/slots":                  "enumeration",
    "/props":                  "enumeration",
    "/infill":                 "code_completion",

    # ── Text Generation WebUI ────────────────────────────────────────────────
    "/api/v1/generate":        "inference",
    "/api/v1/chat":            "inference",
    "/api/v1/model":           "enumeration",
    "/api/v1/token-count":     "model_info",
    "/api/v1/stop-stream":     "model_management",
    "/api/v1/info":            "enumeration",

    # ── Cohere ───────────────────────────────────────────────────────────────
    "/v1/chat":                "inference",
    "/v1/generate":            "inference",
    "/v1/embed":               "embeddings",
    "/v1/rerank":              "rerank",
    "/v1/classify":            "inference",
    "/v1/tokenize":            "model_info",
    "/v1/detokenize":          "model_info",

    # ── Mistral AI ────────────────────────────────────────────────────────────
    "/v1/fim/completions":     "code_completion",
    "/v1/agents":              "enumeration",
    "/v1/agents/completions":  "inference",

    # ── Stable Diffusion WebUI ────────────────────────────────────────────────
    "/sdapi/v1/txt2img":       "image_generation",
    "/sdapi/v1/img2img":       "image_generation",
    "/sdapi/v1/interrogate":   "inference",
    "/sdapi/v1/sd-models":     "enumeration",
    "/sdapi/v1/sd-vae":        "enumeration",
    "/sdapi/v1/samplers":      "enumeration",
    "/sdapi/v1/schedulers":    "enumeration",
    "/sdapi/v1/upscalers":     "enumeration",
    "/sdapi/v1/loras":         "enumeration",
    "/sdapi/v1/options":       "model_management",
    "/sdapi/v1/memory":        "enumeration",
    "/sdapi/v1/progress":      "enumeration",
    "/sdapi/v1/interrupt":     "model_management",
    "/sdapi/v1/skip":          "model_management",

    # ── ComfyUI ───────────────────────────────────────────────────────────────
    "/system_stats":           "enumeration",
    "/object_info":            "enumeration",
    "/queue":                  "enumeration",
    "/history":                "enumeration",
    "/prompt":                 "image_generation",
    "/interrupt":              "model_management",
    "/free":                   "model_management",
    "/view":                   "enumeration",

    # ── LocalAI / OpenAI extensions ───────────────────────────────────────────
    "/v1/audio/transcriptions":"audio_transcription",
    "/v1/audio/translations":  "audio_transcription",
    "/v1/audio/speech":        "audio_transcription",
    "/tts":                    "audio_transcription",
    "/v1/images/generations":  "image_generation",
    "/v1/images/edits":        "image_generation",
    "/v1/images/variations":   "image_generation",
    "/v1/backends":            "enumeration",
    "/v1/backend/monitor":     "enumeration",
    "/v1/backend/shutdown":    "model_management",

    # ── Gemini / Vertex AI (dynamic — prefix-matched in classify_request) ────
    # Handled via KNOWN_PATH_PREFIXES + category inference below
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
    category = PATH_CATEGORY.get(path)
    if category is None:
        # Check dynamic prefixes (e.g. /v1beta/models/..., /history/uuid)
        if any(path.startswith(p) for p in KNOWN_PATH_PREFIXES):
            # Infer category from prefix
            if "/models/" in path and ("generateContent" in path or "streamGenerate" in path):
                category = "inference"
            elif "/models/" in path and "embed" in path.lower():
                category = "embeddings"
            elif "/models/" in path and "countTokens" in path:
                category = "model_info"
            elif "/models/" in path:
                category = "enumeration"
            elif path.startswith("/history/"):
                category = "enumeration"
            elif path.startswith("/object_info/"):
                category = "enumeration"
            elif path.startswith("/sdapi/v1/"):
                category = "image_generation"
            else:
                category = "enumeration"
        else:
            category = "scanning"

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
    # Embeddings / rerank / image-gen are inherently MEDIUM (data exfil risk)
    if category in ("embeddings", "rerank", "image_generation", "audio_transcription"):
        return category, "MEDIUM", flagged

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
    if (path not in KNOWN_PATHS
            and not any(path.startswith(p) for p in KNOWN_PATH_PREFIXES)):
        return "scanning", "MEDIUM", flagged

    return category, "LOW", flagged


def _extract_model(body_json: dict) -> Optional[str]:
    return body_json.get("model") or body_json.get("name")


# Known models that shouldn't trigger MEDIUM risk
_KNOWN_MODEL_PREFIXES = (
    # Ollama / llama.cpp families
    "llama", "mistral", "codellama", "phi", "gemma", "qwen",
    "deepseek", "vicuna", "orca", "wizard", "falcon", "mpt",
    "stablelm", "solar", "neural", "openchat", "tinyllama",
    "dolphin", "hermes", "nous", "mixtral", "yi", "zephyr",
    # Anthropic
    "claude",
    # Google
    "gemini", "palm", "bison", "gecko", "embedding-001", "text-embedding",
    # Cohere
    "command", "embed-english", "embed-multilingual", "rerank-",
    # Mistral AI
    "codestral", "open-mistral", "open-mixtral",
    # Stable Diffusion / image
    "stable-diffusion", "sdxl", "dreamshaper", "realistic",
    "v1-5", "dall-e",
    # Audio / Whisper
    "whisper", "tts-1", "bark",
    # Hugging Face / generic
    "gpt", "bert", "roberta", "t5", "bart", "flan",
)


def _is_known_model(model: str) -> bool:
    model_lower = model.lower()
    return any(model_lower.startswith(p) for p in _KNOWN_MODEL_PREFIXES)
