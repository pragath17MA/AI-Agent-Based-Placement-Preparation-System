import pytest
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.models import User, UserProfile, UserResume
from sqlalchemy.orm import Session
import io

client = TestClient(app)

def test_resume_upload_success():
    resume_content = """
    John Doe
    Software Engineering Resume
    
    Skills:
    - Python
    - JavaScript
    - React
    - Node.js
    - Postgresql
    - Docker
    - FastAPI
    
    Experience:
    Google - Software Engineer Intern (2025)
    Worked on building high-performance backend pipelines in Python and FastAPI.
    
    Education:
    MIT - BS in Computer Science (2022-2026)
    """
    
    # Send mock upload file request
    file_payload = {"file": ("resume.txt", io.BytesIO(resume_content.encode("utf-8")), "text/plain")}
    response = client.post("/api/v1/resume/upload", files=file_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "resume.txt"
    assert "python" in data["skills"]
    assert "react" in data["skills"]
    assert data["current_skill_level"] == "Advanced"
    assert "Dynamic Programming" in data["weak_topics"]
    
def test_resume_inferred_beginner():
    resume_content = """
    Beginner Developer
    No experience
    Skills:
    - HTML
    - CSS
    """
    file_payload = {"file": ("beginner.txt", io.BytesIO(resume_content.encode("utf-8")), "text/plain")}
    response = client.post("/api/v1/resume/upload", files=file_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["current_skill_level"] == "Beginner"
    assert "Arrays" in data["weak_topics"]
