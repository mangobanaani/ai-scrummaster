import logging
import re
import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class BranchNamingRule(BaseModel):
    pattern: str = "^(feature|fix|chore|security)/"
    required: bool = True


class CveThresholds(BaseModel):
    auto_ticket_severity: list[str] = ["CRITICAL", "HIGH"]
    block_merge_severity: list[str] = ["CRITICAL"]


class PolicyRules(BaseModel):
    wip_limits: dict[str, int] = {"feature": 5, "bug": 10, "security": 3}
    stale_days: int = 7
    auto_close_days: int = 30
    stale_nudge_message: str = ""
    branch_naming: BranchNamingRule = BranchNamingRule()
    pr_requires_linked_issue: bool = True
    protected_branches: list[str] = ["main", "master"]
    cve_thresholds: CveThresholds = CveThresholds()
    dedup_confidence_threshold: float = 0.85


class PolicyEngine:
    def __init__(self, rules_path: str):
        try:
            with open(rules_path) as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning("Policy file not found at %s, using defaults", rules_path)
            data = {}
        except yaml.YAMLError as exc:
            logger.warning(
                "Invalid YAML in policy file %s: %s, using defaults", rules_path, exc
            )
            data = {}
        self.rules = PolicyRules.model_validate(data)

    def check_branch_name(self, branch: str) -> bool:
        if not self.rules.branch_naming.required:
            return True
        return bool(re.match(self.rules.branch_naming.pattern, branch))

    def is_protected_branch(self, branch: str) -> bool:
        return branch in self.rules.protected_branches

    def should_auto_ticket(self, severity: str) -> bool:
        return severity.upper() in self.rules.cve_thresholds.auto_ticket_severity

    def should_block_merge(self, severity: str) -> bool:
        return severity.upper() in self.rules.cve_thresholds.block_merge_severity

    def wip_limit_for(self, label_type: str) -> int:
        return self.rules.wip_limits.get(label_type, 999)
