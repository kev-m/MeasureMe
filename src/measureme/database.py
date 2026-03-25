from sqlalchemy import create_engine, event
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import sessionmaker
from .models import Base, IntradayMetricType, INTRADAY_METRIC_TYPE_SEED

def get_engine(db_url: str):
    """
    Create a SQLAlchemy engine.
    Examples:
        - SQLite: 'sqlite:///measureme.db'
        - MariaDB: 'mysql+pymysql://user:password@localhost/dbname'
    Enables SQLite foreign key constraints if using SQLite.
    """
    engine = create_engine(db_url, echo=False, connect_args={"check_same_thread": False} if 'sqlite' in db_url else {})

    # Enable foreign key constraints for SQLite
    if 'sqlite' in db_url:
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine

def init_db(engine):
    """
    Creates all tables described by the Base metadata.
    """
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            insert(IntradayMetricType)
            .values(INTRADAY_METRIC_TYPE_SEED)
            .on_conflict_do_nothing(index_elements=['id'])
        )    

def get_session_maker(engine):
    """
    Returns a configured sessionmaker for the given engine.
    """
    return sessionmaker(bind=engine)
