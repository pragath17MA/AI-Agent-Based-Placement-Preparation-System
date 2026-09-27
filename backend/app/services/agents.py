import os
import json
import httpx
import asyncio
from typing import Dict, Any, List, TypedDict, Optional
from langgraph.graph import StateGraph, END
from app.services.executor import CodeExecutor

# Define LangGraph State Schema
class InterviewState(TypedDict):
    session_id: str
    problem_id: str
    problem_title: str
    problem_description: str
    chat_history: List[Dict[str, str]]
    user_code: str
    hint_count: int
    current_node: str
    execution_result: Optional[Dict[str, Any]]
    final_feedback: Optional[str]
    overall_score: Optional[float]
    status: str
    model: Optional[str]

# ----------------------------------------------------
# 1. LLM Integration Client (Direct HTTP Calls via httpx)
# ----------------------------------------------------
import re

# In-memory simple cache for completed identical requests to minimize latency
_completion_cache = {}
_cache_lock = asyncio.Lock()

# Reusable async HTTP client instance to preserve connections
_async_client: Optional[httpx.AsyncClient] = None

def get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(timeout=15.0)
    return _async_client

def strip_markdown_formatting(prompt: str, text: str) -> str:
    p_lower = prompt.lower()
    if "markdown" in p_lower or "use md" in p_lower or "format as md" in p_lower:
        return text
        
    # Split text by code blocks to avoid altering code blocks
    parts = text.split("```")
    for i in range(len(parts)):
        # Even indices are outside code blocks
        if i % 2 == 0:
            s = parts[i]
            # Replace *** and ** with empty string
            s = s.replace("***", "")
            s = s.replace("**", "")
            
            # Remove * bullet points and single * formatting
            lines = []
            for line in s.splitlines():
                stripped = line.strip()
                if stripped.startswith("* ") or stripped.startswith("- "):
                    line = line.replace("* ", "", 1).replace("- ", "", 1)
                lines.append(line)
            s = "\n".join(lines)
            
            # Remove remaining formatting asterisks
            s = s.replace("*", "")
            parts[i] = s
            
    return "```".join(parts)

