import pytest
import yaml
from src.checks.policy import PolicyEngine


@pytest.fixture
def rules_file(tmp_path):
    rules = {
        "wip_limits": {"feature": 2, "bug": 5},
        "stale_days": 7,
        "branch_naming": {"pattern": "^(feature|fix)/", "required": True},
        "pr_requires_linked_issue": True,
        "protected_branches": ["main"],
        "cve_thresholds": {
            "auto_ticket_severity": ["CRITICAL", "HIGH"],
            "block_merge_severity": ["CRITICAL"],
        },
        "dedup_confidence_threshold": 0.85,
    }
    f = tmp_path / "rules.yaml"
    f.write_text(yaml.dump(rules))
    return str(f)


def test_loads_rules(rules_file):
    engine = PolicyEngine(rules_file)
    assert engine.rules.stale_days == 7
    assert engine.rules.dedup_confidence_threshold == 0.85


def test_branch_naming_valid(rules_file):
    engine = PolicyEngine(rules_file)
    assert engine.check_branch_name("feature/add-login") is True


def test_branch_naming_invalid(rules_file):
    engine = PolicyEngine(rules_file)
    assert engine.check_branch_name("my-random-branch") is False


def test_branch_naming_not_required(tmp_path):
    rules = {"branch_naming": {"pattern": "^feature/", "required": False}}
    f = tmp_path / "rules.yaml"
    f.write_text(yaml.dump(rules))
    engine = PolicyEngine(str(f))
    assert engine.check_branch_name("anything") is True


def test_is_protected_branch(rules_file):
    engine = PolicyEngine(rules_file)
    assert engine.is_protected_branch("main") is True
    assert engine.is_protected_branch("feature/x") is False


def test_should_auto_ticket_critical(rules_file):
    engine = PolicyEngine(rules_file)
    assert engine.should_auto_ticket("CRITICAL") is True
    assert engine.should_auto_ticket("HIGH") is True
    assert engine.should_auto_ticket("MEDIUM") is False


def test_should_block_merge(rules_file):
    engine = PolicyEngine(rules_file)
    assert engine.should_block_merge("CRITICAL") is True
    assert engine.should_block_merge("HIGH") is False
