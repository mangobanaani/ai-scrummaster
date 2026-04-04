from src.checks.secrets import scan_for_secrets
from src.schemas.findings import FindingType, Severity


def test_detects_aws_access_key():
    diff = "+AKIAIOSFODNN7EXAMPLE = 'secret'"
    findings = scan_for_secrets(diff)
    assert len(findings) == 1
    assert findings[0].type == FindingType.secret
    assert findings[0].severity == Severity.critical


def test_detects_github_token():
    diff = "+token = 'ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456'"
    findings = scan_for_secrets(diff)
    assert len(findings) >= 1
    assert any(f.type == FindingType.secret for f in findings)


def test_detects_private_key_header():
    diff = "+-----BEGIN RSA PRIVATE KEY-----"
    findings = scan_for_secrets(diff)
    assert len(findings) >= 1


def test_detects_generic_password_assignment():
    diff = '+password = "SuperSecret123!"'
    findings = scan_for_secrets(diff)
    assert len(findings) >= 1


def test_detects_stripe_key():
    prefix = "sk_live_"
    suffix = "aBcDeFgHiJkLmNoPqRsTuVwXyZ"
    diff = f"+{prefix}{suffix}"
    findings = scan_for_secrets(diff)
    assert len(findings) >= 1


def test_clean_diff_has_no_findings():
    diff = "+def add(a, b):\n+    return a + b"
    findings = scan_for_secrets(diff)
    assert findings == []


def test_returns_recommendation():
    diff = "+AKIAIOSFODNN7EXAMPLE = 'x'"
    findings = scan_for_secrets(diff)
    assert findings[0].recommendation != ""