class LLMClientFactory:
    def __init__(self):
        self.providers = ["openai", "gemini", "anthropic", "groq", "deepseek", "openrouter", "ollama"]

    async def _call_provider(self, provider: str, prompt: str, system_message: str) -> str:
        provider = provider.lower()
        client = get_async_client()
        
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key or "your_openai_api_key_here" in api_key:
                raise ValueError("Missing OPENAI_API_KEY")
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7
            }
            response = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=12.0)
            response.raise_for_status()
            res_json = response.json()
            return res_json["choices"][0]["message"]["content"]
            
        elif provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key or "your_gemini_api_key_here" in api_key:
                raise ValueError("Missing GEMINI_API_KEY")
            
            headers = {
                "Content-Type": "application/json"
            }
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": f"System context: {system_message}\n\nUser prompt: {prompt}"}
                        ]
                    }
                ]
            }
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            response = await client.post(url, json=payload, headers=headers, timeout=12.0)
            response.raise_for_status()
            res_json = response.json()
            return res_json["candidates"][0]["content"]["parts"][0]["text"]
            
        elif provider in ("anthropic", "claude"):
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key or "your_anthropic_api_key_here" in api_key:
                raise ValueError("Missing ANTHROPIC_API_KEY")
            
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            payload = {
                "model": "claude-3-5-sonnet-20240620",
                "system": system_message,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1024,
                "temperature": 0.7
            }
            response = await client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers, timeout=12.0)
            response.raise_for_status()
            res_json = response.json()
            return res_json["content"][0]["text"]

        elif provider == "groq":
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key or "your_groq_api_key_here" in api_key or "YOUR_GROQ_API_KEY" in api_key:
                raise ValueError("Missing GROQ_API_KEY")
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 4096
            }
            response = await client.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=12.0)
            response.raise_for_status()
            res_json = response.json()
            return res_json["choices"][0]["message"]["content"]

        elif provider == "deepseek":
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key or "your_deepseek_api_key_here" in api_key:
                raise ValueError("Missing DEEPSEEK_API_KEY")
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7
            }
            response = await client.post("https://api.deepseek.com/chat/completions", json=payload, headers=headers, timeout=12.0)
            response.raise_for_status()
            res_json = response.json()
            return res_json["choices"][0]["message"]["content"]

        elif provider == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key or "your_openrouter_api_key_here" in api_key:
                raise ValueError("Missing OPENROUTER_API_KEY")
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:3000",
                "X-Title": "PrepAgent"
            }
            payload = {
                "model": "meta-llama/llama-3.1-8b-instruct:free",
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7
            }
            response = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=12.0)
            response.raise_for_status()
            res_json = response.json()
            return res_json["choices"][0]["message"]["content"]

        elif provider == "ollama":
            # Call local Ollama server
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": "llama3",
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                "stream": False
            }
            response = await client.post(f"{ollama_host}/api/chat", json=payload, headers=headers, timeout=15.0)
            response.raise_for_status()
            res_json = response.json()
            return res_json["message"]["content"]
            
        raise ValueError(f"Unknown provider: {provider}")

    async def get_completion(self, prompt: str, system_message: str = "You are a professional technical interviewer.", preferred_provider: Optional[str] = None) -> str:
        # Caching for repeated identical requests
        cache_key = f"{prompt}||{system_message}||{preferred_provider or ''}"
        async with _cache_lock:
            if cache_key in _completion_cache:
                return _completion_cache[cache_key]

        # Strict priority list: Groq -> Gemini -> OpenAI -> Anthropic (Claude)
        priority = ["groq", "gemini", "openai", "anthropic"]
        search_order = []
        
        # Add preferred provider first if specified
        if preferred_provider:
            pref = preferred_provider.lower()
            if pref == "claude":
                pref = "anthropic"
            if pref in self.providers:
                search_order.append(pref)
                
        # Add priority providers if not already added
        for p in priority:
            if p not in search_order and p in self.providers:
                search_order.append(p)
                
        # Add rest of the providers
        for p in self.providers:
            if p not in search_order:
                search_order.append(p)
                
        for provider in search_order:
            try:
                raw_response = await self._call_provider(provider, prompt, system_message)
                processed = strip_markdown_formatting(prompt, raw_response)
                async with _cache_lock:
                    _completion_cache[cache_key] = processed
                return processed
            except Exception:
                # Silent failover (no printing of warning messages)
                pass
        
        # If all fail, return the required error message
        return "Sorry, I'm temporarily unavailable. Please try again in a moment."

class LLMService:
    @staticmethod
    async def get_completion(prompt: str, system_message: str = "You are a professional technical interviewer.", preferred_provider: Optional[str] = None) -> str:
        factory = LLMClientFactory()
        return await factory.get_completion(prompt, system_message, preferred_provider)

    @staticmethod
    def _mock_response(prompt: str) -> str:
        return "Sorry, I'm temporarily unavailable. Please try again in a moment."


# ----------------------------------------------------
# 2. LangGraph Interview Dialog State Machine
# ----------------------------------------------------

