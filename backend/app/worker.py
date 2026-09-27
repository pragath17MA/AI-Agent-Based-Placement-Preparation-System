import os
from dotenv import load_dotenv

# Load environment variables from backend/.env relative to this file
base_dir = os.path.dirname(os.path.abspath(__file__))
backend_env = os.path.abspath(os.path.join(base_dir, "..", ".env"))
load_dotenv(backend_env)
load_dotenv() # Fallback to current working directory

from celery import Celery

# Initialize Celery application
celery = Celery(
    "placement_tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://redis:6379/0")
)

# Celery task configuration
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

@celery.task
def execute_code_async(language: str, code: str, inputs: str, expected: str, timeout_sec: float = 2.0):
    """
    Asynchronously executes code in Celery worker.
    """
    from app.services.executor import CodeExecutor
    return CodeExecutor.run_code(language, code, inputs, expected, timeout_sec)
