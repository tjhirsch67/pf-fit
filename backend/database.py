"""Database engine, session factory, and FastAPI dependency.

Schema creation is owned by Alembic (`alembic upgrade head`), not `create_all` — see
Schema.md §14. `get_db` is the request-scoped session dependency used by every router.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

# Single declarative base shared by all ORM models and Alembic's autogenerate target.
Base = declarative_base()

engine = create_engine(
    settings.normalized_database_url,
    pool_pre_ping=True,   # transparently recycle connections dropped by Railway
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
