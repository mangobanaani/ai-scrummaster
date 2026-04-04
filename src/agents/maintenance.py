from crewai import Agent, Task, LLM


def build_maintenance_agent(llm: LLM, tools: list) -> Agent:
    return Agent(
        role="Repository Maintenance Manager",
        goal=(
            "Manage stale issues by posting nudge comments, closing abandoned issues, "
            "and reporting WIP limit violations. Follow exact instructions."
        ),
        backstory=(
            "You are a project maintenance agent. You keep the issue tracker healthy "
            "by nudging stale issues and enforcing work-in-progress limits."
        ),
        llm=llm,
        tools=tools,
        verbose=False,
        max_iter=10,
    )


def build_maintenance_task(
    agent: Agent,
    stale_issues: list[dict],
    auto_close_issues: list[dict],
    wip_violations: list[dict],
    repo: str,
    stale_nudge_message: str = "",
) -> Task:
    instructions = [
        f"Execute maintenance actions for repository '{repo}':\n",
    ]

    if stale_issues:
        instructions.append("**Stale issues to nudge** (post a comment reminding the assignee):")
        for issue in stale_issues:
            assignee = issue.get("assignee", {})
            assignee_name = assignee.get("login", "unassigned") if assignee else "unassigned"
            instructions.append(
                f"- Issue #{issue['number']}: \"{issue['title']}\" "
                f"(stale {issue['days_stale']} days, assigned to @{assignee_name})"
            )
            nudge_text = stale_nudge_message or "a polite nudge reminding the assignee to update the issue"
            instructions.append(
                f"  Call add_issue_comment on #{issue['number']} with: {nudge_text}"
            )
            instructions.append(
                f"  Call issue_write on #{issue['number']} to add label 'stale'."
            )

    if auto_close_issues:
        instructions.append("\n**Issues to close** (inactive beyond auto-close threshold):")
        for issue in auto_close_issues:
            instructions.append(
                f"- Issue #{issue['number']}: \"{issue['title']}\" "
                f"(stale {issue['days_stale']} days)"
            )
            instructions.append(
                f"  Call add_issue_comment on #{issue['number']} explaining closure due to inactivity."
            )
            instructions.append(
                f"  Call issue_write on #{issue['number']} with state='closed'."
            )

    if wip_violations:
        instructions.append("\n**WIP limit violations:**")
        for v in wip_violations:
            instructions.append(
                f"- Label '{v['label']}': {v['count']} open issues (limit: {v['limit']})"
            )

    if not stale_issues and not auto_close_issues and not wip_violations:
        instructions.append("No maintenance actions needed. All clear.")

    instructions.append("\nDo not make any tool calls not listed above.")

    return Task(
        description="\n".join(instructions),
        expected_output="Confirmation of all maintenance actions taken.",
        agent=agent,
    )
