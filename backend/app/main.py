import os
import json
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import time
import random

from app.database import engine, get_db, Base
from app.models import (
    User, UserProfile, Problem, TestCase, UserSubmission, 
    InterviewSession, InterviewDialogue, UserResume,
    ChatSession, ChatMessage, InterviewScore, Recommendation, LeaderboardEntry
)
from app.services.executor import CodeExecutor
from app.services.agents import (
    ProblemRecommender, InterviewState, create_interview_workflow, 
    process_user_dialogue, LLMService
)

app = FastAPI(title="Placement Preparation Agent API", version="1.1.0")

# Simple In-Memory Caching & Rate Limiting (Fallback for Redis/SlowAPI)
class AppCache:
    def __init__(self):
        self.cache = {}
        self.rate_limits = {}

    def get(self, key):
        if key in self.cache:
            entry = self.cache[key]
            if entry["expires"] > time.time():
                return entry["data"]
            else:
                del self.cache[key]
        return None

    def set(self, key, data, ttl=60):
        self.cache[key] = {"data": data, "expires": time.time() + ttl}
        
    def check_rate_limit(self, ip: str, endpoint: str, limit: int, window: int) -> bool:
        key = f"rate_{ip}_{endpoint}"
        now = time.time()
        if key not in self.rate_limits:
            self.rate_limits[key] = {"count": 1, "start": now}
            return True
        record = self.rate_limits[key]
        if now - record["start"] > window:
            self.rate_limits[key] = {"count": 1, "start": now}
            return True
        if record["count"] >= limit:
            return False
        record["count"] += 1
        return True

app_cache = AppCache()

# Enable CORS for frontend workspace access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize DB tables automatically on startup and perform self-healing SQLite check
@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    try:
        from sqlalchemy import text
        from app.database import SessionLocal
        db = SessionLocal()
        
        # Self-healing migration for SQLite/Postgres: add problem_id to interview_sessions if missing
        try:
            db.execute(text("ALTER TABLE interview_sessions ADD COLUMN problem_id VARCHAR(36) REFERENCES problems(id) ON DELETE SET NULL"))
            db.commit()
            print("Successfully migrated sqlite DB: added problem_id to interview_sessions")
        except Exception:
            db.rollback()

        # Self-healing migration for Problem model metadata columns (Phase 2 upgrades)
        cols_to_add = [
            ("tags", "JSON"),
            ("companies", "JSON"),
            ("constraints", "JSON"),
            ("examples", "JSON"),
            ("hints", "JSON"),
            ("editorial", "TEXT"),
            ("optimal_solution", "TEXT"),
            ("time_complexity", "VARCHAR(100)"),
            ("space_complexity", "VARCHAR(100)")
        ]
        for col_name, col_type in cols_to_add:
            try:
                db.execute(text(f"ALTER TABLE problems ADD COLUMN {col_name} {col_type}"))
                db.commit()
                print(f"Self-healing database: Added column {col_name} to problems table.")
            except Exception:
                db.rollback()

        count = db.query(Problem).count()
        db.close()
        if count == 0:
            print("Problems table is empty. Running seed_db...")
            from seed import seed_db
            seed_db()
    except Exception as e:
        print(f"Auto-seed / migration check failed: {e}")


# ----------------------------------------------------
# 1. Pydantic Models for Input Validation
# ----------------------------------------------------
class RegisterRequest(BaseModel):
    email: str
    password: str

class ResumeUploadResponse(BaseModel):
    filename: str
    skills: List[str]
    experience: Optional[str] = None
    education: Optional[str] = None
    weak_topics: List[str]
    current_skill_level: str

class LoginRequest(BaseModel):
    email: str
    password: str

class CodeExecutionRequest(BaseModel):
    problem_id: str
    language: str
    code: str

class RecommendationRequest(BaseModel):
    user_skill: str
    weak_topics: List[str]

class StartInterviewRequest(BaseModel):
    user_id: str
    topic: str
    difficulty: str
    model: Optional[str] = None

class DialogRequest(BaseModel):
    session_id: str
    user_message: str
    user_code: Optional[str] = None
    model: Optional[str] = None

class EndInterviewRequest(BaseModel):
    session_id: str
    user_code: Optional[str] = None

class ChatStartRequest(BaseModel):
    user_id: str
    title: Optional[str] = "New Conversation"

class ChatMessageRequest(BaseModel):
    session_id: str
    message: str
    provider: Optional[str] = None


