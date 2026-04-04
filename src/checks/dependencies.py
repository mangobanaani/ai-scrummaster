import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

from src.schemas.findings import Finding, FindingType, Severity

_OSV_API = "https://api.osv.dev/v1/query"

_REQUIREMENTS_RE = re.compile(r"^([A-Za-z0-9_\-\.]+)==([0-9][^\s;]+)", re.MULTILINE)
_PACKAGE_JSON_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def extract_packages(content: str, filename: str) -> list[dict]:
    """Extract pinned packages from a dependency file. Returns list of {name, version, ecosystem}."""
    filename_lower = filename.lower()

    if "requirements" in filename_lower and filename_lower.endswith(".txt"):
        return [
            {"name": m.group(1), "version": m.group(2), "ecosystem": "PyPI"}
            for m in _REQUIREMENTS_RE.finditer(content)
        ]

    basename = filename_lower.rsplit("/", 1)[-1]

    if basename == "package.json":
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return []
        packages = []
        for section in ("dependencies", "devDependencies"):
            for name, ver in data.get(section, {}).items():
                if _PACKAGE_JSON_VERSION_RE.match(ver):
                    packages.append({"name": name, "version": ver, "ecosystem": "npm"})
        return packages

    if basename == "go.mod":
        results = []
        in_require = False
        _GO_REQUIRE_BLOCK = re.compile(r"^require\s*\(")
        for line in content.splitlines():
            stripped = line.strip()
            if _GO_REQUIRE_BLOCK.match(stripped):
                in_require = True
                continue
            if in_require and stripped == ")":
                in_require = False
                continue
            if re.match(r"^require\s", stripped) and "(" not in stripped:
                # Single-line require: require github.com/foo/bar v1.2.3
                parts = re.split(r"\s+", stripped, maxsplit=1)[1].strip().split()
                if len(parts) == 2 and parts[1].startswith("v") and "/" in parts[0]:
                    results.append(
                        {"name": parts[0], "version": parts[1].lstrip("v"), "ecosystem": "Go"}
                    )
                continue
            if in_require:
                parts = stripped.split()
                if len(parts) >= 2 and parts[1].startswith("v") and "/" in parts[0]:
                    results.append(
                        {"name": parts[0], "version": parts[1].lstrip("v"), "ecosystem": "Go"}
                    )
        return results

    return []


def _parse_severity(vuln: dict) -> Severity:
    # First try database_specific severity (most reliable)
    db_severity = vuln.get("database_specific", {}).get("severity", "")
    if db_severity:
        upper = db_severity.upper()
        if "CRITICAL" in upper:
            return Severity.critical
        if "HIGH" in upper:
            return Severity.high
        if "MEDIUM" in upper or "MODERATE" in upper:
            return Severity.medium
        if "LOW" in upper:
            return Severity.low

    # Then try numeric scores from severity entries
    for s in vuln.get("severity", []):
        score_raw = s.get("score", "")
        # Try parsing as a plain numeric score
        try:
            val = float(score_raw)
            if val >= 9.0:
                return Severity.critical
            if val >= 7.0:
                return Severity.high
            if val >= 4.0:
                return Severity.medium
            return Severity.low
        except ValueError:
            pass
    return Severity.high


async def lookup_cves_batch(packages: list[dict]) -> list[Finding]:
    """Query OSV API for each package and return Findings for any vulnerabilities found."""
    findings: list[Finding] = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        for pkg in packages:
            try:
                resp = await client.post(
                    _OSV_API,
                    json={
                        "version": pkg["version"],
                        "package": {"name": pkg["name"], "ecosystem": pkg["ecosystem"]},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as exc:
                logger.warning("CVE lookup failed for %s@%s: %s", pkg["name"], pkg["version"], exc)
                continue

            for vuln in data.get("vulns", []):
                cve_id = next(
                    (a for a in vuln.get("aliases", []) if a.startswith("CVE-")),
                    vuln.get("id"),
                )
                advisory_url = next(
                    (
                        r["url"]
                        for r in vuln.get("references", [])
                        if "osv.dev" in r.get("url", "")
                    ),
                    None,
                )
                fixed_version = None
                for affected in vuln.get("affected", []):
                    if fixed_version:
                        break
                    for rng in affected.get("ranges", []):
                        if fixed_version:
                            break
                        for event in rng.get("events", []):
                            if "fixed" in event:
                                fixed_version = event["fixed"]
                                break

                severity = _parse_severity(vuln)
                findings.append(
                    Finding(
                        type=FindingType.cve,
                        severity=severity,
                        description=(
                            f"{cve_id or vuln['id']}: "
                            f"{vuln.get('summary', 'Vulnerability found')} "
                            f"in {pkg['name']}@{pkg['version']}"
                        ),
                        recommendation=(
                            f"Upgrade {pkg['name']} to "
                            f"{fixed_version or 'latest patched version'}. "
                            f"See advisory for details."
                        ),
                        cve_id=cve_id,
                        package=pkg["name"],
                        fixed_version=fixed_version,
                        advisory_url=advisory_url,
                    )
                )

    return findings
