import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from measureme.database import Base

@pytest.fixture(scope="session")
def engine():
    # Use an in-memory SQLite database for blazing fast, isolated tests
    engine = create_engine("sqlite:///:memory:")
    return engine

@pytest.fixture(scope="function")
def tables(engine):
    # Setup tables before test
    Base.metadata.create_all(engine)
    yield
    # Tear down tables after test
    Base.metadata.drop_all(engine)

@pytest.fixture(scope="function")
def db_session(engine, tables):
    """Returns an sqlalchemy session, and after the test clears out."""
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
