from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

def get_engine(db_url: str):
    """
    Create a SQLAlchemy engine.
    Examples:
        - SQLite: 'sqlite:///measureme.db'
        - MariaDB: 'mysql+pymysql://user:password@localhost/dbname'
    """
    return create_engine(db_url, echo=False)

def init_db(engine):
    """
    Creates all tables described by the Base metadata.
    """
    Base.metadata.create_all(engine)

def get_session_maker(engine):
    """
    Returns a configured sessionmaker for the given engine.
    """
    return sessionmaker(bind=engine)