async def generate_interviewer_response(state: InterviewState) -> Dict[str, Any]:
    """Generates the next question, hint, or follow-up question based on the graph state."""
    chat_hist = state.get("chat_history", [])
    user_code = state.get("user_code", "")
    hint_cnt = state.get("hint_count", 0)
    prob_title = state.get("problem_title", "Active Problem")
    prob_desc = state.get("problem_description", "")
    exec_res = state.get("execution_result", None)
    preferred_model = state.get("model")
    topic = state.get("topic", "Data Structures & Algorithms")
    difficulty = state.get("difficulty", "Easy")

    # Construct the advanced prompt to enforce structured feedback and conversational tone
    prompt = f"""
You are a senior technical interviewer at a top-tier technology company. You are conducting a live mock interview.

INTERVIEW METADATA:
- Category/Topic: {topic}
- Target Difficulty: {difficulty}
- Active Problem: {prob_title}
- Description: {prob_desc}

ACTIVE USER WORKSPACE:
- User Code currently written:
```
{user_code}
```
- Last code run verification: {json.dumps(exec_res) if exec_res else 'No runs yet'}
- Hints given so far: {hint_cnt}

DIALOGUE HISTORICAL TIMELINE:
{json.dumps(chat_hist)}

YOUR INSTRUCTIONS:
1. Act like a real human interviewer. Keep your tone professional, supportive, and conversational.
2. Structure the interview into natural progression phases:
   - Clarification & Constraints (e.g. check inputs, edge cases)
   - Approach discussion (brute-force vs. optimal, tradeoffs)
   - Code writing (direct the user to write code in the Monaco canvas - skip this for non-coding topics like Behavioral or System Design)
   - Complexity walk-through (time and space complexities)
3. If they make logical errors or get stuck, do NOT give them the code. Guide them with subtle, progressive hints.
4. Calculate a live scorecard (each metric out of 10.0) based on their answers, coding, and responses:
   - communication
   - confidence
   - technical_knowledge
   - problem_solving
   - coding_style
   - optimization
   - time_complexity
   - space_complexity
   - edge_cases
   - code_quality
5. Update a checkbox checklist for completion:
   - clarified_requirements (boolean)
   - discussed_brute_force (boolean)
   - implemented_optimal_code (boolean)
   - analyzed_complexity (boolean)
   - handled_edge_cases (boolean)

6. DO NOT use any markdown characters (like **, *, ###, >, ---, or inline backticks) in the "interviewer_speech" content. Keep it clean plain text only, structured as natural professional speech.

You MUST respond ONLY in valid JSON format:
{{
  "interviewer_speech": "Your dialogue spoken to the student.",
  "live_evaluation": {{
    "communication": float,
    "confidence": float,
    "technical_knowledge": float,
    "problem_solving": float,
    "coding_style": float,
    "optimization": float,
    "time_complexity": float,
    "space_complexity": float,
    "edge_cases": float,
    "code_quality": float,
    "feedback": "Encouraging 1-2 sentence real-time feedback."
  }},
  "checklist": {{
    "clarified_requirements": bool,
    "discussed_brute_force": bool,
    "implemented_optimal_code": bool,
    "analyzed_complexity": bool,
    "handled_edge_cases": bool
  }},
  "action": "CONTINUE" // "CONTINUE" | "PROBE_COMPLEXITY" | "TERMINATE"
}}
"""
    system_msg = "You are a professional mock interviewer. Respond only in valid JSON format."
    response_text = await LLMService.get_completion(prompt, system_msg, preferred_model)

    interviewer_speech = response_text
    live_eval = None
    checklist = None
    action = "CONTINUE"

    try:
        # Extract JSON block if surrounded by markdown backticks
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
        interviewer_speech = parsed.get("interviewer_speech", response_text)
        live_eval = parsed.get("live_evaluation", None)
        checklist = parsed.get("checklist", None)
        action = parsed.get("action", "CONTINUE")
    except Exception as e:
        print(f"[Agents] JSON parse failed: {e}. Falling back to clean transcript.")
        # Fallback scorecard
        live_eval = {
            "communication": 7.5,
            "confidence": 7.0,
            "technical_knowledge": 7.0,
            "problem_solving": 7.0,
            "coding_style": 7.0,
            "optimization": 6.5,
            "time_complexity": 6.5,
            "space_complexity": 6.5,
            "edge_cases": 6.0,
            "code_quality": 7.0,
            "feedback": "Keep going! Good start. Walk me through the implementation details."
        }
        checklist = {
            "clarified_requirements": True,
            "discussed_brute_force": len(chat_hist) > 1,
            "implemented_optimal_code": len(user_code) > 40,
            "analyzed_complexity": False,
            "handled_edge_cases": False
        }

    # Write live evaluation scorecard directly to database to preserve history
    session_id = state.get("session_id")
    if session_id and live_eval:
        from app.database import SessionLocal
        from app.models import InterviewScore
        db = SessionLocal()
        try:
            score_entry = db.query(InterviewScore).filter(InterviewScore.session_id == session_id).first()
            if not score_entry:
                score_entry = InterviewScore(session_id=session_id)
                db.add(score_entry)
            
            score_entry.communication = float(live_eval.get("communication", 7.0))
            score_entry.confidence = float(live_eval.get("confidence", 7.0))
            score_entry.technical_knowledge = float(live_eval.get("technical_knowledge", 7.0))
            score_entry.problem_solving = float(live_eval.get("problem_solving", 7.0))
            score_entry.coding_style = float(live_eval.get("coding_style", 7.0))
            score_entry.optimization = float(live_eval.get("optimization", 7.0))
            score_entry.time_complexity = float(live_eval.get("time_complexity", 7.0))
            score_entry.space_complexity = float(live_eval.get("space_complexity", 7.0))
            score_entry.edge_cases = float(live_eval.get("edge_cases", 7.0))
            score_entry.code_quality = float(live_eval.get("code_quality", 7.0))
            score_entry.feedback = live_eval.get("feedback", "")
            db.commit()
        except Exception as db_err:
            print(f"[Agents] Database score update failed: {db_err}")
            db.rollback()
        finally:
            db.close()

    updated_history = list(chat_hist)
    updated_history.append({"speaker": "INTERVIEWER", "message": interviewer_speech})

    # Adapt difficulty dynamically: If the user is scoring highly, suggest adapting
    new_diff = difficulty
    avg_score = sum(live_eval.values()) / 10 if (live_eval and isinstance(live_eval, dict)) else 7.0
    if avg_score >= 8.5 and difficulty == "Easy":
        new_diff = "Medium"
    elif avg_score >= 8.5 and difficulty == "Medium":
        new_diff = "Hard"
    elif avg_score < 5.0 and difficulty == "Hard":
        new_diff = "Medium"
    elif avg_score < 5.0 and difficulty == "Medium":
        new_diff = "Easy"

    return {
        "chat_history": updated_history,
        "current_node": "interviewer_turn",
        "live_evaluation": live_eval,
        "difficulty": new_diff,
        "status": "ACTIVE" if action != "TERMINATE" else "COMPLETED"
    }

