# TicketDesk Enterprise — Local & AWS Cloud Deployment Guide

## 1. Local Docker Compose Deployment

To run PostgreSQL 16, the FastAPI backend, and the React Vite frontend together in containers:

```bash
cp .env.example .env
docker compose up --build -d
```

- **Frontend Application**: `http://localhost:5173`
- **Backend API & Swagger Docs**: `http://localhost:8000/docs`
- **Backend Health Check**: `http://localhost:8000/health`

The development Compose ports bind to `127.0.0.1`. Development source mounts
are read-only inside the containers. Rebuild after dependency or frontend
configuration changes. The backend writes attachments to its named upload
volume as UID/GID `10001:10001`.

For an upload volume previously used by the root-run backend, back it up and
check it against the new image before switching the running deployment:

```powershell
docker compose run --rm --no-deps backend python -c "from pathlib import Path; import os; p=Path('/app/uploads'); assert all(os.access(d, os.R_OK | os.W_OK | os.X_OK) for d in [p, *(item for item in p.rglob('*') if item.is_dir())]); assert all(os.access(item, os.R_OK) for item in p.rglob('*') if item.is_file())"
```

If the check fails, restore or copy the attachment tree into a staging volume
owned by `10001:10001`, verify the data and access, then cut over to that volume.
Keep the original volume until the new deployment is verified.

## 2. Production database and backend startup

The local Compose file starts the development stack. For production, use the
release's backend image or Python environment with the approved production
settings. Run database migration once per release in a separate job using the
migration credential. Start API workers afterward with the runtime credential.

1. **Create or restore the target PostgreSQL database.** A fresh database starts
   with an empty application schema. For an existing database, inspect its
   current revision before selecting the upgrade path. Follow the reconciliation
   procedure below for a database previously initialized with `create_all()`.
2. **Back up existing data.** Take a database snapshot or a PostgreSQL dump and
   verify that it restores to an isolated database before upgrading the target.
   Stop application writers during the migration and cutover.
3. **Run the migration and stop on failure.** From `backend/` (the image uses
   `/app`), run the following PowerShell commands with the migration credential.
4. **Verify the current revision.** The second command below requires exactly
   one revision at head. This release's head is `0005_transfer_segment_closure`.

   ```powershell
   python -m alembic upgrade head
   if ($LASTEXITCODE -ne 0) { throw 'Alembic upgrade failed. Stop deployment.' }

   $currentRevision = @(python -m alembic current)
   if ($LASTEXITCODE -ne 0 -or $currentRevision.Count -ne 1 -or $currentRevision[0] -notmatch ' \(head\)$') {
       throw 'Database revision is not at Alembic head. Stop deployment.'
   }
   $currentRevision
   ```

