from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.api.v1 import api_router
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine, get_db
import app.services.ticket_log_sync  # Register history synchronization
from app.core.exceptions import register_exception_handlers
from app.core.logging_config import logger
from app.core.schema import SchemaNotCurrent, require_current_schema
from app.services.seed_service import initialize_reference_data, seed_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} ({settings.APP_ENV})...")
    if settings.APP_ENV == "production":
        try:
            with SessionLocal.begin() as db:
                require_current_schema(db.connection())
                initialize_reference_data(db)
        except SchemaNotCurrent:
            raise
        except Exception:
            logger.error("Production database initialization failed", exc_info=True)
            raise RuntimeError("Production database initialization failed. Check connectivity and reference data.") from None
    else:
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            try:
                seed_database(db)
            except Exception:
                logger.error("Database initialization/seeding error", exc_info=True)
    yield
    logger.info(f"Shutting down {settings.APP_NAME}...")


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Enterprise IT Service Management (ITSM) Platform API — "
        "Full-lifecycle incident & service request management, SLA tracking, "
        "role-based access control, knowledge base, analytics, audit trail, and AWS S3/Lambda integration."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"])
@app.get(f"{settings.API_V1_STR}/health", tags=["Health"])
def health_check(response: Response, db: Session = Depends(get_db)) -> dict:
    db_status = "healthy"
    schema_status = "unchecked"
    db_dialect = engine.dialect.name
    try:
        db.execute(text("SELECT 1"))
        if settings.APP_ENV == "production":
            require_current_schema(db.connection())
            schema_status = "current"
    except SchemaNotCurrent:
        schema_status = "out_of_date"
    except Exception:
        logger.error("Health check DB error", exc_info=True)
        db_status = "unhealthy"

    ready = db_status == "healthy" and schema_status != "out_of_date"
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if ready else "degraded",
        "service": settings.APP_NAME,
        "version": "1.0.0",
        "environment": settings.APP_ENV,
        "database": {
            "status": db_status,
            "engine": db_dialect,
            "schema": schema_status,
        },
        "storage": {
            "provider": settings.STORAGE_PROVIDER,
            "s3_bucket": settings.S3_BUCKET_NAME if settings.STORAGE_PROVIDER == "s3" else None,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