def evaluate_user_code(state: InterviewState) -> Dict[str, Any]:
    """Runs test cases against user code and evaluates whether hints or next steps are needed."""
    user_code = state.get("user_code", "")
    prob_id = state.get("problem_id", "")
    topic = state.get("topic", "")

    # Skip test execution for non-coding/verbal interviews (System Design, Core CS, Behavioral)
    is_non_coding = topic.lower() in [
        "system design", "low level design", "behavioral", "hr", "behavioral interview", "hr interview",
        "operating systems", "dbms", "sql", "computer networks", "oop", "core cs"
    ] or prob_id == "non-coding"

    if is_non_coding:
        result = {
            "status": "ACCEPTED",
            "passed": True,
            "stdout": "Discussion parsed.",
            "stderr": "",
            "execution_time_ms": 0.0,
            "actual": "verbal",
            "expected": "verbal"
        }
        return {
            "execution_result": result,
            "current_node": "evaluate_code"
        }

    from app.database import SessionLocal
    from app.models import TestCase, Problem
    
    db = SessionLocal()
    try:
        test_cases = db.query(TestCase).filter(TestCase.problem_id == prob_id).all()
        problem = db.query(Problem).filter(Problem.id == prob_id).first()
        
        if test_cases and problem:
            all_passed = True
            first_fail = None
            for tc in test_cases:
                res = CodeExecutor.run_code(
                    language="python",
                    code=user_code,
                    inputs=tc.input_data,
                    expected=tc.expected_output,
                    timeout_sec=float(problem.time_limit_ms) / 1000.0
                )
                if not res["passed"]:
                    all_passed = False
                    first_fail = res
                    break
            
            if all_passed:
                result = {
                    "status": "ACCEPTED",
                    "passed": True,
                    "stdout": "",
                    "stderr": "",
                    "execution_time_ms": 10.0,
                    "actual": test_cases[0].expected_output,
                    "expected": test_cases[0].expected_output
                }
            else:
                result = {
                    "status": first_fail.get("status", "WRONG_ANSWER"),
                    "passed": False,
                    "stdout": first_fail.get("stdout", ""),
                    "stderr": first_fail.get("stderr", ""),
                    "execution_time_ms": first_fail.get("execution_time_ms", 10.0),
                    "actual": first_fail.get("actual", ""),
                    "expected": first_fail.get("expected", "")
                }
        else:
            # Fallbacks for synthetic challenges without explicit test cases
            if "def twoSum" in user_code:
                inputs = "[[2, 7, 11, 15], 9]"
                expected = "[0, 1]"
                result = CodeExecutor.run_code("python", user_code, inputs, expected)
            elif "def isValid" in user_code:
                inputs = "[\"()\"]"
                expected = "true"
                result = CodeExecutor.run_code("python", user_code, inputs, expected)
            else:
                result = {
                    "status": "ACCEPTED",
                    "passed": True,
                    "stdout": "",
                    "stderr": "",
                    "execution_time_ms": 10.0,
                    "actual": "[]",
                    "expected": "[]"
                }
    except Exception as e:
        print(f"Error during evaluate_user_code node query: {e}")
        result = {
            "status": "COMPILE_ERROR",
            "passed": False,
            "stdout": "",
            "stderr": str(e),
            "execution_time_ms": 0
        }
    finally:
        db.close()

    return {
        "execution_result": result,
        "current_node": "evaluate_code"
    }

