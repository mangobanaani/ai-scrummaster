from src.checks.owasp import classify_owasp


def test_injection_detected():
    text = "user can submit SQL queries via the search input"
    categories = classify_owasp(text)
    assert "A03:2021-Injection" in categories


def test_broken_auth_detected():
    text = "implement login, session management and password reset"
    categories = classify_owasp(text)
    assert "A07:2021-Identification and Authentication Failures" in categories


def test_sensitive_data_detected():
    text = "store user credit card numbers and PII"
    categories = classify_owasp(text)
    assert "A02:2021-Cryptographic Failures" in categories


def test_access_control_detected():
    text = "admin panel should only be visible to admins"
    categories = classify_owasp(text)
    assert "A01:2021-Broken Access Control" in categories


def test_clean_text_has_no_categories():
    text = "fix the button color on the homepage"
    categories = classify_owasp(text)
    assert categories == []