# ----------------------------------------------------
# 2. Database Sync Helpers
# ----------------------------------------------------
def get_or_create_user(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        if user_id == "anonymous":
            user = User(
                id="anonymous",
                email="anonymous@example.com",
                password_hash=hash_password("anonymous_secure_pass")
            )
            db.add(user)
            db.flush()
            
            profile = UserProfile(
                user_id=user.id,
                current_skill_level="Beginner",
                weak_topics=["Arrays", "Searching"]
            )
            db.add(profile)
            db.commit()
        else:
            user = User(
                id=user_id,
                email=f"{user_id}@example.com",
                password_hash=hash_password("default_secure_pass")
            )
            db.add(user)
            db.flush()
            
            profile = UserProfile(
                user_id=user.id,
                current_skill_level="Beginner",
                weak_topics=["Arrays", "Searching"]
            )
            db.add(profile)
            db.commit()
    return user

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def sync_leaderboard(db: Session, user_id: str):
    try:
        # Calculate solved count
        solved_count = db.query(UserSubmission).filter(
            UserSubmission.user_id == user_id,
            UserSubmission.status == "ACCEPTED"
        ).distinct(UserSubmission.problem_id).count()
        
        # Calculate average interview score
        interviews = db.query(InterviewSession).filter(
            InterviewSession.user_id == user_id,
            InterviewSession.status == "COMPLETED",
            InterviewSession.overall_score.isnot(None)
        ).all()
        avg_score = sum(i.overall_score for i in interviews) / len(interviews) if interviews else 0.0

        # Calculate streak
        submissions = db.query(UserSubmission).filter(UserSubmission.user_id == user_id).order_by(UserSubmission.created_at.desc()).all()
        streak = 0
        if submissions:
            dates = sorted(list(set(s.created_at.date() for s in submissions)), reverse=True)
            from datetime import date, timedelta
            current_date = date.today()
            if dates[0] == current_date or dates[0] == current_date - timedelta(days=1):
                streak = 1
                expected_date = dates[0] - timedelta(days=1)
                for d in dates[1:]:
                    if d == expected_date:
                        streak += 1
                        expected_date = d - timedelta(days=1)
                    elif d > expected_date:
                        continue
                    else:
                        break
        
        # Find primary language
        from sqlalchemy import func
        lang_query = db.query(
            UserSubmission.language, 
            func.count(UserSubmission.language).label('qty')
        ).filter(UserSubmission.user_id == user_id).group_by(UserSubmission.language).order_by(func.count(UserSubmission.language).desc()).first()
        primary_lang = lang_query[0] if lang_query else "Python"

        user = db.query(User).filter(User.id == user_id).first()
        name = user.email.split('@')[0] if user else "Anonymous"
        if user_id == "anonymous":
            name = "Anonymous (You)"

        leader = db.query(LeaderboardEntry).filter(LeaderboardEntry.user_id == user_id).first()
        if not leader:
            leader = LeaderboardEntry(user_id=user_id)
            db.add(leader)
        
        leader.name = name
        leader.solved = solved_count
        leader.avg_score = round(avg_score, 1)
        leader.streak = streak
        leader.language = primary_lang.capitalize()
        leader.status = "Preparing" if avg_score < 7.5 else ("Interviewing" if avg_score < 8.8 else "Available")
        db.commit()
    except Exception as e:
        print(f"Error syncing leaderboard entry: {e}")
        db.rollback()


# ----------------------------------------------------
# 3. REST API Routes
# ----------------------------------------------------
@app.get("/health")
def health_check():
    return {"status": "healthy", "time": datetime.utcnow().isoformat()}

# LLM Providers Diagnostic API
@app.get("/api/v1/providers")
def list_providers():
    providers_status = {}
    keys = {
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "groq": "GROQ_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "openrouter": "OPENROUTER_API_KEY"
    }
    for provider, env_var in keys.items():
        val = os.getenv(env_var)
        providers_status[provider] = bool(val and "your_" not in val.lower() and "YOUR_" not in val)
    
    # Check Ollama
    try:
        import httpx
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        res = httpx.get(f"{ollama_host}/api/tags", timeout=1.0)
        providers_status["ollama"] = res.status_code == 200
    except Exception:
        providers_status["ollama"] = False

    return providers_status

# Authentication & Registration
@app.post("/api/v1/auth/register", status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        email=req.email,
        password_hash=hash_password(req.password)
    )
    db.add(new_user)
    db.flush()

    profile = UserProfile(
        user_id=new_user.id,
        current_skill_level="Beginner",
        weak_topics=["Arrays", "Searching"]
    )
    db.add(profile)
    db.commit()

    return {"message": "User registered successfully", "user_id": new_user.id}

@app.post("/api/v1/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    hashed = hash_password(req.password)
    user = db.query(User).filter(User.email == req.email, User.password_hash == hashed).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    return {
        "message": "Login successful",
        "user_id": user.id,
        "email": user.email,
        "token": f"mock_jwt_token_{user.id}"
    }

# Problem Repository
@app.get("/api/v1/problems")
def list_problems(db: Session = Depends(get_db)):
    cached = app_cache.get("all_problems")
    if cached:
        return cached
    problems = db.query(Problem).all()
    result = [{"id": p.id, "title": p.title, "difficulty": p.difficulty, "category": p.category} for p in problems]
    app_cache.set("all_problems", result, ttl=120)
    return result

@app.get("/api/v1/problems/{problem_id}")
def get_problem(problem_id: str, db: Session = Depends(get_db)):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
    
    test_cases = db.query(TestCase).filter(TestCase.problem_id == problem_id, TestCase.is_hidden == False).all()
    
    return {
        "id": problem.id,
        "title": problem.title,
        "description": problem.description,
        "difficulty": problem.difficulty,
        "category": problem.category,
        "time_limit_ms": problem.time_limit_ms,
        "memory_limit_mb": problem.memory_limit_mb,
        "template_code": problem.template_code,
        "sample_test_cases": [{"input": tc.input_data, "output": tc.expected_output} for tc in test_cases]
    }

# Code Executor API
@app.post("/api/v1/execute")
def execute_code(req: CodeExecutionRequest, db: Session = Depends(get_db)):
    if not app_cache.check_rate_limit("user", "execute", limit=15, window=60):
        raise HTTPException(status_code=429, detail="Too many execution requests. Please wait.")
        
    problem = db.query(Problem).filter(Problem.id == req.problem_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
    
    test_cases = db.query(TestCase).filter(TestCase.problem_id == req.problem_id).all()
    if not test_cases:
        raise HTTPException(status_code=400, detail="No test cases found for this problem")

    results = []
    all_passed = True
    total_time_ms = 0.0
    
    for tc in test_cases:
        res = CodeExecutor.run_code(
            language=req.language,
            code=req.code,
            inputs=tc.input_data,
            expected=tc.expected_output,
            timeout_sec=float(problem.time_limit_ms) / 1000.0
        )
        total_time_ms += res.get("execution_time_ms", 0.0)
        
        results.append({
            "test_case_id": tc.id,
            "input": tc.input_data,
            "expected": tc.expected_output,
            "actual": res.get("actual", ""),
            "status": res["status"],
            "passed": res["passed"],
            "stdout": res.get("stdout", ""),
            "stderr": res.get("stderr", "")
        })
        
        if not res["passed"]:
            all_passed = False

    overall_status = "ACCEPTED" if all_passed else "WRONG_ANSWER"
    
    default_user = db.query(User).first()
    user_id = default_user.id if default_user else "anonymous"
    
    sub = UserSubmission(
        user_id=user_id,
        problem_id=req.problem_id,
        code=req.code,
        language=req.language,
        status=overall_status,
        execution_time_ms=int(total_time_ms / len(test_cases)) if test_cases else 0,
        memory_used_mb=24
    )
    db.add(sub)
    db.commit()

    # Sync leaderboard solved stats
    sync_leaderboard(db, user_id)

    return {
        "status": overall_status,
        "total_test_cases": len(test_cases),
        "passed_count": sum(1 for r in results if r["passed"]),
        "results": results
    }

# Recommendation API
@app.post("/api/v1/problems/recommend")
def recommend_problem(req: RecommendationRequest):
    rec = ProblemRecommender.get_recommendation(req.user_skill, req.weak_topics)
    return rec

# Start Mock Interview Session
@app.post("/api/v1/interviews/start")
async def start_interview(req: StartInterviewRequest, db: Session = Depends(get_db)):
    get_or_create_user(db, req.user_id)
    profile = db.query(UserProfile).filter(UserProfile.user_id == req.user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")

    # Dynamic unseen question generation: query users' past attempts to avoid repeats
    past_sessions = db.query(InterviewSession).filter(
        InterviewSession.user_id == req.user_id,
        InterviewSession.problem_id.isnot(None)
    ).all()
    seen_ids = [s.problem_id for s in past_sessions]

    is_non_coding = req.topic.lower() in [
        "system design", "low level design", "behavioral", "hr", "behavioral interview", "hr interview",
        "operating systems", "dbms", "sql", "computer networks", "oop", "core cs"
    ]

    problem_title = ""
    problem_desc = ""
    problem_id = ""
    template_code = {}

    if is_non_coding:
        # Verbal dynamic interview
        problem_id = "non-coding"
        problem_title = f"{req.topic} Concept Session"
        problem_desc = f"Conducting a professional technical discussion on: {req.topic} ({req.difficulty} difficulty)."
    else:
        # Coding challenge
        query = db.query(Problem).filter(Problem.difficulty == req.difficulty)
        if req.topic and req.topic not in ("Data Structures & Algorithms", "Random Mix"):
            query = query.filter(Problem.category.like(f"%{req.topic}%"))
        
        candidates = query.all()
        unseen = [p for p in candidates if p.id not in seen_ids]
        
        if unseen:
            selected_problem = random.choice(unseen)
        elif candidates:
            selected_problem = random.choice(candidates)
        else:
            selected_problem = db.query(Problem).first()

        if not selected_problem:
            raise HTTPException(status_code=500, detail="No problems found in database. Seed problems first.")

        problem_id = selected_problem.id
        problem_title = selected_problem.title
        problem_desc = selected_problem.description
        template_code = selected_problem.template_code

    session = InterviewSession(
        user_id=req.user_id,
        problem_id=None if is_non_coding else problem_id,
        topic=req.topic,
        status="ACTIVE"
    )
    db.add(session)
    db.flush()

    # Initial Agentic InterviewState
    state: InterviewState = {
        "session_id": session.id,
        "problem_id": problem_id,
        "problem_title": problem_title,
        "problem_description": problem_desc,
        "chat_history": [],
        "user_code": template_code.get("python", "") if not is_non_coding else "",
        "hint_count": 0,
        "current_node": "init",
        "execution_result": None,
        "final_feedback": None,
        "overall_score": None,
        "status": "ACTIVE",
        "model": req.model,
        "topic": req.topic,
        "difficulty": req.difficulty,
        "time_started": time.time(),
        "live_evaluation": None
    }

    workflow = create_interview_workflow()
    new_state = await workflow.ainvoke(state)

    for message in new_state["chat_history"]:
        dial = InterviewDialogue(
            session_id=session.id,
            speaker=message["speaker"],
            message=message["message"]
        )
        db.add(dial)
    db.commit()

    return {
        "session_id": session.id,
        "topic": req.topic,
        "difficulty": req.difficulty,
        "problem": {
            "id": problem_id,
            "title": problem_title,
            "description": problem_desc,
            "template_code": template_code
        },
        "initial_message": new_state["chat_history"][-1]["message"] if new_state["chat_history"] else "Welcome to your mock interview."
    }

# Dynamic dialogue response endpoint
@app.post("/api/v1/interviews/respond")
async def respond_interview(req: DialogRequest, db: Session = Depends(get_db)):
    if not app_cache.check_rate_limit("user", "interview", limit=10, window=10):
        raise HTTPException(status_code=429, detail="Rate limit exceeded for agent interactions.")
        
    session = db.query(InterviewSession).filter(InterviewSession.id == req.session_id).first()
    if not session or session.status == "COMPLETED":
        raise HTTPException(status_code=400, detail="Session invalid or already completed")

    # Fetch dialogues history
    dialogues = db.query(InterviewDialogue).filter(InterviewDialogue.session_id == req.session_id).all()
    chat_history = [{"speaker": d.speaker, "message": d.message} for d in dialogues]

    user_msg_log = InterviewDialogue(
        session_id=req.session_id,
        speaker="USER",
        message=req.user_message,
        code_submitted=req.user_code
    )
    db.add(user_msg_log)
    db.commit()

    chat_history.append({"speaker": "USER", "message": req.user_message})
    
    is_non_coding = session.topic.lower() in [
        "system design", "low level design", "behavioral", "hr", "behavioral interview", "hr interview",
        "operating systems", "dbms", "sql", "computer networks", "oop", "core cs"
    ] or session.problem_id is None

    if is_non_coding:
        problem_title = f"{session.topic} Discussion"
        problem_desc = f"Conducting a deep-dive interview on {session.topic}."
        problem_id = "non-coding"
    else:
        problem = db.query(Problem).filter(Problem.id == session.problem_id).first()
        problem_title = problem.title if problem else "Coding challenge"
        problem_desc = problem.description if problem else ""
        problem_id = session.problem_id

    hint_count = sum(1 for h in chat_history if h["speaker"] == "INTERVIEWER" and "hint" in h["message"].lower())

    state: InterviewState = {
        "session_id": req.session_id,
        "problem_id": problem_id,
        "problem_title": problem_title,
        "problem_description": problem_desc,
        "chat_history": chat_history,
        "user_code": req.user_code if req.user_code else "",
        "hint_count": hint_count,
        "current_node": "evaluate_code" if (req.user_code and not is_non_coding) else "interviewer_turn",
        "execution_result": None,
        "final_feedback": None,
        "overall_score": None,
        "status": "ACTIVE",
        "model": req.model,
        "topic": session.topic,
        "difficulty": "Easy",
        "time_started": time.time(),
        "live_evaluation": None
    }

    workflow = create_interview_workflow()
    new_state = await workflow.ainvoke(state)

    last_msg = new_state["chat_history"][-1]
    interviewer_msg_log = InterviewDialogue(
        session_id=req.session_id,
        speaker=last_msg["speaker"],
        message=last_msg["message"]
    )
    db.add(interviewer_msg_log)
    
    if new_state.get("status") == "COMPLETED":
        session.status = "COMPLETED"
        session.overall_score = new_state.get("overall_score", 8.0)
        session.final_feedback = new_state.get("final_feedback", "Interview finished.")
        session.ended_at = datetime.utcnow()
        sync_leaderboard(db, session.user_id)
    
    db.commit()

    # Load latest scores record to return to client
    scores_entry = db.query(InterviewScore).filter(InterviewScore.session_id == req.session_id).first()
    live_scores = None
    if scores_entry:
        live_scores = {
            "communication": scores_entry.communication,
            "confidence": scores_entry.confidence,
            "technical_knowledge": scores_entry.technical_knowledge,
            "problem_solving": scores_entry.problem_solving,
            "coding_style": scores_entry.coding_style,
            "optimization": scores_entry.optimization,
            "time_complexity": scores_entry.time_complexity,
            "space_complexity": scores_entry.space_complexity,
            "edge_cases": scores_entry.edge_cases,
            "code_quality": scores_entry.code_quality,
            "feedback": scores_entry.feedback
        }

    return {
        "status": session.status,
        "response_message": last_msg["message"],
        "overall_score": session.overall_score,
        "final_feedback": session.final_feedback,
        "live_evaluation": live_scores
    }

# End Interview Session API
@app.post("/api/v1/interviews/end")
def end_interview(req: EndInterviewRequest, db: Session = Depends(get_db)):
    session = db.query(InterviewSession).filter(InterviewSession.id == req.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")
        
    if session.status != "COMPLETED":
        if req.user_code:
            user_msg_log = InterviewDialogue(
                session_id=req.session_id,
                speaker="USER",
                message="Submitting final code and concluding interview.",
                code_submitted=req.user_code
            )
            db.add(user_msg_log)
            db.commit()

        session.status = "COMPLETED"
        session.ended_at = datetime.utcnow()
        
        dialogues = db.query(InterviewDialogue).filter(InterviewDialogue.session_id == req.session_id).all()
        chat_history = [{"speaker": d.speaker, "message": d.message} for d in dialogues]
        
        hint_count = sum(1 for h in chat_history if h["speaker"] == "INTERVIEWER" and "hint" in h["message"].lower())
        
        state: InterviewState = {
            "session_id": req.session_id,
            "problem_id": session.problem_id or "non-coding",
            "problem_title": "Active Problem",
            "problem_description": "",
            "chat_history": chat_history,
            "user_code": req.user_code or "",
            "hint_count": hint_count,
            "current_node": "conclude_interview",
            "execution_result": None,
            "final_feedback": None,
            "overall_score": None,
            "status": "COMPLETED",
            "model": "openai",
            "topic": session.topic,
            "difficulty": "Easy",
            "time_started": time.time(),
            "live_evaluation": None
        }
        
        try:
            from app.services.agents import grade_session
            res_state = grade_session(state)
            session.overall_score = res_state.get("overall_score", 8.0)
            session.final_feedback = res_state.get("final_feedback", "Interview completed.")
        except Exception:
            session.overall_score = 7.5
            session.final_feedback = "Completed successfully."
            
        db.commit()
        sync_leaderboard(db, session.user_id)
        
    return {
        "status": session.status,
        "overall_score": session.overall_score,
        "final_feedback": session.final_feedback
    }

# Retrieve detailed calibration final report
@app.get("/api/v1/interviews/{session_id}/report")
def get_interview_report(session_id: str, db: Session = Depends(get_db)):
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")
    
    # Try parsing complete JSON structure from final_feedback
    try:
        report_data = json.loads(session.final_feedback)
    except Exception:
        # Fallback raw string data wrap
        report_data = {
            "overall_score": session.overall_score or 7.0,
            "scores": {
                "communication": 7.0,
                "confidence": 7.0,
                "technical_knowledge": 7.0,
                "problem_solving": 7.0,
                "coding_style": 7.0,
                "optimization": 7.0,
                "time_complexity": 7.0,
                "space_complexity": 7.0,
                "edge_cases": 7.0,
                "code_quality": 7.0
            },
            "strengths": ["Clear communication", "Structured approach"],
            "weaknesses": ["Minor timing optimizations"],
            "final_feedback": session.final_feedback or "Completed.",
            "topic_scores": {"Data Structures": 7.0, "Algorithms": 7.0, "Communication": 7.0, "Systems/Core CS": 7.0},
            "recommendations": {
                "problems": [{"title": "Two Sum", "difficulty": "Easy", "category": "Arrays"}],
                "videos": [{"title": "Complexity Walkthrough", "url": "https://www.youtube.com/watch?v=TG6418w1"}],
                "articles": [{"title": "Ace the Technical Prep", "url": "https://medium.com/tech-prep"}]
            },
            "roadmap": ["Step 1: Solve similar Array/HashMap problems.", "Step 2: Focus on optimal complexities."],
            "placement_readiness": 70.0
        }

    return report_data


# ----------------------------------------------------
# 4. ChatGPT-like AI Assistant API (Chats & Threads)
# ----------------------------------------------------
@app.post("/api/v1/chat/start")
def start_chat_session(req: ChatStartRequest, db: Session = Depends(get_db)):
    get_or_create_user(db, req.user_id)
    session = ChatSession(
        user_id=req.user_id,
        title=req.title
    )
    db.add(session)
    db.commit()
    return {
        "session_id": session.id,
        "title": session.title,
        "created_at": session.created_at.isoformat()
    }

@app.get("/api/v1/chat/history")
def list_chat_sessions(user_id: str = "anonymous", db: Session = Depends(get_db)):
    sessions = db.query(ChatSession).filter(ChatSession.user_id == user_id).order_by(ChatSession.updated_at.desc()).all()
    return [
        {
            "session_id": s.id,
            "title": s.title,
            "updated_at": s.updated_at.isoformat()
        } for s in sessions
    ]

@app.get("/api/v1/chat/history/{session_id}")
def get_chat_history(session_id: str, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc()).all()
    return {
        "session_id": session.id,
        "title": session.title,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat()
            } for m in messages
        ]
    }

@app.delete("/api/v1/chat/history/{session_id}")
def delete_chat_session(session_id: str, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    db.delete(session)
    db.commit()
    return {"message": "Chat session deleted successfully"}

@app.post("/api/v1/chat/message/stream")
def send_chat_message_stream(req: ChatMessageRequest, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == req.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    # Save User message
    user_msg = ChatMessage(
        session_id=req.session_id,
        role="user",
        content=req.message
    )
    db.add(user_msg)
    db.commit()

    # Get thread context
    all_msgs = db.query(ChatMessage).filter(ChatMessage.session_id == req.session_id).order_by(ChatMessage.created_at.asc()).all()
    
    # Compress history string to avoid token blowup
    history_str = ""
    for m in all_msgs[-12:]: # Last 12 messages for token efficiency
        history_str += f"{m.role.upper()}: {m.content}\n"

    system_instruction = (
        "You are PrepAgent Chatbot, a professional programming placement assistant. "
        "Explain coding, databases, algorithms, system design, resume reviews, behavioral "
        "interviews, or low-level design.\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. Answer the user's question directly. DO NOT include any preamble or filler sentences (like 'I received your message', 'You asked', 'Processing...', 'Sure, here is the answer', etc.).\n"
        "2. Do NOT use bold (**), italic (*), headers (###, ##, #), blockquotes (>), or horizontal rules (---) in your responses. Write clean, structured plain text using paragraphs, lists (using numbered list 1. 2. or bullet points - ), and code blocks (wrapped in triple backticks like ```python ... ``` for programming code). Do NOT use inline backticks around code symbols."
    )

    async def event_generator():
        import asyncio
        from app.database import SessionLocal
        try:
            response_text = await LLMService.get_completion(
                prompt=history_str,
                system_message=system_instruction,
                preferred_provider=req.provider
            )
            
            # Yield response content in chunks to simulate smooth real-time typing
            chunk_size = 8
            for i in range(0, len(response_text), chunk_size):
                chunk = response_text[i:i+chunk_size]
                yield f"data: {json.dumps({'content': chunk})}\n\n"
                await asyncio.sleep(0.005) # Small 5ms latency delay for fluent animation
            
            # Save final response to db in a fresh session
            db_new = SessionLocal()
            try:
                assistant_msg = ChatMessage(
                    session_id=req.session_id,
                    role="assistant",
                    content=response_text
                )
                db_new.add(assistant_msg)
                
                # Auto-title on first message
                session_new = db_new.query(ChatSession).filter(ChatSession.id == req.session_id).first()
                if session_new:
                    if len(all_msgs) <= 2:
                        session_new.title = req.message[:35] + "..." if len(req.message) > 35 else req.message
                    session_new.updated_at = datetime.utcnow()
                db_new.commit()
            finally:
                db_new.close()
                
        except Exception as e:
            yield f"data: {json.dumps({'content': f'Error during chat stream generation: {str(e)}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/v1/chat/message")
async def send_chat_message(req: ChatMessageRequest, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == req.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    # Save User message
    user_msg = ChatMessage(
        session_id=req.session_id,
        role="user",
        content=req.message
    )
    db.add(user_msg)
    db.commit()

    # Get thread context
    all_msgs = db.query(ChatMessage).filter(ChatMessage.session_id == req.session_id).order_by(ChatMessage.created_at.asc()).all()
    
    # Compress history string to avoid token blowup
    history_str = ""
    for m in all_msgs[-12:]: # Last 12 messages for token efficiency
        history_str += f"{m.role.upper()}: {m.content}\n"

    system_instruction = (
        "You are PrepAgent Chatbot, a professional programming placement assistant. "
        "Explain coding, databases, algorithms, system design, resume reviews, behavioral "
        "interviews, or low-level design.\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. Answer the user's question directly. DO NOT include any preamble or filler sentences (like 'I received your message', 'You asked', 'Processing...', 'Sure, here is the answer', etc.).\n"
        "2. Do NOT use bold (**), italic (*), headers (###, ##, #), blockquotes (>), or horizontal rules (---) in your responses. Write clean, structured plain text using paragraphs, lists (using numbered list 1. 2. or bullet points - ), and code blocks (wrapped in triple backticks like ```python ... ``` for programming code). Do NOT use inline backticks around code symbols."
    )

    response_text = await LLMService.get_completion(
        prompt=history_str,
        system_message=system_instruction,
        preferred_provider=req.provider
    )

    # Save assistant response
    assistant_msg = ChatMessage(
        session_id=req.session_id,
        role="assistant",
        content=response_text
    )
    db.add(assistant_msg)
    
    # Auto-title naming on first message
    if len(all_msgs) <= 2:
        session.title = req.message[:35] + "..." if len(req.message) > 35 else req.message

    session.updated_at = datetime.utcnow()
    db.commit()

    return {
        "session_id": req.session_id,
        "role": "assistant",
        "content": response_text
    }


# ----------------------------------------------------
# 5. Leaderboard API
# ----------------------------------------------------
@app.get("/api/v1/leaderboard")
def get_leaderboard(db: Session = Depends(get_db)):
    entries = db.query(LeaderboardEntry).order_by(LeaderboardEntry.solved.desc(), LeaderboardEntry.avg_score.desc()).all()
    
    # Return mapped data
    res = []
    for idx, e in enumerate(entries):
        res.append({
            "rank": idx + 1,
            "name": e.name,
            "avatar": "👨‍💻" if idx % 2 == 0 else "👩‍💻",
            "solved": e.solved,
            "avgScore": e.avg_score,
            "streak": e.streak,
            "language": e.language,
            "status": e.status
        })

    # Default Mock fallback list if database leaderboard is empty
    if not res:
        res = [
            { "rank": 1, "name": "Arjun Mehta", "avatar": "👨‍💻", "solved": 184, "avgScore": 9.4, "streak": 45, "language": "Python", "status": "Available" },
            { "rank": 2, "name": "Sophia Chen", "avatar": "👩‍💻", "solved": 162, "avgScore": 9.2, "streak": 38, "language": "C++", "status": "Interviewing" },
            { "rank": 3, "name": "Pranav Rao", "avatar": "👨‍💻", "solved": 147, "avgScore": 8.9, "streak": 21, "language": "Java", "status": "Available" },
            { "rank": 4, "name": "Emily Watson", "avatar": "👩‍💻", "solved": 139, "avgScore": 8.8, "streak": 14, "language": "JavaScript", "status": "Available" },
            { "rank": 5, "name": "Anonymous (You)", "avatar": "⚡", "solved": 0, "avgScore": 0.0, "streak": 0, "language": "Python", "status": "Preparing" }
        ]
    return res


# ----------------------------------------------------
# 6. Resume Scans & Progress APIs
# ----------------------------------------------------
@app.post("/api/v1/resume/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    contents = await file.read()
    raw_text = ""
    try:
        raw_text = contents.decode("utf-8")
    except UnicodeDecodeError:
        try:
            raw_text = contents.decode("latin-1")
        except Exception:
            raw_text = str(contents)

    skills_db = ["python", "javascript", "react", "next.js", "node.js", "java", "c++", "c", "sql", "postgresql", "redis", "docker", "aws", "git", "html", "css", "typescript", "kubernetes", "rust", "go", "machine learning", "fastapi"]
    lowercase_text = raw_text.lower()
    
    import re
    
    # Defaults and Regex fallbacks
    detected_skills = []
    for skill in skills_db:
        if skill in ("c++", "next.js", "node.js"):
            if skill in lowercase_text:
                detected_skills.append(skill)
        else:
            if re.search(r'\b' + re.escape(skill) + r'\b', lowercase_text):
                detected_skills.append(skill)
            
    skill_count = len(detected_skills)
    if skill_count < 3:
        skill_level = "Beginner"
        weak_topics = ["Arrays", "Strings", "Searching"]
    elif skill_count <= 6:
        skill_level = "Intermediate"
        weak_topics = ["HashMap", "Stack", "Graphs"]
    else:
        skill_level = "Advanced"
        weak_topics = ["Dynamic Programming", "Greedy", "Trees"]

    experience_text = "No detailed work experience block found."
    education_text = "No detailed education block found."
    
    exp_match = re.search(r'(?:experience|work|employment|history)(.*?)(?:education|skills|projects|interests|$)', raw_text, re.IGNORECASE | re.DOTALL)
    if exp_match:
        extracted = exp_match.group(1).strip()
        if len(extracted) > 10:
            experience_text = extracted[:300] + "..." if len(extracted) > 300 else extracted

    edu_match = re.search(r'(?:education|university|college|school)(.*?)(?:experience|skills|work|projects|interests|$)', raw_text, re.IGNORECASE | re.DOTALL)
    if edu_match:
        extracted = edu_match.group(1).strip()
        if len(extracted) > 10:
            education_text = extracted[:300] + "..." if len(extracted) > 300 else extracted

    # AI resume parsing with Groq/failovers
    prompt = f"""
Analyze the following resume text. Extract technical skills, work experience summary, education summary, infer the user's placement preparation skill level (Beginner, Intermediate, or Advanced), and identify 3-5 weak topics/improvement areas in computer science (e.g., Arrays, HashMap, Graphs, Dynamic Programming, Trees, Stacks, System Design, etc.) that they should focus on.

RESUME TEXT:
{raw_text[:4000]}

You must return your analysis ONLY in valid JSON format:
{{
  "skills": ["list of detected skills in lowercase, e.g. python, react, docker"],
  "experience": "Brief 1-2 sentence work experience summary.",
  "education": "Brief 1-2 sentence education summary.",
  "current_skill_level": "Beginner" or "Intermediate" or "Advanced",
  "weak_topics": ["list of 3-5 weak topics / focus areas"]
}}
"""
    system_msg = "You are a professional technical resume scanner. Respond only in valid JSON."
    
    try:
        response_text = await LLMService.get_completion(prompt, system_msg)
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        parsed = json.loads(cleaned)
        
        if "skills" in parsed and isinstance(parsed["skills"], list):
            detected_skills = [s.lower() for s in parsed["skills"]]
        if "experience" in parsed and parsed["experience"]:
            experience_text = parsed["experience"]
        if "education" in parsed and parsed["education"]:
            education_text = parsed["education"]
        if "current_skill_level" in parsed and parsed["current_skill_level"] in ("Beginner", "Intermediate", "Advanced"):
            skill_level = parsed["current_skill_level"]
        if "weak_topics" in parsed and isinstance(parsed["weak_topics"], list):
            weak_topics = parsed["weak_topics"]
    except Exception as e:
        print(f"[Main] Resume AI analysis fallback to regex parsing: {e}")

    default_user = db.query(User).first()
    if not default_user:
        default_user = User(
            email="developer@example.com",
            password_hash=hash_password("developer_secure_pass")
        )
        db.add(default_user)
        db.flush()
        
        profile = UserProfile(
            user_id=default_user.id,
            current_skill_level=skill_level,
            weak_topics=weak_topics
        )
        db.add(profile)
        db.flush()
    else:
        profile = db.query(UserProfile).filter(UserProfile.user_id == default_user.id).first()
        if profile:
            profile.current_skill_level = skill_level
            profile.weak_topics = weak_topics
            db.flush()

    resume = db.query(UserResume).filter(UserResume.user_id == default_user.id).first()
    if resume:
        resume.filename = file.filename
        resume.skills = detected_skills
        resume.experience = experience_text
        resume.education = education_text
        resume.raw_text = raw_text
    else:
        resume = UserResume(
            user_id=default_user.id,
            filename=file.filename,
            skills=detected_skills,
            experience=experience_text,
            education=education_text,
            raw_text=raw_text
        )
        db.add(resume)
    
    db.commit()

    return {
        "filename": file.filename,
        "skills": detected_skills,
        "experience": experience_text,
        "education": education_text,
        "weak_topics": weak_topics,
        "current_skill_level": skill_level
    }

@app.get("/api/v1/users/{user_id}/progress")
def get_user_progress(user_id: str, db: Session = Depends(get_db)):
    target_user_id = user_id
    if user_id == "anonymous":
        default_user = db.query(User).first()
        target_user_id = default_user.id if default_user else "anonymous"

    get_or_create_user(db, target_user_id)

    submissions = db.query(UserSubmission).filter(UserSubmission.user_id == target_user_id).all()
    interviews = db.query(InterviewSession).filter(InterviewSession.user_id == target_user_id).all()
    profile = db.query(UserProfile).filter(UserProfile.user_id == target_user_id).first()
    resume = db.query(UserResume).filter(UserResume.user_id == target_user_id).first()
    
    solved_problems = set(s.problem_id for s in submissions if s.status == "ACCEPTED")
    
    return {
        "total_submissions": len(submissions),
        "solved_count": len(solved_problems),
        "interview_count": len(interviews),
        "average_score": sum(i.overall_score for i in interviews if i.overall_score) / max(len(interviews), 1),
        "current_skill_level": profile.current_skill_level if profile else "Beginner",
        "weak_topics": profile.weak_topics if profile else ["Arrays", "Searching"],
        "resume": {
            "filename": resume.filename,
            "skills": resume.skills,
            "experience": resume.experience,
            "education": resume.education
        } if resume else None,
        "history": [{
            "id": s.id,
            "language": s.language,
            "status": s.status,
            "time_ms": s.execution_time_ms,
            "date": s.created_at.isoformat()
        } for s in submissions[-10:]]
    }


# ----------------------------------------------------
# 7. WebSocket Interactive Interview Gateway
# ----------------------------------------------------
@app.websocket("/api/v1/interviews/ws/{session_id}")
async def websocket_interview(websocket: WebSocket, session_id: str, db: Session = Depends(get_db)):
    await websocket.accept()
    try:
        session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
        if not session:
            await websocket.send_json({"type": "error", "message": "Interview session not found"})
            await websocket.close()
            return

        # Handshake confirmation
        await websocket.send_json({
            "type": "connection_status",
            "status": "connected",
            "session_id": session_id,
            "topic": session.topic
        })

        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            msg_type = payload.get("type")

            if msg_type == "text_message":
                user_msg = payload.get("content", "")
                user_code = payload.get("code", "")
                preferred_model = payload.get("model", "openai")

                dialogues = db.query(InterviewDialogue).filter(InterviewDialogue.session_id == session_id).all()
                chat_history = [{"speaker": d.speaker, "message": d.message} for d in dialogues]

                # Save user dialogue
                user_msg_log = InterviewDialogue(
                    session_id=session_id,
                    speaker="USER",
                    message=user_msg,
                    code_submitted=user_code
                )
                db.add(user_msg_log)
                db.commit()

                chat_history.append({"speaker": "USER", "message": user_msg})

                is_non_coding = session.topic.lower() in [
                    "system design", "low level design", "behavioral", "hr", "behavioral interview", "hr interview",
                    "operating systems", "dbms", "sql", "computer networks", "oop", "core cs"
                ] or session.problem_id is None

                if is_non_coding:
                    problem_title = f"{session.topic} Discussion"
                    problem_desc = f"Conducting a deep-dive interview on {session.topic}."
                    problem_id = "non-coding"
                else:
                    problem = db.query(Problem).filter(Problem.id == session.problem_id).first()
                    problem_title = problem.title if problem else "Coding challenge"
                    problem_desc = problem.description if problem else ""
                    problem_id = session.problem_id

                hint_count = sum(1 for h in chat_history if h["speaker"] == "INTERVIEWER" and "hint" in h["message"].lower())

                state: InterviewState = {
                    "session_id": session_id,
                    "problem_id": problem_id,
                    "problem_title": problem_title,
                    "problem_description": problem_desc,
                    "chat_history": chat_history,
                    "user_code": user_code,
                    "hint_count": hint_count,
                    "current_node": "evaluate_code" if (user_code and not is_non_coding) else "interviewer_turn",
                    "execution_result": None,
                    "final_feedback": None,
                    "overall_score": None,
                    "status": "ACTIVE",
                    "model": preferred_model,
                    "topic": session.topic,
                    "difficulty": "Easy",
                    "time_started": time.time(),
                    "live_evaluation": None
                }

                workflow = create_interview_workflow()
                new_state = await workflow.ainvoke(state)

                last_msg = new_state["chat_history"][-1]
                interviewer_msg_log = InterviewDialogue(
                    session_id=session_id,
                    speaker=last_msg["speaker"],
                    message=last_msg["message"]
                )
                db.add(interviewer_msg_log)

                if new_state.get("status") == "COMPLETED":
                    session.status = "COMPLETED"
                    session.overall_score = new_state.get("overall_score", 8.0)
                    session.final_feedback = new_state.get("final_feedback", "Interview finished.")
                    session.ended_at = datetime.utcnow()
                    sync_leaderboard(db, session.user_id)

                db.commit()

                # Get scorecard
                scores_entry = db.query(InterviewScore).filter(InterviewScore.session_id == session_id).first()
                live_scores = None
                if scores_entry:
                    live_scores = {
                        "communication": scores_entry.communication,
                        "confidence": scores_entry.confidence,
                        "technical_knowledge": scores_entry.technical_knowledge,
                        "problem_solving": scores_entry.problem_solving,
                        "coding_style": scores_entry.coding_style,
                        "optimization": scores_entry.optimization,
                        "time_complexity": scores_entry.time_complexity,
                        "space_complexity": scores_entry.space_complexity,
                        "edge_cases": scores_entry.edge_cases,
                        "code_quality": scores_entry.code_quality,
                        "feedback": scores_entry.feedback
                    }

                await websocket.send_json({
                    "type": "interviewer_speech",
                    "text": last_msg["message"],
                    "status": session.status,
                    "live_evaluation": live_scores,
                    "overall_score": session.overall_score,
                    "final_feedback": session.final_feedback
                })

            elif msg_type == "code_sync":
                # Heartbeat or cursor/code change sync
                await websocket.send_json({
                    "type": "code_sync_ack",
                    "status": "synchronized"
                })

    except WebSocketDisconnect:
        print(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass

# Trigger reload for .env path fix
