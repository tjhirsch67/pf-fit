"""Database engine, session factory, and FastAPI dependency.

Schema creation is owned by Alembic (`alembic upgrade head`), not `create_all` — see
Schema.md §14. `get_db` is the request-scoped session dependency used by every router.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

# Single declarative base shared by all ORM models and Alembic's autogenerate target.
Base = declarative_base()

# Engine creation is guarded so the ORM models (and the pure progress engine that imports
# their enum vocabulary) stay importable without a DATABASE_URL — e.g. in unit tests. The
# engine is only actually needed when a request hits the DB or Alembic runs.
_url = settings.normalized_database_url
engine = (
    create_engine(_url, pool_pre_ping=True, future=True)  # pool_pre_ping: recycle dropped Railway conns
    if _url
    else None
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
