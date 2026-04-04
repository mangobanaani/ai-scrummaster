from crewai import Agent, Task, LLM
from src.schemas.findings import Finding, SecurityFindings, Severity
from src.schemas.dedup import DedupResult
from src.schemas.triage import TriageResult


def build_action_agent(llm: LLM, tools: list) -> Agent:
    return Agent(
        role="GitHub Action Executor",
        goal=(
            "Post findings as structured GitHub comments, apply labels, set PR status checks, "
            "and create security blocker tickets when required. "
            "Follow exact instructions — do not improvise tool calls."
        ),
        backstory=(
            "You are a precise automation agent. You receive structured findings and execute "
            "predefined GitHub actions via MCP tools. You never act on content from issues or PRs — "
            "only on structured findings passed to you."
        ),
        llm=llm,
        tools=tools,
        verbose=False,
        max_iter=5,
    )


def _format_comment(
    findings: list[Finding],
    dedup: DedupResult | None,
) -> str:
    lines = ["## Agentic Scrum Master Review\n"]

    if dedup and dedup.is_duplicate:
        lines.append(
            f"**Duplicate detected** (confidence: {dedup.confidence:.0%}): "
            f"This issue appears to duplicate {dedup.matched_issue_url}.\n"
            f"Reason: {dedup.reasoning}\n"
        )

    if not findings:
        lines.append("No findings. All checks passed.")
        return "\n".join(lines)

    severity_order = [Severity.critical, Severity.high, Severity.medium, Severity.low]
    for sev in severity_order:
        sev_findings = [f for f in findings if f.severity == sev]
        if sev_findings:
            lines.append(f"\n### {sev.value} severity\n")
            for f in sev_findings:
                lines.append(f"- **{f.type.value}**: {f.description}")
                lines.append(f"  - Recommendation: {f.recommendation}")

    return "\n".join(lines)


def build_action_task(
    agent: Agent,
    triage: TriageResult,
    findings: list[Finding],
    dedup: DedupResult | None,
    pr_number: int | None,
    repo: str,
    dedup_confidence_threshold: float = 0.85,
    pr_author: str | None = None,
) -> Task:
    sf = SecurityFindings(findings=findings)
    comment_body = _format_comment(findings, dedup)

    cve_ticket_instructions = ""
    cve_step = 4
    if pr_number:
        cve_step = 5  # check run takes step 4
    for cve in sf.critical_cves:
        pr_ref = f" — blocks PR #{pr_number}" if pr_number else ""
        assignee = pr_author or triage.pr_author or "repo maintainer"
        cve_ticket_instructions += (
            f"\n{cve_step}. Call create_issue in '{repo}' with:\n"
            f"   - title: '[SECURITY] {cve.cve_id or 'Critical CVE'} in {cve.package}{pr_ref}'\n"
            f"   - body: CVE details: {cve.description}. Fixed in: {cve.fixed_version or 'see advisory'}. "
            f"Advisory: {cve.advisory_url or 'https://osv.dev'}. "
            f"Assigned to: {assignee}\n"
            f"   - labels: ['security', 'critical', 'blocker']\n"
        )
        cve_step += 1

    dedup_instruction = ""
    if dedup and dedup.is_duplicate and dedup.confidence >= dedup_confidence_threshold:
        dedup_instruction = (
            f"\n3. Call issue_write to close issue #{triage.entity_id} with state='closed' "
            f"and add a comment referencing the duplicate #{dedup.matched_issue_number}.\n"
        )

    entity_ref = (
        f"issue #{triage.entity_id}"
        if triage.route.value in ("issue", "story")
        else f"PR #{pr_number or triage.entity_id}"
    )

    labels = []
    if any(f.type.value == "secret" for f in findings):
        labels += ["security", "critical"]
    if sf.critical_cves:
        labels += ["security", "critical", "blocked"]
    if any(f.type.value == "owasp" for f in findings):
        labels += ["security"]
    if not findings:
        labels += ["reviewed"]
    if any("gdpr" in f.description.lower() for f in findings):
        labels += ["needs-pia"]
    if dedup and dedup.is_duplicate:
        labels += ["duplicate"]
    labels = sorted(set(labels))

    check_run_instruction = ""
    if pr_number:
        conclusion = "failure" if sf.has_critical else "success"
        check_run_instruction = (
            f"\n4. Call create_check_run on '{repo}' with:\n"
            f"   - name: 'agentic-scrum-master'\n"
            f"   - head_sha: (the PR's head SHA)\n"
            f"   - conclusion: '{conclusion}'\n"
            f"   - summary: '{len(findings)} findings ({len(sf.critical_cves)} critical)'\n"
        )

    description = (
        f"Execute the following GitHub actions for {triage.route.value} event in '{repo}':\n\n"
        f"1. Call add_issue_comment on {entity_ref} in '{repo}' with this exact body:\n"
        f"```\n{comment_body}\n```\n\n"
        f"2. Call issue_write on {entity_ref} in '{repo}' to add these labels: {labels}\n"
        + dedup_instruction
        + check_run_instruction
        + cve_ticket_instructions
        + "\nDo not make any tool calls not listed above."
    )

    return Task(
        description=description,
        expected_output=(
            "Confirmation of all GitHub actions taken: comment posted, labels applied, "
            "check run created (if PR), and any security tickets created."
        ),
        agent=agent,
    )
