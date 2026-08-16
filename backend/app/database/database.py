from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
import os
from pathlib import Path

# Charge environment variables from .env file
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# obtain database connection parameters from environment variables
MYSQL_USER = os.getenv("DB_USER")
MYSQL_PASSWORD = os.getenv("DB_PASS")
MYSQL_HOST = os.getenv("DB_HOST")
MYSQL_PORT = os.getenv("DB_PORT")
MYSQL_DATABASE = os.getenv("DB_NAME")

# Build connection URL with or without password
if MYSQL_PASSWORD:
    SQLALCHEMY_DATABASE_URL = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
    )
else:
    SQLALCHEMY_DATABASE_URL = (
        f"mysql+pymysql://{MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
    )

# Create SQLAlchemy engine and session
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base for models
Base = declarative_base()
