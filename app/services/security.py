"""
Security & Prompt-Injection Defender
Protects Veritas AI from direct and indirect prompt-injection attacks, system prompt overrides,
jailbreaks, and adversarial input manipulation.
"""

import re
from typing import Tuple, List, Dict, Any

# Known prompt-injection and jailbreak trigger patterns
PROMPT_INJECTION_PATTERNS = [
    # 1. System directive overrides
    (r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions\b", "directive_override", 0.95),
    (r"\bdisregard\s+(all\s+)?(previous|prior|above)\s+directives\b", "directive_override", 0.95),
    (r"\bforget\s+(what\s+you\s+were\s+told|all\s+previous\s+rules)\b", "directive_override", 0.90),
    (r"\boverride\s+(system|core|developer)\s+instructions\b", "directive_override", 0.95),
    (r"\breset\s+prompt\b", "directive_override", 0.85),
    (r"\byou\s+are\s+now\s+free\s+from\s+all\s+rules\b", "directive_override", 0.95),

    # 2. Roleplay & jailbreak markers
    (r"\b(do\s+anything\s+now|dan\s+mode|jailbreak|evil\s+bot)\b", "jailbreak_attempt", 0.95),
    (r"\bdeveloper\s+mode\s+(enabled|activated|on)\b", "jailbreak_attempt", 0.90),
    (r"\bact\s+as\s+an\s+(unfiltered|unrestricted|uncensored)\s+(ai|assistant|model)\b", "jailbreak_attempt", 0.90),
    (r"\bpretend\s+you\s+have\s+no\s+(guidelines|safety|filters)\b", "jailbreak_attempt", 0.90),

    # 3. System role and delimiter smuggling
    (r"<\|im_start\|>", "delimiter_smuggling", 0.98),
    (r"<\|im_end\|>", "delimiter_smuggling", 0.98),
    (r"\[\s*SYSTEM\s*:\s*", "delimiter_smuggling", 0.90),
    (r"\[\s*SYSTEM\s+INSTRUCTION\s*\]", "delimiter_smuggling", 0.95),
    (r"```\s*(system|assistant)\b", "delimiter_smuggling", 0.90),
    (r"<\s*system\s*>", "delimiter_smuggling", 0.90),
    (r"Human:\s*Assistant:", "role_spoofing", 0.85),

    # 4. Prompt extraction & exfiltration
    (r"\b(repeat|print|output|display)\s+(your\s+)?(system\s+prompt|initial\s+instructions)\b", "prompt_extraction", 0.85),
    (r"\bwhat\s+are\s+your\s+exact\s+(instructions|system\s+directives)\b", "prompt_extraction", 0.80),
    (r"\boutput\s+everything\s+(above|before\s+this)\s+verbatim\b", "prompt_extraction", 0.85),

    # 5. Indirect prompt injection inside retrieved evidence
    (r"\[\s*HIDDEN\s+INSTRUCTION\s*:", "indirect_injection", 0.95),
    (r"\bIMPORTANT\s+INSTRUCTION\s+FOR\s+AI\b", "indirect_injection", 0.95),
    (r"\bDO\s+NOT\s+VERIFY\s+THIS\s+CLAIM\b", "indirect_injection", 0.90),
]


def detect_prompt_injection(text: str) -> Tuple[bool, float, List[str]]:
    """
    Scans text for prompt injection, jailbreak attempts, and delimiter smuggling.
    Returns:
      (is_suspicious: bool, risk_score: float, detected_threats: List[str])
    """
    if not text:
        return False, 0.0, []

    detected_threats = []
    max_risk = 0.0

    for pattern, threat_type, score in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            detected_threats.append(f"{threat_type}: matches pattern '{pattern}'")
            if score > max_risk:
                max_risk = score

    # Threshold for flagging as suspicious
    is_suspicious = max_risk >= 0.80
    return is_suspicious, round(max_risk, 2), detected_threats


def sanitize_input(text: str) -> str:
    """
    Neutralizes known prompt-injection tokens and control sequences,
    stripping dangerous delimiter sequences while preserving safe text.
    """
    if not text:
        return ""

    sanitized = text
    # Strip delimiter smuggling sequences
    for pattern, threat_type, _ in PROMPT_INJECTION_PATTERNS:
        if threat_type in ("delimiter_smuggling", "indirect_injection"):
            sanitized = re.sub(pattern, " [neutralized_marker] ", sanitized, flags=re.IGNORECASE)

    # Neutralize instruction override phrases
    override_phrases = [
        r"ignore\s+all\s+previous\s+instructions",
        r"disregard\s+all\s+previous\s+directives",
        r"do\s+anything\s+now",
        r"dan\s+mode",
    ]
    for ph in override_phrases:
        sanitized = re.sub(ph, "[neutralized_directive]", sanitized, flags=re.IGNORECASE)

    return sanitized.strip()


def wrap_untrusted_input(text: str, tag: str = "user_input") -> str:
    """
    Wraps untrusted user content in structured XML-style delimiters
    to prevent the LLM from executing input text as system commands.
    """
    safe_text = sanitize_input(text)
    return f"<{tag}>\n{safe_text}\n</{tag}>"


def sanitize_evidence_passage(passage: str) -> str:
    """
    Strips potential indirect prompt injection embedded inside third-party
    documents or untrusted web pages before the passage is fed to synthesis or verification.
    """
    if not passage:
        return ""
    return sanitize_input(passage)


def validate_query_safety(query: str) -> Dict[str, Any]:
    """
    Performs full safety validation on an incoming user query.
    Returns a dict with safety determination, risk score, threats, and safe query.
    """
    is_suspicious, risk_score, threats = detect_prompt_injection(query)
    safe_query = sanitize_input(query) if is_suspicious else query

    return {
        "is_safe": not is_suspicious,
        "risk_score": risk_score,
        "threats": threats,
        "safe_query": safe_query,
        "action_taken": "sanitized" if is_suspicious else "passed"
    }