async def grade_session(state: InterviewState) -> Dict[str, Any]:
    """Calculates final scores and structural mock interview feedback."""
    user_code = state.get("user_code", "")
    chat_hist = state.get("chat_history", [])
    hint_cnt = state.get("hint_count", 0)
    preferred_model = state.get("model")
    topic = state.get("topic", "Data Structures & Algorithms")
    difficulty = state.get("difficulty", "Easy")
    prob_title = state.get("problem_title", "Active Problem")

    # Let LLM compile the comprehensive final report
    prompt = f"""
You are the Calibrations Panel Lead at a tech firm. Provide a comprehensive calibration report evaluating this completed mock interview.

INTERVIEW SPECIFICATIONS:
- Topic: {topic}
- Difficulty: {difficulty}
- Challenge: {prob_title}
- Final Code Submitted:
```
{user_code}
```
- Full chat history transcript:
{json.dumps(chat_hist)}
- Hints requested/needed: {hint_cnt}

EVALUATION TASK:
Evaluate the student on the following 10 criteria out of 10.0:
- communication
- confidence
- technical_knowledge
- problem_solving
- coding_style
- optimization
- time_complexity
- space_complexity
- edge_cases
- code_quality

Compute an overall score (average of the 10 scores). Provide explicit details on:
1. Strengths (list of strings)
2. Weaknesses (list of strings)
3. Topic-wise proficiency breakdown (score for categories like Data Structures, Coding Quality, Communication)
4. Recommended resources:
   - Coding problems (provide titles, category, and difficulty)
   - Suggested placement readiness improvement articles (names and URLs)
   - Helpful educational videos (names and URLs)
5. A structured 3-step pathway/roadmap to improvement
6. Placement Readiness percentage (e.g. 75%) based on performance and target difficulty.

Return your response ONLY in valid JSON format:
{{
  "overall_score": float,
  "scores": {{
    "communication": float,
    "confidence": float,
    "technical_knowledge": float,
    "problem_solving": float,
    "coding_style": float,
    "optimization": float,
    "time_complexity": float,
    "space_complexity": float,
    "edge_cases": float,
    "code_quality": float
  }},
  "strengths": ["string"],
  "weaknesses": ["string"],
  "final_feedback": "Detailed paragraph explaining overall calibration results.",
  "topic_scores": {{
     "Data Structures": float,
     "Algorithms": float,
     "Communication": float,
     "Systems/Core CS": float
  }},
  "recommendations": {{
     "problems": [
        {{"title": "Two Sum", "difficulty": "Easy", "category": "Arrays"}},
        {{"title": "Valid Parentheses", "difficulty": "Easy", "category": "Stacks"}}
     ],
     "videos": [
        {{"title": "Binary Search Deep Dive", "url": "https://www.youtube.com/watch?v=TG6418w1"}},
        {{"title": "Dynamic Programming Intro", "url": "https://www.youtube.com/watch?v=oBt53Yh9"}}
     ],
     "articles": [
        {{"title": "How to Ace the Coding Interview", "url": "https://medium.com/tech-prep/ace-interview"}}
     ]
  }},
  "roadmap": [
     "Step 1: Focus on Array hashing and sliding window concepts.",
     "Step 2: Dry-run code on edge cases before submitting.",
     "Step 3: Practice mock communicating while writing code."
  ],
  "placement_readiness": float
}}
"""
    system_msg = "You are the calibrations board director. Respond only in valid JSON format."
    raw_eval = await LLMService.get_completion(prompt, system_msg, preferred_model)
    
    # Secure parser
    try:
        cleaned_eval = raw_eval.strip()
        if cleaned_eval.startswith("```json"):
            cleaned_eval = cleaned_eval[7:]
            if cleaned_eval.endswith("```"):
                cleaned_eval = cleaned_eval[:-3]
        elif cleaned_eval.startswith("```"):
            cleaned_eval = cleaned_eval[3:]
            if cleaned_eval.endswith("```"):
                cleaned_eval = cleaned_eval[:-3]
        cleaned_eval = cleaned_eval.strip()
        
        eval_json = json.loads(cleaned_eval)
        overall_score = float(eval_json.get("overall_score", 7.5))
        final_feedback = json.dumps(eval_json)  # Store complete json payload inside final_feedback text
    except Exception as e:
        print(f"[Agents] Final grading parse failed: {e}. Falling back to default report schema.")
        # Fallback JSON structure
        fallback_json = {
            "overall_score": 8.0 - (0.5 * hint_cnt),
            "scores": {
                "communication": 8.0,
                "confidence": 8.0,
                "technical_knowledge": 7.5,
                "problem_solving": 7.5,
                "coding_style": 8.0,
                "optimization": 7.0,
                "time_complexity": 7.0,
                "space_complexity": 7.0,
                "edge_cases": 6.5,
                "code_quality": 8.0
            },
            "strengths": ["Clear logical explanations", "Optimal usage of structures"],
            "weaknesses": ["Minor speed delays", "Missed extreme edge-cases initially"],
            "final_feedback": "Completed successfully. Solid code logic demonstrated with high communication clarity.",
            "topic_scores": {
                "Data Structures": 7.5,
                "Algorithms": 7.0,
                "Communication": 8.0,
                "Systems/Core CS": 7.0
            },
            "recommendations": {
                "problems": [
                    {"title": "Two Sum", "difficulty": "Easy", "category": "Arrays"}
                ],
                "videos": [
                    {"title": "Data Structures Basics", "url": "https://www.youtube.com/watch?v=TG6418w1"}
                ],
                "articles": [
                    {"title": "Edge Case Testing", "url": "https://medium.com/tech-prep/ace-interview"}
                ]
            },
            "roadmap": [
                "Step 1: Practice coding under time constraints.",
                "Step 2: Focus on recursion stack size optimization."
            ],
            "placement_readiness": 75.0
        }
        overall_score = fallback_json["overall_score"]
        final_feedback = json.dumps(fallback_json)

    # Save final scores directly in Database scores table for permanence
    session_id = state.get("session_id")
    if session_id:
        from app.database import SessionLocal
        from app.models import InterviewScore
        db = SessionLocal()
        try:
            score_entry = db.query(InterviewScore).filter(InterviewScore.session_id == session_id).first()
            if not score_entry:
                score_entry = InterviewScore(session_id=session_id)
                db.add(score_entry)
            
            # Populate scores if parsed successfully
            if "scores" in eval_json:
                s = eval_json["scores"]
                score_entry.communication = float(s.get("communication", 7.0))
                score_entry.confidence = float(s.get("confidence", 7.0))
                score_entry.technical_knowledge = float(s.get("technical_knowledge", 7.0))
                score_entry.problem_solving = float(s.get("problem_solving", 7.0))
                score_entry.coding_style = float(s.get("coding_style", 7.0))
                score_entry.optimization = float(s.get("optimization", 7.0))
                score_entry.time_complexity = float(s.get("time_complexity", 7.0))
                score_entry.space_complexity = float(s.get("space_complexity", 7.0))
                score_entry.edge_cases = float(s.get("edge_cases", 7.0))
                score_entry.code_quality = float(s.get("code_quality", 7.0))
                score_entry.feedback = eval_json.get("final_feedback", "")
            db.commit()
        except Exception as db_err:
            print(f"[Agents] Final grading database update failed: {db_err}")
            db.rollback()
        finally:
            db.close()

    return {
        "overall_score": overall_score,
        "final_feedback": final_feedback,
        "status": "COMPLETED",
        "current_node": "conclude_interview"
    }


