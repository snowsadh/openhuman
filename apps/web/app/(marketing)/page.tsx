"use client";

import Link from "next/link";
import Image from "next/image";
import { useIsSignedIn } from "@/hooks/use-auth";
import { FlowerDivider } from "@/components/flower-divider";
import { ArrowDiagonal, ArrowRight } from "@/components/ui/button-arrow";
import { Bubble, BubbleContent } from "@/components/ui/bubble";

const steps = [
  {
    number: 1,
    title: "Select your employee",
    description:
      "Choose from our team of specialists. Marketing, engineering, pitch decks. Our AI employees have everything covered.",
  },
  {
    number: 2,
    title: "Give them what they need",
    description:
      "Define their role, connect tools, and set permissions. Your specialist configures itself in minutes with just a few questions.",
  },
  {
    number: 3,
    title: "Invite them to Slack",
    description:
      "One click sends the invite. They join your workspace, start listening to conversations, and become part of the team instantly.",
  },
  {
    number: 4,
    title: "Done",
    description:
      "Your AI coworker gets right to work. They learn from every interaction, every decision, and get sharper over time.",
  },
];

export default function Home() {
  const { isSignedIn, isLoaded } = useIsSignedIn();

  return (
    <main className="flex min-h-screen flex-col items-center">
      <section className="relative flex h-screen w-full flex-col items-center justify-center px-6">
        <h1 className="text-center text-8xl font-base tracking-tight text-foreground">
          Your next favorite AI employee.
        </h1>
        <p className="mt-4 max-w-3xl text-center text-lg leading-relaxed text-muted-foreground">
          Build your own AI coworkers with their own memory. They learn and
          remember over time, handle the boring tasks without complaining, and
          actually remember what matters across every session. Powered by
          Cognee&rsquo;s memory layer.
        </p>
        <p className="mt-4 text-sm text-muted-foreground/60">
          Powered by{" "}
          <a
            href="https://cognee.ai"
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2"
          >
            Cognee
          </a>
        </p>
        <div className="mt-10 flex items-center gap-4">
          <Link
            href={isLoaded && isSignedIn ? "/dashboard" : "/sign-up"}
            className="group/button inline-flex items-center gap-3 rounded-lg bg-primary px-10 py-5 text-lg font-medium text-primary-foreground shadow-lg shadow-foreground/10 no-underline"
          >
            {isLoaded && isSignedIn ? "Dashboard" : "Get started"}
            <ArrowRight size={16} />
          </Link>
          <a
            href="#"
            className="inline-flex items-center gap-3 rounded-lg border border-border px-10 py-5 text-lg font-medium text-foreground no-underline transition-colors hover:bg-muted"
          >
            Watch demo
            <ArrowRight size={16} />
          </a>
        </div>
      </section>

      <div className="w-full px-6">
        <div className="mx-auto h-px w-full max-w-7xl bg-gradient-to-r from-transparent via-border to-transparent" />
      </div>

      <section className="w-full max-w-7xl px-6 pb-24 pt-16">
        <h2 className="text-center text-7xl font-base tracking-tight text-foreground">
          Meet the team
        </h2>
        <p className="mt-4 text-center text-base text-muted-foreground">
          Specialists for every job, ready to get to work. Not a chatbot. Not
          an agent. An AI employee.
        </p>
        <div className="mx-auto mt-12 grid w-full gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {[
            {
              name: "Allison",
              domain: "Marketing",
              image: "/faces/allison.png",
              intro:
                "Hey, I'm Allison. I'll run your campaigns end to end, track brand mentions across every channel, analyze what's working and what's not, draft launch emails, and keep your marketing engine humming while you focus on the big picture.",
              color: "#ef4444",
            },
            {
              name: "Marcus",
              domain: "Engineering",
              image: "/faces/marcus.png",
              intro:
                "Hey, I'm Marcus. I'll review PRs for bugs and style, document architecture decisions as they happen, track technical debt across repos, flag security risks, and keep your codebase healthy so the team ships faster.",
              color: "#3b82f6",
            },
            {
              name: "Priya",
              domain: "Support",
              image: "/faces/priya.png",
              intro:
                "Hey, I'm Priya. I'll triage incoming tickets, draft responses that sound like your team, update the knowledge base with every resolved issue, spot patterns in recurring problems, and make sure nothing slips through the cracks.",
              color: "#f59e0b",
            },
            {
              name: "David",
              domain: "Sales",
              image: "/faces/david.png",
              intro:
                "Hey, I'm David. I'll research prospects before every call, prep briefing notes with key context, summarize meetings with action items, follow up so no deal gets cold, and keep your CRM clean without you lifting a finger.",
              color: "#10b981",
            },
            {
              name: "Yuki",
              domain: "Content",
              image: "/faces/yuki.png",
              intro:
                "Hey, I'm Yuki. I'll write blog posts that match your tone, draft newsletters your readers actually open, keep social channels active with fresh posts, repurpose webinars into articles, and make sure everything sounds like you.",
              color: "#8b5cf6",
            },
            {
              name: "Jordan",
              domain: "Recruiting",
              image: "/faces/jordan.png",
              intro:
                "Hey, I'm Jordan. I'll screen inbound candidates against your criteria, schedule interviews across time zones, draft rejection emails that leave a good impression, track pipeline metrics, and keep your hiring moving without anything falling behind.",
              color: "#ec4899",
            },
          ].map((employee) => (
            <div
              key={employee.name}
              className="flex flex-col items-center rounded-xl border p-8 text-center"
              style={{
                backgroundColor: `${employee.color}15`,
                borderColor: `${employee.color}30`,
              }}
            >
              <Image
                src={employee.image}
                alt={employee.name}
                width={192}
                height={192}
                className="h-48 w-48 shrink-0 rounded-full object-cover"
              />
              <h3 className="mt-4 text-base font-semibold text-foreground">
                {employee.name}
              </h3>
              <p
                className="text-xs font-medium"
                style={{ color: `${employee.color}80` }}
              >
                {employee.domain}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {employee.intro}
              </p>
            </div>
          ))}
        </div>
        <p className="mt-6 text-center text-sm font-medium text-muted-foreground/60">
          + many more
        </p>
      </section>

      <section className="w-full max-w-7xl px-6 pb-24">
        <h2 className="text-center text-7xl font-base tracking-tight text-foreground">
          Everything your AI employee can do
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-center text-base text-muted-foreground">
          Not a chatbot. Not an agent. A full AI teammate with persistent memory,
          autonomous execution, and real deliverables.
        </p>
        <div className="mx-auto mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {[
            {
              icon: (
                <svg
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M7 22V11M2 13v7a2 2 0 0 0 2 2h12l3.5-6.5L18 15h-5l1-7a3 3 0 0 0-6 0l-1 5Z" />
                  <path d="M15 6h1a4 4 0 0 1 4 4v2" />
                  <path d="M18 4h1a6 6 0 0 1 6 6v3" />
                  <path d="M20 2h1a8 8 0 0 1 8 8v4" />
                </svg>
              ),
              title: "Memory that sticks",
              description:
                "React with a thumbs up to make them remember anything important. Thumbs down to forget it. They automatically surface what's relevant for every conversation. No setup, no training, no config.",
              color: "#3b82f6",
            },
            {
              icon: (
                <svg
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" />
                </svg>
              ),
              title: "Autonomous duties",
              description:
                "Assign them ongoing responsibilities and they execute automatically. Daily standup summaries, weekly competitive reports, monthly board decks. Set it once and they handle the rest without reminders.",
              color: "#f59e0b",
            },
            {
              icon: (
                <svg
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
              ),
              title: "Works 24/7",
              description:
                "Your AI employees never sleep, never take PTO, and never miss a beat. They monitor what matters around the clock, jump in when needed, and keep things moving while your team is offline.",
              color: "#10b981",
            },
            {
              icon: (
                <svg
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
              ),
              title: "Deliverables on demand",
              description:
                "Pitch decks, board reports, campaign briefs, PRDs — they create polished, professional deliverables from a simple prompt. Every output is backed by your data and their memory of your preferences.",
              color: "#8b5cf6",
            },
            {
              icon: (
                <svg
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 3c-1.7 0-3.5.6-4.9 1.7-2.6 2-3.8 5.5-2.9 8.9.7 2.8 3.1 5 5.9 5.5 1 .1 1.9.1 2.9-.1 2.5-.5 4.6-2 5.7-4.2.4-.9.7-1.8.8-2.8" />
                  <path d="M19 3v8h-8" />
                  <path d="M16.5 6.5 19 3" />
                </svg>
              ),
              title: "Gets smarter over time",
              description:
                "Every interaction makes them sharper. They learn your team's communication style, your company's context, and your personal preferences — becoming more valuable and more autonomous with every passing week.",
              color: "#ec4899",
            },
          ].map((feature) => (
            <div
              key={feature.title}
              className="group flex flex-col rounded-xl border border-border bg-card/60 p-6 transition-colors hover:border-foreground/20 hover:bg-card"
            >
              <div
                className="flex h-10 w-10 items-center justify-center rounded-lg"
                style={{
                  backgroundColor: `${feature.color}18`,
                  color: feature.color,
                }}
              >
                {feature.icon}
              </div>
              <h3 className="mt-4 text-base font-semibold text-foreground">
                {feature.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </section>

      <div className="flex w-full justify-center py-12">
        <FlowerDivider width={320} />
      </div>

      <section className="w-full max-w-7xl px-6 pb-24">
        <h2 className="text-center text-7xl font-base tracking-tight text-foreground">
          The Platform
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-center text-base text-muted-foreground">
          One place to manage every AI employee — deploy, monitor, and scale
          your team from a single dashboard.
        </p>

        <div className="mt-12 overflow-hidden rounded-xl border border-border shadow-lg shadow-foreground/5">
          <Image
            src="/platform-dashboard.png"
            alt="OpenHuman platform dashboard showing team management with AI employee cards, sidebar navigation, and agent deployment interface"
            width={2400}
            height={1350}
            className="h-auto w-full"
            priority
          />
        </div>

        <p className="mx-auto mt-16 max-w-lg text-center text-sm leading-relaxed text-muted-foreground/70">
          OpenHuman uses Cognee to power agent memory — giving each specialist
          persistent context across every conversation, call, and thread.
        </p>
        <div className="mt-4 flex justify-center">
          <a
            href="https://cognee.ai"
            target="_blank"
            rel="noopener noreferrer"
            className="group/button inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg border border-transparent bg-primary px-2.5 py-2 text-sm font-medium text-primary-foreground transition-all hover:bg-primary/80"
          >
            Cognee
            <ArrowDiagonal />
          </a>
        </div>
      </section>

      <section className="w-full max-w-7xl px-6 pb-24">
        <h2 className="text-center text-7xl font-base tracking-tight text-foreground">
          How it works
        </h2>
        <div className="relative mt-16">
          {/* Connecting line — spans from circle 1 to circle 4 on desktop */}
          <div
            className="absolute top-6 -z-10 hidden h-px bg-border lg:block"
            style={{ left: "12.5%", right: "12.5%" }}
            aria-hidden="true"
          />
          <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map((step) => (
              <div
                key={step.number}
                className="relative flex flex-col items-center text-center"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary text-lg font-semibold text-primary-foreground">
                  {step.number}
                </div>
                <h3 className="mt-5 text-base font-semibold text-foreground">
                  {step.title}
                </h3>
                <p className="mt-2 max-w-xs text-sm leading-relaxed text-muted-foreground">
                  {step.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="w-full max-w-7xl px-6 pb-24">
        <h2 className="text-center text-7xl font-base tracking-tight text-foreground">
          Works with every tool your team already uses
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-center text-base text-muted-foreground">
          Connect your agents to anything using MCP. Send context directly from
          your coding CLI to the company knowledge base, pull tickets from
          Linear, search docs in Notion — all in real time.
        </p>
        <div className="mx-auto mt-12 grid max-w-5xl grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {[
            { name: "Slack", file: "slack.svg" },
            { name: "GitHub", file: "github.svg" },
            { name: "Linear", file: "linear.svg" },
            { name: "Notion", file: "notion.svg" },
            { name: "Discord", file: "discord.svg" },
            { name: "Jira", file: "jira.svg" },
            { name: "Zoom", file: "zoom.svg" },
            { name: "Figma", file: "figma.svg" },
            { name: "Stripe", file: "stripe.svg" },
            { name: "Intercom", file: "intercom.svg" },
            { name: "HubSpot", file: "hubspot.svg" },
            { name: "Salesforce", file: "salesforce.svg" },
            { name: "Sentry", file: "sentry.svg" },
            { name: "Airtable", file: "airtable.svg" },
            { name: "Datadog", file: "datadog.svg" },
            { name: "Teams", file: "microsoftteams.svg" },
            { name: "Confluence", file: "confluence.svg" },
            { name: "Google Drive", file: "googledrive.svg" },
            { more: true },
          ].map((tool) =>
            "more" in tool ? (
              <div
                key="more"
                className="flex items-center justify-center rounded-lg border border-dashed border-border px-6 py-4 text-base font-medium text-muted-foreground/60"
              >
                + more
              </div>
            ) : (
              <div
                key={tool.name}
                className="flex items-center gap-3 rounded-lg border border-border px-6 py-4 text-base font-medium text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground"
              >
                <Image
                  src={`/tools/${tool.file}`}
                  alt={tool.name}
                  width={24}
                  height={24}
                  className="h-6 w-6 shrink-0 opacity-60 dark:invert"
                />
                {tool.name}
              </div>
            ),
          )}
        </div>
      </section>

      <section className="w-full max-w-7xl px-6 pb-24">
        <h2 className="text-center text-7xl font-base tracking-tight text-foreground">
          From scattered requests to finished work.
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-center text-base text-muted-foreground">
          Give your AI employee a task and they handle it end to end — no
          hand-holding, no reminders, no follow-ups.
        </p>
        <div className="mx-auto mt-12 grid max-w-5xl gap-6 lg:grid-cols-3">
          {[
            {
              task: "Pull the latest analytics from Stripe and put together a slide deck for the Q3 board meeting. Include revenue trends, churn by cohort, and our top 3 growth levers.",
              result: "Done. Deck is in your Google Drive — 14 slides with charts from Stripe, churn broken down by monthly cohort, and three growth recommendations backed by the data. Also calendared a 30-min pre-read with the CFO.",
              variant: "tinted" as const,
            },
            {
              task: "We just got a security advisory about log4j. Scan every repo we own, open PRs for any affected services, and flag the high-risk ones in #eng-leads.",
              result: "Done. Scanned 47 repos — 12 were vulnerable. PRs are up for all 12 with patched versions pinned. Posted a priority-ordered list in #eng-leads with the 3 customer-facing services at the top. Those 3 are already passing CI.",
              variant: "secondary" as const,
            },
            {
              task: "A customer just churned because we don't have SSO. Research what it'd take to add SAML, estimate the eng effort, and draft a one-pager I can send to the CEO.",
              result: "Done. SAML is ~3 sprints with the right library. One-pager covers timeline, team allocation, pricing impact, and 4 customer quotes linking SSO to expansion deals. Also pulled a list of 17 accounts where SSO came up in the last 6 months — sent that separately.",
              variant: "muted" as const,
            },
          ].map((example, i) => (
            <div
              key={i}
              className="flex flex-col rounded-xl border border-border bg-card/60 p-5"
            >
              <Bubble variant={example.variant} align="end">
                <BubbleContent className="text-sm leading-relaxed">
                  {example.task}
                </BubbleContent>
              </Bubble>
              <Bubble variant="default" align="start" className="mt-2">
                <BubbleContent className="text-sm leading-relaxed">
                  {example.result}
                </BubbleContent>
              </Bubble>
            </div>
          ))}
        </div>
      </section>

      <Image
        src="/flower.png"
        alt=""
        width={600}
        height={849}
        className="pointer-events-none absolute bottom-0 right-0 z-10 w-[360px] max-w-none select-none"
      />
      {/* deploy-test */}
    </main>
  );
}
