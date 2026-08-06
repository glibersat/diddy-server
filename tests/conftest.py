import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import User


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def user(db_session):
    u = User(email="ada@example.com", timezone="Europe/Paris")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u
