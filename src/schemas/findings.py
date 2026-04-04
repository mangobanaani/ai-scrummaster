from enum import Enum

from pydantic import BaseModel


class Severity(str, Enum):
    critical = "CRITICAL"
    high = "HIGH"
    medium = "MEDIUM"
    low = "LOW"


class FindingType(str, Enum):
    secret = "secret"
    cve = "cve"
    policy = "policy"
    agile = "agile"
    owasp = "owasp"
    gdpr = "gdpr"


class Finding(BaseModel):
    type: FindingType
    severity: Severity
    description: str
    recommendation: str
    cve_id: str | None = None
    package: str | None = None
    fixed_version: str | None = None
    advisory_url: str | None = None


class SecurityFindings(BaseModel):
    findings: list[Finding] = []

    @property
    def has_critical(self) -> bool:
        return any(f.severity == Severity.critical for f in self.findings)

    @property
    def has_high(self) -> bool:
        return any(f.severity == Severity.high for f in self.findings)

    @property
    def critical_cves(self) -> list[Finding]:
        return [
            f
            for f in self.findings
            if f.severity == Severity.critical and f.type == FindingType.cve
        ]
