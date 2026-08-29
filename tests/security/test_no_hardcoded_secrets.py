"""Static security audit: zero hardcoded secrets verification across repository.

Performs static AST analysis and regex pattern matching to ensure no live API keys,
passwords, access tokens, or private certificates are committed in source code files.
"""
import ast
import math
import os
import re
from pathlib import Path
from typing import List, Tuple
import pytest

# ---------------------------------------------------------------------------
# 1. Regex Matchers for Credentials and API Keys
# ---------------------------------------------------------------------------

STRICT_PRODUCTION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"AIza[0-9A-Za-z-_]{35}"), "Google Cloud / Gemini API Key"),
    (re.compile(r"AQ\.[A-Za-z0-9_-]{40,}"), "Gemini OAuth / Access Token"),
    (re.compile(r"sk-[a-zA-Z0-9_-]{24,}"), "OpenAI / Third-Party Secret Key"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS Access Key ID"),
    (re.compile(r"-----BEGIN (RSA|EC|OPENSSH|DSA|PGP|PRIVATE) KEY-----"), "Private Key Header"),
    (
        re.compile(
            r"(?i)(password|api_key|secret_key|auth_token|access_key)\s*[:=]\s*['\"]([a-zA-Z0-9_\-\.]{16,})['\"]"
        ),
        "Hardcoded High-Entropy Credential Assignment",
    ),
    (
        re.compile(r"(postgres|postgresql|mysql|mongodb|redis):\/\/[^:\s]+:([^@\s]{6,})@"),
        "Database Connection String with Embedded Password",
    ),
]

SAFE_WHITELIST_STRINGS = {
    "test_mock_gemini_key_12345",
    "your_gemini_api_key_here",
    "your_redis_password_here",
    "your_postgres_password_here",
    "placeholder",
    "sqlite+aiosqlite:///:memory:",
    "sqlite+aiosqlite:///./fan_zone.db",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/fan_zone",
    "postgresql+asyncpg://user:pass@localhost:5432/fanzone",
    "postgres://user:pass@localhost:5432/fanzone",
    "postgresql+asyncpg://db:5432/test",
}

EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".agents",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
}

EXCLUDED_FILE_NAMES = {
    ".env.example",
    "test_no_hardcoded_secrets.py",  # Exclude self to avoid matching pattern definitions
}

CHECKED_EXTENSIONS = {
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sh",
    ".md",
    ".env",
    ".ini",
    ".txt",
}


def _shannon_entropy(s: str) -> float:
    """Computes the Shannon entropy of a string to detect high-entropy tokens."""
    if not s:
        return 0.0
    probabilities = [float(s.count(c)) / len(s) for c in set(s)]
    return -sum(p * math.log2(p) for p in probabilities)


def _is_test_mock_token(val: str, is_test_file: bool) -> bool:
    """Returns True if the string is clearly a mock or test placeholder in a test file."""
    if any(safe in val for safe in SAFE_WHITELIST_STRINGS):
        return True
    if is_test_file:
        lower = val.lower()
        if any(marker in lower for marker in ("mock", "test", "dummy", "fake", "valid-api-key", "some-key", "sample")):
            return True
    return False


def _scan_file_regex(file_path: Path, root_path: Path) -> List[str]:
    """Scans file line-by-line for known secret regex patterns."""
    violations = []
    is_test_file = "tests" in file_path.parts
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return violations

    for line_no, line in enumerate(content.splitlines(), start=1):
        if _is_test_mock_token(line, is_test_file):
            continue

        for pattern, desc in STRICT_PRODUCTION_PATTERNS:
            match = pattern.search(line)
            if match:
                matched_text = match.group(0)
                if _is_test_mock_token(matched_text, is_test_file):
                    continue
                rel_path = file_path.relative_to(root_path)
                masked = matched_text[:6] + "..." + matched_text[-4:] if len(matched_text) > 10 else "***"
                violations.append(f"Line {line_no} in {rel_path}: {desc} (Match: {masked})")
    return violations


def _scan_python_ast(file_path: Path, root_path: Path) -> List[str]:
    """Parses Python file AST looking for hardcoded string literals assigned to sensitive variable names."""
    violations = []
    is_test_file = "tests" in file_path.parts
    try:
        code = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(code, filename=str(file_path))
    except Exception:
        return violations

    sensitive_var_names = {"api_key", "secret", "password", "token", "auth_key", "private_key"}

    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            target_names = []
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        target_names.append(t.id.lower())
                    elif isinstance(t, ast.Attribute):
                        target_names.append(t.attr.lower())
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    target_names.append(node.target.id.lower())
                elif isinstance(node.target, ast.Attribute):
                    target_names.append(node.target.attr.lower())

            # Check if any sensitive target name is found
            is_sensitive = any(any(s in name for s in sensitive_var_names) for name in target_names)
            if is_sensitive and node.value:
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    val = node.value.value
                    if _is_test_mock_token(val, is_test_file) or len(val) < 12:
                        continue
                    # High entropy or long hex/base64 check
                    if _shannon_entropy(val) > 3.2 and len(val) >= 16:
                        rel_path = file_path.relative_to(root_path)
                        violations.append(
                            f"Line {node.lineno} in {rel_path}: Hardcoded high-entropy secret assigned to {target_names}"
                        )
    return violations


@pytest.mark.security
def test_no_hardcoded_secrets_in_repository():
    """Verify that zero hardcoded API keys or high-entropy credentials exist in repository."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    all_violations: List[str] = []

    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in path.parts for part in EXCLUDED_DIR_NAMES):
            continue
        if path.name in EXCLUDED_FILE_NAMES:
            continue
        if path.suffix.lower() not in CHECKED_EXTENSIONS:
            continue

        # 1. Regex pattern scan
        regex_violations = _scan_file_regex(path, repo_root)
        all_violations.extend(regex_violations)

        # 2. Python AST scan
        if path.suffix == ".py":
            ast_violations = _scan_python_ast(path, repo_root)
            all_violations.extend(ast_violations)

    assert not all_violations, (
        f"Static Security Audit Failed! {len(all_violations)} secret violation(s) detected:\n"
        + "\n".join(f"  - {v}" for v in all_violations)
    )
