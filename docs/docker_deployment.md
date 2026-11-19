# Docker deployment

The stack runs PostgreSQL 16, FastAPI and a built React application served by
Nginx. Nginx proxies `/api/` to the backend, so the browser uses one origin.
There are no development source mounts or Vite development servers in the stack.

## Start a fresh installation

Install and start Docker Desktop with the Linux container engine. Create an
ignored `.env.docker` file in the repository root:

```dotenv
POSTGRES_USER=ticketdesk
POSTGRES_PASSWORD=REPLACE_WITH_A_RANDOM_ALPHANUMERIC_SECRET
POSTGRES_DB=ticketdesk_db
SECRET_KEY=REPLACE_WITH_A_LONG_RANDOM_SECRET
APP_ENV=production
FRONTEND_PORT=8080
BACKEND_PORT=8001
```

Use random hexadecimal database passwords so the database URL needs no escaping.
Then run:

```bash
docker compose --env-file .env.docker up -d --build --wait
docker compose --env-file .env.docker ps
```

Open `http://localhost:8080`. The API documentation is available at
`http://localhost:8001/docs`. PostgreSQL is reachable only on the Compose network.
The backend applies Alembic migrations before starting. Health checks ensure
PostgreSQL is ready before the API, and the API is ready before the frontend.
For remote hosting, add a domain and HTTPS through a reverse proxy.

## Preserve an existing local SQLite installation

Stop writes to the local application and use SQLite's backup API to create a
consistent backup. Preserve the original database and uploads as rollback data.
Build the images and start only `db`, then run migrations before importing:

```bash
docker compose --env-file .env.docker build
docker compose --env-file .env.docker up -d --wait db
docker compose --env-file .env.docker run --rm --no-deps backend alembic upgrade head
docker compose --env-file .env.docker run --rm --no-deps -v /absolute/path/to/backup.db:/migration/source.db:ro backend python -m scripts.import_sqlite /migration/source.db
```

The importer refuses any nonempty application table, verifies every copied
value, resets PostgreSQL sequences, and commits all application rows together.
Do not start the API before importing: startup initialization can populate a
fresh database. Copy existing upload files into the `backend_uploads` volume
before starting the full stack. The database import does not copy attachments.
Account passwords and ticket data remain unchanged. A new deployment JWT secret
requires users to sign in again.

## Manage the stack

```bash
docker compose --env-file .env.docker logs --tail=100 backend
docker compose --env-file .env.docker stop
docker compose --env-file .env.docker up -d --wait
```

Database and uploads persist in named Docker volumes. Keep `.env.docker` private
and back up both volumes. Do not use `docker compose down -v` when retaining data.