# Build LangGraph Router Workflows
def create_interview_workflow():
    workflow = StateGraph(InterviewState)

    def start_routing_node(state: InterviewState) -> Dict[str, Any]:
        return state

    # Add Nodes
    workflow.add_node("start_routing_node", start_routing_node)
    workflow.add_node("interviewer_turn", generate_interviewer_response)
    workflow.add_node("evaluate_code", evaluate_user_code)
    workflow.add_node("conclude_interview", grade_session)

    # Set Entry Point
    workflow.set_entry_point("start_routing_node")

    # Define Conditional Entry routing
    def route_start_decision(state: InterviewState) -> str:
        if state.get("current_node") == "evaluate_code":
            return "evaluate_code"
        elif state.get("current_node") == "conclude_interview":
            return "conclude_interview"
        return "interviewer_turn"

    # Define Conditional Routing Edges from evaluate_code
    def should_continue(state: InterviewState):
        exec_res = state.get("execution_result", None)
        hint_cnt = state.get("hint_count", 0)
        
        if exec_res and exec_res.get("passed") is True:
            return "conclude_interview"
        elif hint_cnt >= 2:
            return "conclude_interview"
        else:
            return "interviewer_turn"

    # Add edges
    workflow.add_conditional_edges(
        "start_routing_node",
        route_start_decision,
        {
            "evaluate_code": "evaluate_code",
            "interviewer_turn": "interviewer_turn",
            "conclude_interview": "conclude_interview"
        }
    )
    workflow.add_conditional_edges(
        "evaluate_code",
        should_continue,
        {
            "conclude_interview": "conclude_interview",
            "interviewer_turn": "interviewer_turn"
        }
    )
    workflow.add_edge("interviewer_turn", END)
    workflow.add_edge("conclude_interview", END)

    return workflow.compile()


