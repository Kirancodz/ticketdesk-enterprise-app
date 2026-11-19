# TicketDesk Enterprise — Enterprise IT Service Management Platform

**TicketDesk Enterprise** is a full-stack corporate IT Service Management (ITSM) platform built to manage the end-to-end lifecycle of technical support incidents, service requests, Service Level Agreements (SLAs), knowledge base articles, role-based access control, file attachments, operational analytics, and compliance audit trails.

---

## 1. Technology Stack

- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Lucide React Icons, React Router v6, TanStack Query v5, Recharts, React Hook Form, Zod, Vitest
- **Backend**: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.0 ORM, Alembic Migrations, PyJWT, Bcrypt, Boto3
- **Database**: PostgreSQL 16 (with full relational schema, foreign keys, and composite indexes)
- **File Storage**: Pluggable `StorageProvider` supporting local disk (`STORAGE_PROVIDER=local`) and Amazon S3 (`STORAGE_PROVIDER=s3`) with pre-signed download URLs
- **Serverless Integration**: AWS Lambda S3 `ObjectCreated` event processor (`lambda/file_processor/handler.py`) with structured JSON CloudWatch logging

---

## 2. Quick Start (Local Development)

### Option A: Docker Compose (PostgreSQL + Backend + Frontend)

For the container deployment, environment setup, and importing existing local
accounts/tickets, follow [Docker deployment](docs/docker_deployment.md).
The container frontend is served at `http://localhost:8080`.

```bash
# Configure .env.docker as described in docs/docker_deployment.md first
docker compose --env-file .env.docker up --build -d --wait
```

### Option B: Running Backend & Frontend Directly

1. **Backend Setup**:
   ```bash
   cd backend
   pip install -r requirements.txt
   alembic upgrade head
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   *(On startup, the backend automatically verifies schema tables and seeds realistic enterprise demo data if empty.)*

2. **Frontend Setup**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

3. **Access Application URLs**:
   - **Frontend Web App**: `http://localhost:5173`
   - **Swagger / OpenAPI UI**: `http://localhost:8000/docs`
   - **Backend Health Check**: `http://localhost:8000/health`

---

## 3. Development Demo Credentials

> **Note**: These credentials are for local evaluation and development only. Never use default demo credentials in production.

| Role | Full Name | Email | Password | Capabilities |
| :--- | :--- | :--- | :--- | :--- |
| **Administrator** | Evelyn Sterling | `admin@ticketdesk.enterprise` | `Admin@12345` | Full platform control: all tickets, User/Role/Team management, SLA configuration, Audit Logs, Reports, and System Settings |
| **IT Support Agent** | Alex Rivera | `alex.rivera@ticketdesk.enterprise` | `Agent@12345` | Support queue triage, accept/assign tickets, status & priority updates, internal notes, Knowledge Base authoring, Reports |
| **IT Support Agent** | Priya Nair | `priya.nair@ticketdesk.enterprise` | `Agent@12345` | Identity & Security (IAM) support queue and incident resolution |
| **IT Support Agent** | Marcus Vance | `marcus.vance@ticketdesk.enterprise` | `Agent@12345` | Workplace & Endpoint Engineering support queue |
| **Employee** | Sarah Chen | `sarah.chen@ticketdesk.enterprise` | `Employee@12345` | Submit tickets, upload attachments, add public comments, track SLA status, reopen resolved tickets, browse Knowledge Base |

---

## 4. Running Automated Tests

- **Backend & AWS Lambda Pytest Suite**:
  ```bash
  PYTHONPATH=backend pytest backend/tests/test_api.py lambda/file_processor/tests/test_handler.py -v
  ```
- **Frontend Vitest Component & Utility Suite**:
  ```bash
  cd frontend
  npm test
  ```

---

## 5. Documentation Index

- [System Architecture](docs/architecture.md)
- [Database Schema & ER Diagram](docs/database_schema.md)
- [REST API Documentation](docs/api_documentation.md)
- [Local & AWS Cloud Deployment Guide](docs/deployment_guide.md)


## Current workflow and local data

See [Workflow and session behavior](docs/workflow_and_sessions.md) for ticket acceptance, transfers, closed work segments, SLA monitoring, and account isolation. Apply all Alembic migrations before starting an existing database.

Local databases, uploads, `.env` files, runtime caches, and generated account/login exports in `outputs/` are excluded from version control. Department accounts and ticket scenarios created in a local database are not part of this source repository. Configure a fresh environment using `.env.example`; development seed accounts listed above do not describe accounts in an existing local database.
