import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Load environment variables from backend/.env relative to this file
base_dir = os.path.dirname(os.path.abspath(__file__))
backend_env = os.path.abspath(os.path.join(base_dir, "..", ".env"))
load_dotenv(backend_env)
load_dotenv() # Fallback to current working directory

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./placement_prep.db")

# SQLite needs special connection parameters for multithreading
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
