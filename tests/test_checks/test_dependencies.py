import pytest
import respx
import httpx
from src.checks.dependencies import extract_packages, lookup_cves_batch, _parse_severity
from src.schemas.findings import Severity


def test_extract_requirements_txt():
    content = "requests==2.28.0\nflask==2.0.1\nnumpy>=1.21.0"
    packages = extract_packages(content, "requirements.txt")
    assert {"name": "requests", "version": "2.28.0", "ecosystem": "PyPI"} in packages
    assert {"name": "flask", "version": "2.0.1", "ecosystem": "PyPI"} in packages


def test_extract_requirements_txt_ignores_unpinned():
    content = "requests\nflask>=2.0"
    packages = extract_packages(content, "requirements.txt")
    assert packages == []


def test_extract_package_json():
    content = '{"dependencies": {"express": "4.18.2", "lodash": "4.17.20"}}'
    packages = extract_packages(content, "package.json")
    assert {"name": "express", "version": "4.18.2", "ecosystem": "npm"} in packages


def test_extract_package_json_ignores_ranges():
    content = '{"dependencies": {"express": "^4.18.2"}}'
    packages = extract_packages(content, "package.json")
    assert packages == []


def test_extract_unknown_file_returns_empty():
    packages = extract_packages("something", "Makefile")
    assert packages == []


def test_extract_go_mod_block_require():
    content = (
        "module example.com/myapp\n"
        "\n"
        "go 1.21\n"
        "\n"
        "require (\n"
        "\tgithub.com/gin-gonic/gin v1.9.1\n"
        "\tgithub.com/lib/pq v1.10.9 // indirect\n"
        ")\n"
    )
    packages = extract_packages(content, "go.mod")
    assert len(packages) == 2
    assert packages[0] == {
        "name": "github.com/gin-gonic/gin",
        "version": "1.9.1",
        "ecosystem": "Go",
    }
    assert packages[1] == {
        "name": "github.com/lib/pq",
        "version": "1.10.9",
        "ecosystem": "Go",
    }


def test_extract_go_mod_single_line_require():
    content = (
        "module example.com/myapp\n"
        "\n"
        "go 1.21\n"
        "\n"
        "require github.com/stretchr/testify v1.8.4\n"
    )
    packages = extract_packages(content, "go.mod")
    assert len(packages) == 1
    assert packages[0] == {
        "name": "github.com/stretchr/testify",
        "version": "1.8.4",
        "ecosystem": "Go",
    }


def test_extract_go_mod_ignores_go_directive():
    content = "module example.com/myapp\n\ngo 1.21\n"
    packages = extract_packages(content, "go.mod")
    assert packages == []


@pytest.mark.asyncio
@respx.mock
async def test_lookup_cves_batch_returns_findings():
    respx.post("https://api.osv.dev/v1/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "vulns": [
                    {
                        "id": "GHSA-test-1234-abcd",
                        "aliases": ["CVE-2024-1234"],
                        "summary": "Critical RCE in requests",
                        "severity": [{"type": "CVSS_V3", "score": "9.8"}],
                        "affected": [
                            {
                                "versions": ["2.28.0"],
                                "package": {"name": "requests", "ecosystem": "PyPI"},
                                "ranges": [
                                    {
                                        "type": "ECOSYSTEM",
                                        "events": [
                                            {"introduced": "0"},
                                            {"fixed": "2.31.0"},
                                        ],
                                    }
                                ],
                            }
                        ],
                        "references": [
                            {"url": "https://osv.dev/vulnerability/GHSA-test-1234-abcd"}
                        ],
                    }
                ]
            },
        )
    )
    packages = [{"name": "requests", "version": "2.28.0", "ecosystem": "PyPI"}]
    findings = await lookup_cves_batch(packages)
    assert len(findings) == 1
    assert findings[0].cve_id == "CVE-2024-1234"
    assert findings[0].package == "requests"


def test_parse_severity_cvss_vector_critical():
    """CVSS vector with network access, no privs, high impact -> critical."""
    vuln = {
        "severity": [
            {"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H"}
        ]
    }
    assert _parse_severity(vuln) == Severity.critical


def test_parse_severity_cvss_vector_high():
    """CVSS vector with network access, no privs, but not all high impact -> high."""
    vuln = {
        "severity": [
            {"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:N"}
        ]
    }
    assert _parse_severity(vuln) == Severity.high


def test_parse_severity_cvss_vector_medium():
    """CVSS vector with network but requires privileges -> medium."""
    vuln = {
        "severity": [
            {"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:L/A:N"}
        ]
    }
    assert _parse_severity(vuln) == Severity.medium


def test_parse_severity_cvss_vector_low():
    """CVSS vector requiring local access -> low."""
    vuln = {
        "severity": [
            {"type": "CVSS_V3", "score": "CVSS:3.1/AV:L/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N"}
        ]
    }
    assert _parse_severity(vuln) == Severity.low


def test_parse_severity_numeric_score():
    """Plain numeric score string should still work."""
    vuln = {"severity": [{"type": "CVSS_V3", "score": "9.8"}]}
    assert _parse_severity(vuln) == Severity.critical


def test_parse_severity_database_specific_takes_precedence():
    """database_specific.severity should take precedence over CVSS vector."""
    vuln = {
        "database_specific": {"severity": "LOW"},
        "severity": [
            {"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H"}
        ],
    }
    assert _parse_severity(vuln) == Severity.low


@pytest.mark.asyncio
@respx.mock
async def test_lookup_cves_batch_no_vulns():
    respx.post("https://api.osv.dev/v1/query").mock(
        return_value=httpx.Response(200, json={})
    )
    packages = [{"name": "requests", "version": "2.31.0", "ecosystem": "PyPI"}]
    findings = await lookup_cves_batch(packages)
    assert findings == []
