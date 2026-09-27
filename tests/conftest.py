"""Shared pytest fixtures: isolated in-memory DB per test + TestClient."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.routers.redirect import redirect_rate_limiter
from app.routers.urls import create_rate_limiter, redirect_cache


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Reset shared in-process state between tests so tests don't leak into
    # each other (cache entries, rate-limit counters).
    redirect_cache._store.clear()
    create_rate_limiter.reset()
    redirect_rate_limiter.reset()

    from starlette.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
