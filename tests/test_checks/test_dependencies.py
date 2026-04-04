import pytest
import respx
import httpx
from src.checks.dependencies import extract_packages, lookup_cves_batch


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
                        "affected": [{"versions": ["2.28.0"], "package": {"name": "requests", "ecosystem": "PyPI"}, "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.31.0"}]}]}],
                        "references": [{"url": "https://osv.dev/vulnerability/GHSA-test-1234-abcd"}],
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


@pytest.mark.asyncio
@respx.mock
async def test_lookup_cves_batch_no_vulns():
    respx.post("https://api.osv.dev/v1/query").mock(
        return_value=httpx.Response(200, json={})
    )
    packages = [{"name": "requests", "version": "2.31.0", "ecosystem": "PyPI"}]
    findings = await lookup_cves_batch(packages)
    assert findings == []
