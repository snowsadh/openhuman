# DevOps & Deployment Guide

This document describes how to configure, run, and deploy the OpenHuman monorepo in development and production environments.

---

## 1. Local Development Setup

To run OpenHuman on a local machine, you need **Node.js (v20+)**, **Bun (v1.3+)**, **Python (v3.12)**, and **PostgreSQL (v16)** installed.

### Step 1: Initialize Frontend and Monorepo Workspaces
OpenHuman uses Turborepo with Bun to run development tasks. From the root directory:
```bash
# Install node dependencies across apps/web and packages/api-client
bun install
```

### Step 2: Initialize Backend Dependencies
The backend uses **uv** for fast package installations. Navigate to `apps/api/` and run:
```bash
# Sync dependencies and create a virtual environment (.venv)
uv sync
```

### Step 3: Run Database Migrations
Start your local PostgreSQL instance, create a database named `openhuman`, and apply the schemas:
```bash
# Run migrations using uv and alembic from apps/api/
uv run alembic upgrade head
```

### Step 4: Export OpenAPI Contract & Generate Type-Safe Client
To synchronize API changes with the frontend client:
1.  Run the backend API exporting script:
    ```bash
    uv run python scripts/export_openapi.py
    ```
2.  Navigate to `packages/api-client` and compile Orval schemas:
    ```bash
    bun run generate
    ```

### Step 5: Start Local Development Servers
Run the workspaces concurrently from the root directory:
```bash
bun run dev
```
*   **Next.js Dashboard**: [http://localhost:3000](http://localhost:3000)
*   **FastAPI REST server**: [http://localhost:8000](http://localhost:8000)
*   **Interactive Swagger documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 2. Docker Containers Deployment

For production builds, OpenHuman builds separate packages for the API and frontend:

### Production Dockerfile (`apps/api/Dockerfile`)
The backend uses a multi-stage compilation layout:
1.  **Builder Stage**: Installs `uv`, copies the `pyproject.toml` definition, and compiles all packages into a virtual environment (`/app/.venv`) without developer dependencies.
2.  **Runtime Stage**: Employs a slim Python image, imports the compiled virtual environment, overrides the shell path to target `/app/.venv/bin`, copies the source modules (`app`, `alembic`, config), and starts the server via `uvicorn`.

### Example Docker Compose Config (`docker-compose.yml`)
To deploy OpenHuman as a self-hosted stack, use the following layout. Note the volume mounts for database data and Cognee graph databases to prevent memory loss:

```yaml
version: "3.8"

services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: openhuman-db
    environment:
      POSTGRES_DB: openhuman
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: production-password-here
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  backend:
    build:
      context: ./apps/api
      dockerfile: Dockerfile
    container_name: openhuman-api
    depends_on:
      - postgres
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:production-password-here@postgres:5432/openhuman
      JWT_SECRET_KEY: ${JWT_SECRET_KEY}
      ENCRYPTION_KEY: ${ENCRYPTION_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      COGNEE_DATA_DIR: /app/cognee_data
      STORAGE_BACKEND: s3
      S3_BUCKET_NAME: openhuman-uploads
      GATEWAY_ENABLED: "true"
      SLACK_IDENTITY_MODE: per_employee
    volumes:
      - cognee_data:/app/cognee_data
      - upload_data:/app/uploads
    ports:
      - "8000:8000"

  frontend:
    build:
      context: ./apps/web
    container_name: openhuman-web
    depends_on:
      - backend
    environment:
      NEXT_PUBLIC_API_URL: http://backend:8000
    ports:
      - "3000:3000"

volumes:
  pgdata:
  cognee_data:
  upload_data:
```

> [!WARNING]  
> Cognee relies on SQLite locks internally. When deploying the backend service, it is recommended to run a **single uvicorn worker thread** (`--workers 1` or one container replica) to avoid `database is locked` conflicts.

---

## 3. Environment Variables Reference

| Category | Variable | Default | Description |
| :--- | :--- | :--- | :--- |
| **Server** | `ENVIRONMENT` | `development` | Triggers strict validations if set to `production`. |
| | `API_HOST` | `0.0.0.0` | Bind host for FastAPI. |
| | `API_PORT` | `8000` | Bind port for FastAPI. |
| | `FRONTEND_URL` | `http://localhost:3000` | Core URL used in OAuth redirect callbacks. |
| **Database** | `DATABASE_URL` | `postgresql+asyncpg://...` | Connection URI. Needs vector extension. |
| | `CHECKPOINT_DATABASE_URL`| `""` | Connection string for checkpointer. |
| **Security** | `JWT_SECRET_KEY` | `change-me-in-production`| Token signing key. Must be >= 32 chars in production. |
| | `ENCRYPTION_KEY` | `""` | 32-byte hex string for AES bot tokens. |
| **Cognee** | `COGNEE_DATA_DIR` | `./cognee_data` | Storage folder for Kuzu graphs and vector files. |
| | `COGNEE_LLM_PROVIDER` | `openai` | LLM service provider name. |
| | `COGNEE_LLM_ENDPOINT` | `""` | Custom URL (e.g. OpenRouter endpoint). |
| | `COGNEE_LLM_API_KEY` | `""` | Key for memory indexing and summaries. |
| **Document** | `STORAGE_BACKEND` | `local` | `local` writes files to disk, `s3` writes to buckets. |
| | `S3_BUCKET_NAME` | `openhuman-uploads` | Target bucket when using `s3` backend. |
| **Gateway** | `GATEWAY_ENABLED` | `false` | Set to `true` to start Discord/Slack listeners. |
| | `SLACK_IDENTITY_MODE` | `shared` | `shared` (one bot/org) vs `per_employee` (one app/employee). |
