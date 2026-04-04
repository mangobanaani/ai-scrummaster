import re

from src.schemas.findings import Finding, FindingType, Severity

_SECRET_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    (
        "AWS Access Key",
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "Rotate the AWS key immediately via IAM console and remove from codebase. Use IAM roles or environment variables.",
    ),
    (
        "GitHub Token (ghp_)",
        re.compile(r"ghp_[A-Za-z0-9]{20,}", re.IGNORECASE),
        "Revoke the token at github.com/settings/tokens and store secrets in GitHub Secrets or a vault.",
    ),
    (
        "GitHub Token (ghs_)",
        re.compile(r"ghs_[A-Za-z0-9]{20,}", re.IGNORECASE),
        "Revoke immediately. Use GITHUB_TOKEN or a secrets manager.",
    ),
    (
        "Private Key Header",
        re.compile(r"-----BEGIN\s+(RSA|EC|DSA|OPENSSH|PGP)?\s*PRIVATE KEY-----"),
        "Remove the private key from source. Use a secrets manager (HashiCorp Vault, AWS Secrets Manager).",
    ),
    (
        "Stripe Live Key",
        re.compile(r"sk_live_[A-Za-z0-9]{24,}"),
        "Revoke the Stripe key at dashboard.stripe.com/apikeys and move to environment variables.",
    ),
    (
        "Stripe Test Key",
        re.compile(r"sk_test_[A-Za-z0-9]{24,}"),
        "Remove test keys from source; use environment variables even for test keys.",
    ),
    (
        "Generic Password Assignment",
        re.compile(
            r'(?:password|passwd|pwd|secret|api_key|apikey|auth_token)\s*=\s*["\'][^"\']{8,}["\']',
            re.IGNORECASE,
        ),
        "Move credentials to environment variables or a secrets manager. Never hardcode secrets.",
    ),
    (
        "Google API Key",
        re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
        "Revoke at console.cloud.google.com and restrict API key usage by IP and scope.",
    ),
    (
        "GCP Service Account Key",
        re.compile(r'"type":\s*"service_account"'),
        "Remove the service account JSON from source. Use Workload Identity or Secret Manager.",
    ),
    (
        "Slack Token",
        re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}"),
        "Revoke at api.slack.com/apps and use environment variables.",
    ),
    (
        "Slack Webhook",
        re.compile(r"https://hooks\.slack\.com/services/[A-Z0-9/]+", re.IGNORECASE),
        "Rotate the Slack webhook URL and store in environment variables.",
    ),
    (
        "SendGrid API Key",
        re.compile(r"SG\.[A-Za-z0-9\-_]{22}\.[A-Za-z0-9\-_]{43}"),
        "Revoke the SendGrid key and move to environment variables.",
    ),
    (
        "Twilio Auth Token",
        re.compile(r"(?:twilio|auth.token)\s*=\s*[0-9a-f]{32}", re.IGNORECASE),
        "Rotate the Twilio auth token at console.twilio.com.",
    ),
    (
        "Bearer Token in Code",
        re.compile(
            r'(?:Authorization|Bearer)\s*[:=]\s*["\']?Bearer\s+[A-Za-z0-9\-_\.]{20,}["\']?',
            re.IGNORECASE,
        ),
        "Remove hardcoded bearer tokens. Use environment variables and inject at runtime.",
    ),
    (
        "Basic Auth in URL",
        re.compile(r"https?://[^:@\s]+:[^@\s]+@[^\s]+"),
        "Remove credentials from URLs. Use environment variables for credentials.",
    ),
    (
        "Azure Storage Key",
        re.compile(r"DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[A-Za-z0-9/+=]{86}"),
        "Rotate the Azure Storage key in the Azure portal and use Managed Identity instead.",
    ),
    (
        "NPM Auth Token",
        re.compile(r"//registry\.npmjs\.org/:_authToken=[A-Za-z0-9\-]+"),
        "Remove the NPM token from .npmrc and use CI environment variables.",
    ),
]


def scan_for_secrets(diff: str) -> list[Finding]:
    """Scan a git diff string for secret patterns. Returns a list of Findings."""
    findings: list[Finding] = []
    seen_patterns: set[str] = set()

    for name, pattern, recommendation in _SECRET_PATTERNS:
        if pattern.search(diff) and name not in seen_patterns:
            seen_patterns.add(name)
            findings.append(
                Finding(
                    type=FindingType.secret,
                    severity=Severity.critical,
                    description=f"Potential secret detected: {name}",
                    recommendation=recommendation,
                )
            )

    return findings
