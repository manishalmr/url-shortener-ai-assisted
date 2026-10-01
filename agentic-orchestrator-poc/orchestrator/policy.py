"""
Policy guardrails for security/compliance/change control.

Requirement being satisfied: "embed policy guardrails for security,
compliance, and change control." PoC scope: a small set of regex-based
checks applied to generated code artifacts before they're allowed to pass
an exit gate - enough to demonstrate the guardrail *mechanism* in the
orchestrator, not a production-grade SAST engine (bandit/semgrep would be
the real thing to wire in - see docs/limitations.md).
"""
from __future__ import annotations

import re

_BANNED_PATTERNS = {
    r"\beval\s*\(": "use of eval() is banned by policy",
    r"\bexec\s*\(": "use of exec() is banned by policy",
    r"os\.system\s*\(": "shelling out via os.system() is banned by policy",
    r"password\s*=\s*['\"][^'\"]+['\"]": "hardcoded password literal detected",
    r"api[_-]?key\s*=\s*['\"][^'\"]+['\"]": "hardcoded API key literal detected",
}


def scan_code_for_policy_violations(code: str) -> list[str]:
    """Returns a list of human-readable violation reasons; empty list = clean."""
    violations = []
    for pattern, reason in _BANNED_PATTERNS.items():
        if re.search(pattern, code, flags=re.IGNORECASE):
            violations.append(reason)
    return violations