5. **Start the production backend on a controlled network.** With the runtime
   credential and `APP_ENV=production`, launch the API:

   ```powershell
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

   Startup verifies connectivity and the revision, then fills missing built-in
   reference rows by their stable keys. Existing matching rows are preserved.
   A conflicting unique name can require an operator to reconcile the existing
   reference records. Production starts without demo users or demo articles.
6. **Provision the first administrator on a fresh deployment.** From an
   authorized interactive shell in `backend/`, using the backend runtime
   configuration, substitute the actual administrator's identity:

   ```powershell
   python -m app.bootstrap_admin --email 'operator@example.com' --full-name 'TicketDesk Administrator'
   ```

   Enter a unique password of at least 16 characters and at most 72 UTF-8 bytes
   at the hidden prompts. For an existing installation with an administrator,
   use its approved account and skip bootstrap. Review development imports for
   pre-existing demo accounts before exposing the service.
7. **Verify readiness and administrator login before routing user traffic.**
   Check that `/health` returns HTTP 200 with `database.schema` set to
   `current`, then sign in and confirm an administrator-only page opens. A
   database outage or a revision mismatch yields HTTP 503.

### Production containers

Use `compose.production.yml` separately from the development Compose file.
Set `TICKETDESK_RUNTIME_ENV_FILE` to a restricted file outside the repository
containing the real runtime settings, including `DATABASE_URL`, `SECRET_KEY`,
and `BACKEND_CORS_ORIGINS=[]` for the same-origin Nginx proxy. Compose forces
`APP_ENV=production` and `DEBUG=false`. Use a separate migration credential
when available. If `DATABASE_URL` is set in the operator's shell to the migration
URL, the one-shot commands can pass it through by variable name:

```powershell
docker compose -f compose.production.yml build
if ($LASTEXITCODE -ne 0) { throw 'Container build failed.' }
docker compose -f compose.production.yml run --rm --no-deps -e DATABASE_URL backend python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Alembic upgrade failed. Stop deployment.' }
$currentRevision = @(docker compose -f compose.production.yml run --rm --no-deps -e DATABASE_URL backend python -m alembic current)
if ($LASTEXITCODE -ne 0 -or $currentRevision.Count -ne 1 -or $currentRevision[0] -notmatch ' \(head\)$') {
    throw 'Database revision is not at Alembic head. Stop deployment.'
}
docker compose -f compose.production.yml up -d --wait
if ($LASTEXITCODE -ne 0) { throw 'Production services did not become healthy.' }
```

Run the administrator bootstrap interactively with
`docker compose -f compose.production.yml exec backend python -m app.bootstrap_admin`
and the identity flags shown above. Nginx serves the compiled UI and proxies
`/api/` to FastAPI. The only published port is the Nginx listener on
`127.0.0.1:8080` by default. Put a separately configured HTTPS ingress in front
of it for remote access. PostgreSQL is supplied separately and the API has no
host port. The Nginx upload limit is 12 MiB to accommodate the API's default
10 MiB limit plus multipart framing. Review both limits if changing upload size.

### Reconcile a database previously initialized with `create_all()`

Run `python -m alembic current` and inventory the schema and data on an isolated
restore of the backup. Compare tables, columns, indexes, foreign keys and unique
constraints against a clean database upgraded through the existing Alembic chain.
Review data effects too, including stable account identities and the transfer
closure normalization. A schema-only match cannot establish that those data
migrations ran.

If the schema or data state is uncertain, create a fresh Alembic-managed target,
rehearse a verified data import, and validate relationships, row counts,
sequences, sessions, and attachment references before cutover. If the restored
copy matches a specific historical revision and its data effects can be proven,
review a manual reconciliation and rehearse the remaining upgrades on that
copy before changing the live database. Never automatically stamp an unmanaged
database. Preserve the original backup for rollback.

## 3. AWS Cloud Deployment Guide (EC2 + RDS + S3 + Lambda + CloudWatch)

### Step 1: Amazon RDS for PostgreSQL
1. Provision an **Amazon RDS PostgreSQL 16** instance inside private subnets.
2. Allow inbound TCP `5432` from the EC2 Security Group only.
3. Configure `DATABASE_URL` on EC2:
   ```ini
   DATABASE_URL=postgresql+psycopg://<db_user>:<db_password>@<rds-endpoint>:5432/ticketdesk_db
   ```

### Step 2: Amazon S3 Private Attachment Bucket & IAM Role
1. Create a private S3 bucket (e.g., `ticketdesk-enterprise-attachments-prod`) with **Block All Public Access** enabled and **SSE-S3 (AES-256)** encryption.
2. Attach an **IAM Instance Profile** to your EC2 instance with least-privilege permissions (`s3:PutObject`, `s3:GetObject` on `arn:aws:s3:::ticketdesk-enterprise-attachments-prod/*`). Never hardcode AWS access keys on the server.
3. Set environment variables on the backend:
   ```ini
   APP_ENV=production
   STORAGE_PROVIDER=s3
   AWS_REGION=us-east-1
   S3_BUCKET_NAME=ticketdesk-enterprise-attachments-prod
   S3_PRESIGNED_URL_EXPIRATION=3600
   ```

### Step 3: AWS Lambda S3 File Processor & CloudWatch Logs
1. Package `lambda/file_processor/handler.py` into an AWS Lambda function (`python3.12` runtime, handler `handler.lambda_handler`).
2. Configure an **Amazon S3 Event Notification** on your attachment bucket for `s3:ObjectCreated:*` events targeting the Lambda function.
3. Attach the `AWSLambdaBasicExecutionRole` managed policy so the function writes structured JSON processing logs (`bucket`, `object_key`, `file_size_bytes`, `status`) directly to **Amazon CloudWatch Logs**.
