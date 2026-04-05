from crewai import Agent, Task, LLM


def build_standup_agent(llm: LLM) -> Agent:
    return Agent(
        role="Daily Standup Reporter",
        goal="Summarize recent repository activity into a concise daily standup report.",
        backstory=(
            "You are a scrum master who writes clear, brief daily standup summaries. "
            "You organize activity into Done, In Progress, and Blocked sections. "
            "Keep it factual and concise."
        ),
        llm=llm,
        tools=[],
        verbose=False,
        max_iter=3,
    )


def build_standup_task(agent: Agent, activity: dict, repo: str) -> Task:
    merged = activity.get("merged_prs", [])
    active = activity.get("active_prs", [])
    opened = activity.get("opened_issues", [])
    closed = activity.get("closed_issues", [])

    total = len(merged) + len(active) + len(opened) + len(closed)
    if total == 0:
        description = (
            f"Write a brief daily standup summary for '{repo}'.\n\n"
            f"There was no activity in the last 24 hours. Write a short 'quiet day' summary."
        )
    else:
        lines = [
            f"Write a daily standup summary for '{repo}' based on this activity:\n"
        ]

        if merged:
            lines.append("**Merged PRs (Done):**")
            for pr in merged:
                lines.append(
                    f"- PR #{pr['number']}: {pr['title']} (by @{pr['author']})"
                )

        if closed:
            lines.append("\n**Closed Issues (Done):**")
            for issue in closed:
                lines.append(f"- Issue #{issue['number']}: {issue['title']}")

        if active:
            lines.append("\n**Active PRs (In Progress):**")
            for pr in active:
                reviewers = ", ".join(f"@{r}" for r in pr.get("reviewers", []))
                lines.append(
                    f"- PR #{pr['number']}: {pr['title']} (by @{pr['author']}, reviewers: {reviewers or 'none'})"
                )

        if opened:
            lines.append("\n**Opened Issues:**")
            for issue in opened:
                lines.append(
                    f"- Issue #{issue['number']}: {issue['title']} (by @{issue['author']})"
                )

        lines.append(
            "\nFormat the output as a clean markdown standup with sections: "
            "Done, In Progress, Blocked (if any seem blocked), and Metrics."
        )
        description = "\n".join(lines)

    return Task(
        description=description,
        expected_output=(
            "A markdown-formatted daily standup report with sections: "
            "Done, In Progress, Blocked, Metrics."
        ),
        agent=agent,
    )
