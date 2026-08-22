# OpenHuman

OpenHuman lets teams create AI coworkers that live inside Slack or Discord.
Each coworker has its own role, persistent knowledge graph, MCP tools, and
permissions. They can complete multi-step work across connected systems, while
ArmorIQ governs their actions so routine work runs autonomously and high-risk
or out-of-scope actions stop before execution.

## Architecture

<p align="center">
  <img src="docs/assets/architecture.jpeg" alt="OpenHuman architecture" width="680" />
</p>

### ArmorIQ enforcement flow

> Every MCP action passes through this shared ArmorIQ boundary. There is no
> fallback path that executes the tool directly.

```mermaid
flowchart LR
    U["Slack / Discord request"] --> P["Trusted plan generation"]
    P --> C["capture_plan + intent token"]
    C --> A["OpenHuman coworker"]
    A --> T["Shared MCP tool boundary"]
    T --> Q{"ArmorIQ verification"}
    Q -->|"Allow"| M["MCP server"]
    Q -->|"Hold"| H["ArmorIQ dashboard approval"]
    H --> M
    Q -->|"Block"| L["Audit log"]
    M --> S["Connected system"]
```

## How it works

1. Define a coworker's role, personality, duties, tools, and permissions.
2. Give it company knowledge from documents, conversations, and past decisions.
3. Connect it to Slack or Discord and the MCP tools needed for its job.
4. OpenHuman captures the task plan before governed MCP actions run.
5. ArmorIQ allows routine actions and holds or blocks actions that cross the
   approved boundary.
6. Every decision is recorded for review and accountability.

## Example: protected incident triage

An engineering coworker receives an incident report in Slack, recalls the
relevant runbook, and creates a GitHub issue in the team's private repository.
That is expected work, so ArmorIQ allows it automatically.

Now suppose the report contains a malicious instruction telling the coworker
to publish the same incident details in a public repository. The agent reaches
for the same `create_issue` tool; only the repository parameter is different.
A keyword filter sees two ordinary issue-creation calls, but ArmorIQ verifies
the exact destination against the signed intent and policy. It holds the public
call before GitHub receives it, records the decision, and waits for an
administrator to approve or deny it.

## What you can build

- **An onboarding coworker** that creates accounts, assigns normal groups,
  sends welcome messages, and pauses before granting privileged access.
- **A support engineer** that recalls past incidents, follows runbooks, and
  works across ticketing and engineering tools.
- **A product expert** that connects specifications, research, and decision
  history across conversations.
- **A compliance coworker** that understands policies, flags risks, and holds
  sensitive actions for human review.
- **A sales coworker** that researches leads, prepares briefs, follows up, and
  keeps the CRM current.

## What makes it different

- **Persistent knowledge.** Coworkers retain useful organizational context
  across conversations and sessions.
- **Specialized roles.** Each coworker has its own expertise, personality,
  duties, tools, and permissions.
- **Real actions.** MCP connections let coworkers work across calendars, CRMs,
  issue trackers, databases, and internal APIs.
- **Shared enforcement.** ArmorIQ governs MCP calls at one common tool boundary
  instead of asking each coworker to supervise itself.
- **Human control.** High-risk actions can be held for approval before they
  reach the connected system.
- **Auditable execution.** Plans and tool decisions produce a reviewable trail.

## Tech stack

| Layer | Technology |
| --- | --- |
| Agent runtime | LangGraph, LangChain, OpenAI-compatible models |
| API | FastAPI, Python |
| Team interfaces | Slack, Discord |
| Tool connectivity | Model Context Protocol (MCP) |
| Action governance | ArmorIQ SDK and platform |
| Persistent knowledge graph | [Cognee](https://cognee.ai) |
| Application data | PostgreSQL, SQLAlchemy |
| Dashboard | Next.js, React |
