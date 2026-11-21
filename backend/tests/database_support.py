import os
from uuid import uuid4

from sqlalchemy.engine import make_url

from app.database import build_engine


def test_engine(test, sqlite_url):
    if not (url := os.environ.get("TEST_DATABASE_URL")):
        engine = build_engine(make_url(sqlite_url))
        test.addCleanup(engine.dispose)
        return engine

    url = make_url(url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("TEST_DATABASE_URL must identify a PostgreSQL test database")
    schema = f"test_{uuid4().hex}"
    admin = build_engine(url)
    test.addCleanup(admin.dispose)
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')

    def drop_schema():
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')

    test.addCleanup(drop_schema)
    engine = build_engine(url.update_query_dict({"options": f"-csearch_path={schema}"}))
    test.addCleanup(engine.dispose)
    return engine
