from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

class Base(DeclarativeBase):
    pass

url = settings().database_url
if url.startswith('postgres://'):
    url = 'postgresql://' + url[11:]
if url.startswith('postgresql://'):
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
engine = create_engine(url, pool_pre_ping=True, pool_size=5 if not url.startswith('sqlite') else 5, connect_args={'check_same_thread': False} if url.startswith('sqlite') else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def get_db():
    with SessionLocal() as db:
        yield db
