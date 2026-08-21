# OpenHuman Repository Documentation

Welcome to the official developer documentation for the OpenHuman multi-agent workspace coordination framework. This documentation covers all architectural concepts, backend systems, dashboard designs, and deployment protocols inside the monorepo.

---

## Documentation Directory

Explore the system subsystems:

### 1. [Overview & Tech Stack](overview.md)
Introduction to OpenHuman system design, folder structure, technology stacks, monorepo setup, and basic flow topologies.

### 2. [Backend Architecture](backend.md)
Deep dive into the FastAPI backend, SQLAlchemy database schema, password hashing, AES-256-GCM token encryption, file storage modules, and Alembic database migrations.

### 3. [Frontend Dashboard](frontend.md)
Guide to the Next.js React frontend layout. Details the page route groups, Zustand state stores, TanStack React Query cache managers, and the generated Orval API client.

### 4. [Agent Orchestration Engine](agent_engine.md)
Explains the LangGraph agent state machine, node functionalities (safety guardrails, LLM calls, formatting), conversation checkpointer database, and the asynchronous task worker queue.

### 5. [Cognee Memory System](memory_system.md)
Outlines the embedded cognitive memory engine, multi-tenant permission layers, two-step upload pipeline, ScrapeGraphAI web scraping, and vector database management.

### 6. [Model Context Protocol (MCP)](mcp_integration.md)
Developer guide to dynamic tool integrations, OAuth authentication, client connections, rate-limiting, and circuit breaker middleware.

### 7. [Bot Gateway Manager](bot_gateway.md)
Details on Slack and Discord chat integrations, Socket Mode connections, workspace shared vs. per-employee configurations, and interactive escalation flows.

### 8. [DevOps & Deployment](devops_deployment.md)
Step-by-step developer setup commands (Bun and uv), API client generation, production Docker configurations, and environment variables specifications.