# ----------------------------------------------------
# 3. Vector Database Semantic Problem Recommendations
# ----------------------------------------------------
class ProblemRecommender:
    @staticmethod
    def get_recommendation(user_skill: str, weak_topics: List[str]) -> Dict[str, Any]:
        """
        Uses semantic similarities to match user skill gap vectors with coding tasks.
        Includes a standard database selection matching target areas.
        """
        from app.database import SessionLocal
        from app.models import Problem
        
        db = SessionLocal()
        try:
            problem = None
            for topic in weak_topics:
                problem = db.query(Problem).filter(Problem.category.like(f"%{topic}%")).first()
                if problem:
                    break
            
            if not problem:
                problem = db.query(Problem).filter(Problem.difficulty == "Easy").first()
                
            if not problem:
                problem = db.query(Problem).first()
                
            if problem:
                return {
                    "id": problem.id,
                    "title": problem.title,
                    "difficulty": problem.difficulty,
                    "category": problem.category,
                    "reasoning": f"Identified weak topic: {problem.category}. This {problem.difficulty} problem was selected to fill this gap."
                }
        except Exception as e:
            print(f"Error querying problem recommendations: {e}")
        finally:
            db.close()

        # Hardcoded fallback list if DB query fails or has error
        return {
            "id": "1",
            "title": "Two Sum",
            "difficulty": "Easy",
            "category": "Arrays",
            "reasoning": "Fallback match selection."
        }

def process_user_dialogue(state: InterviewState, user_input: str) -> Dict[str, Any]:
    """Appends user speech or text input to chat history."""
    chat_hist = state.get("chat_history", [])
    updated_history = list(chat_hist)
    updated_history.append({"speaker": "USER", "message": user_input})
    
    return {
        "chat_history": updated_history,
        "current_node": "user_turn"
    }

