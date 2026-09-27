# Technical Specification & Implementation Roadmap: Placement Preparation Agent

This document outlines the end-to-end design, system architecture, database models, API specs, agent logic, and deployment strategy for the **Placement Preparation Agent** — a browser-based IDE and mock interview platform that runs entirely in Chrome.

---

## 1. System Architecture Document

The Placement Preparation Agent utilizes a modern, service-oriented architecture designed for low latency, secure execution of untrusted user code, and complex state management of LLM-driven agents.

### 1.1 High-Level Architecture Diagram

The diagram below details the interaction between the frontend client, backend application servers, containerized code executor pool, stateful agent engine, databases, and LLM APIs.

```mermaid
graph TD
    %% Client Tier
    subgraph Client Tier (Chrome Browser)
        A[Next.js Frontend] -->|HTTP REST / Auth| B[API Gateway]
        A -->|WebSocket Connection| WSGate[WebSocket Gateway]
        A -->|Monaco Editor| Mon[Code Editor Component]
    end

    %% Web & Application Tier
    subgraph Application Tier
        B -->|Reverse Proxy / Load Balancer| FastAPI[FastAPI Backend Server]
        WSGate -->|Real-time Socket Conn| FastAPI
        FastAPI -->|JWT Authentication| AuthSvc[Auth & Profile Service]
        FastAPI -->|State Machine Execution| GraphEng[LangGraph Orchestrator]
    end

    %% Agent & AI Engine
    subgraph AI & Agent Orchestration
        GraphEng -->|Orchestrate Agent Steps| AgentRec[Recommendation Agent]
        GraphEng -->|Orchestrate Dialogues| AgentInt[Mock Interview Agent]
        AgentRec & AgentInt -->|Multi-Provider LLM Gateway| LLMProxy[LLM Client Factory]
        LLMProxy -->|API Request with Retries| OpenAI[OpenAI API]
        LLMProxy -->|API Request with Retries| Claude[Anthropic Claude API]
        LLMProxy -->|API Request with Retries| Gemini[Google Gemini API]
    end

    %% Database & Cache Tier
    subgraph Data & Search Tier
        FastAPI -->|Read/Write Session & Stats| PostgreSQL[(PostgreSQL DB)]
        FastAPI -->|Cache / Task Queue Broker| Redis[(Redis Cache & Broker)]
        Redis -->|Distribute Exec Jobs| Celery[Celery Task Workers]
        AgentRec & AgentInt -->|Semantic Similarity Search| Chroma[(Chroma Vector DB)]
    end

    %% Code Execution Sandbox
    subgraph Execution Sandbox
        Celery -->|Spin up isolated runner| ExecPool[Sandboxed Container Pool]
        ExecPool -->|gVisor / Docker Isolation| Runner[Isolated Python/JS Runner]
        Runner -->|Returns stdout/stderr/time| Celery
    end

    classDef client fill:#1e293b,stroke:#3b82f6,stroke-width:2px,color:#f8fafc;
    classDef app fill:#0f172a,stroke:#8b5cf6,stroke-width:2px,color:#f8fafc;
    classDef ai fill:#0b1329,stroke:#ec4899,stroke-width:2px,color:#f8fafc;
    classDef data fill:#1c1917,stroke:#10b981,stroke-width:2px,color:#f8fafc;
    classDef sandbox fill:#450a0a,stroke:#ef4444,stroke-width:2px,color:#f8fafc;

    class A,B,WSGate,Mon client;
    class FastAPI,AuthSvc,GraphEng app;
    class AgentRec,AgentInt,LLMProxy,OpenAI,Claude,Gemini ai;
    class PostgreSQL,Redis,Chroma,Celery data;
    class ExecPool,Runner sandbox;
```

### 1.2 Component Interaction & Data Flows

#### 1.2.1 Secure Code Execution Flow
1. **Submit**: The user writes Python or JavaScript code inside the browser's Monaco Editor and clicks **Submit**.
2. **REST Call**: The frontend sends a `POST /api/v1/execute` request to the FastAPI backend, including the code string, language identifier (`python` or `javascript`), and the problem ID.
3. **Queue Task**: FastAPI pushes the execution task onto **Redis**, which acts as the message broker for Celery.
4. **Acquire Sandbox**: A background Celery worker picks up the job. It provisions/acquires an isolated sandbox container configured with CPU constraints (`--cpus="0.5"`), memory limits (`--memory="128m"`), and a read-only root file system via gVisor.
5. **Run & Test**: The container mounts the code, executes it against the problem's hidden test cases stored in PostgreSQL, and records:
   - `stdout` / `stderr`
   - Execution time (in milliseconds)
   - Max memory usage (in megabytes)
   - Success/failure boolean for each test case
6. **Return**: The runner returns the JSON payload back to the Celery worker, which updates the Redis task state. FastAPI streams or returns the result to the browser UI.

#### 1.2.2 Agentic Mock Interview Flow
1. **Start**: The user clicks "Start Mock Interview" in the frontend.
2. **WebSocket Handshake**: A WebSocket connection is established with `/api/v1/interviews/ws/{session_id}`.
3. **Initialize State**: The backend initializes a stateful **LangGraph** session. The Graph starts at the `initialize_session` node, retrieves the user's profile from PostgreSQL, maps their weaknesses via Chroma vector DB, and selects an appropriate coding problem.
4. **First Prompt**: The agent pushes the first interview question to the WebSocket. The user receives it as audio/text.
5. **Interactive Loop**:
   - The user writes code and replies verbally/textually.
   - The combined inputs are sent via WebSocket to the server.
   - The graph transition logic evaluates the response, runs tests asynchronously, updates internal confidence thresholds, and branches:
     - If the code is correct but lacks edge-case protection: transition to `probe_edge_cases`.
     - If the user is stuck: transition to `provide_subtle_hint`.
     - If the solution is optimal: transition to `ask_follow_up_complexity`.
6. **Grading & Sync**: When the session ends, the `grade_interview` node aggregates performance metrics (communication, code quality, speed, optimization) and persists results to PostgreSQL.

---

## 2. Frontend Specification

The client application is built as a single-page application (SPA) using React/Next.js and styled with Vanilla CSS.

### 2.1 Component Hierarchy

```
App (Root Wrapper)
├── Navigation Sidebar (Global Navigation & User Settings)
├── Header (Active Session Context, LLM Selector, Network Ping Status)
└── View Container (Dynamic Routing)
    ├── Dashboard View
    │   ├── Stats Summary Panel (Overall Score, Weekly Target Tracker)
    │   ├── Weakness Radar Chart (Visual representation of problem tags)
    │   ├── Recent History Table (List of submissions, status, and scores)
    │   └── Recommended Pathway Container (AI-suggested tasks)
    ├── Practice Workspace View
    │   ├── Split Pane Layout
    │   │   ├── Left Pane: Problem Description Panel
    │   │   │   ├── Markdown Renderer
    │   │   │   ├── Edge Cases Tab
    │   │   │   └── AI Hint Assistant Accordion
    │   │   └── Right Pane: Code Editor Component
    │   │       ├── Editor Toolbar (Language select, Theme toggle, Keybinding maps)
    │   │       ├── Monaco Editor Instance (Syntax highlighting & Autocomplete)
    │   │       └── Output & Console Panel (Interactive stdout/stderr CLI, Test Case metrics)
    └── Interview Workspace View
        ├── Multi-Panel Interaction Space
        │   ├── Header Overlay (Countdown Timer, Stage Progress Bar)
        │   ├── Left Panel: Interviewer Chat Log
        │   │   ├── Dialogue Transcript (Interactive text balloons)
        │   │   └── Audio Waveform Visualization (Voice activation feedback)
        │   ├── Central Panel: Code Canvas
        │   │   └── Shared Monaco Code Editor (Read/Write locked depending on agent turn)
        │   └── Right Panel: Live Feed & Feedback
        │       ├── Structured Requirements Check (Real-time Checklist)
        │       └── Live Sentiment/Tone Meter (Optional visual cue)
```

### 2.2 Global State Management Design (Zustand)

Zustand is chosen for its minimalistic footprint, high performance, and ease of hook integration in React.

```javascript
import { create } from 'zustand';

export const useAppStore = create((set) => ({
  // Authentication & User Profile
  user: null,
  isAuthenticated: false,
  setUser: (user) => set({ user, isAuthenticated: !!user }),

  // LLM Configurations
  activeModelProvider: 'anthropic', // 'openai' | 'anthropic' | 'gemini'
  setActiveModelProvider: (provider) => set({ activeModelProvider: provider }),

  // Active Coding Practice Workspace State
  activeProblem: null,
  editorLanguage: 'python', // 'python' | 'javascript'
  codeBuffer: '',
  executionLogs: null,
  isExecuting: false,
  setActiveProblem: (problem) => set({ activeProblem: problem, codeBuffer: problem.templateCode }),
  setEditorLanguage: (lang) => set({ editorLanguage: lang }),
  setCodeBuffer: (code) => set({ codeBuffer: code }),
  setExecutionLogs: (logs) => set({ executionLogs: logs }),
  setIsExecuting: (status) => set({ isExecuting: status }),

  // Active Interview Session State
  interviewSession: {
    sessionId: null,
    status: 'idle', // 'idle' | 'running' | 'paused' | 'completed'
    dialogueHistory: [],
    timerRemaining: 2700, // 45 minutes in seconds
    isRecording: false,
  },
  startInterview: (sessionId) => set((state) => ({
    interviewSession: { ...state.interviewSession, sessionId, status: 'running', dialogueHistory: [] }
  })),
  addDialogueMessage: (messageObj) => set((state) => ({
    interviewSession: {
      ...state.interviewSession,
      dialogueHistory: [...state.interviewSession.dialogueHistory, messageObj]
    }
  })),
  updateTimer: (timeRemaining) => set((state) => ({
    interviewSession: { ...state.interviewSession, timerRemaining: timeRemaining }
  })),
  setRecordingState: (isRec) => set((state) => ({
    interviewSession: { ...state.interviewSession, isRecording: isRec }
  })),
}));
```

### 2.3 Key Interface Interactions
1. **Interactive Split-Pane**: Supports sliding resize using simple mouse drag listeners, dynamically triggering resizing calls on the Monaco Editor API to prevent text truncation.
2. **Audio Input Interaction**: Uses the HTML5 Web Speech API (speech-to-text) to parse user speech in real-time, allowing users to talk directly to the interviewer agent while writing code.
3. **Execution Console Animations**: Status markers slide in using CSS variables for smooth rendering, with terminal text streaming line-by-line during long evaluations.

### 2.4 Visual Design Palette (Sleek Dark Mode)

The UI utilizes a dark, high-contrast, premium interface inspired by modern developer ecosystems.

| Element | Color Role | HEX / Value | CSS Variable |
| :--- | :--- | :--- | :--- |
| **Primary Canvas** | App Background | `#0B0F19` | `--bg-primary` |
| **Cards & Panels** | Element Containers | `#111827` | `--bg-secondary` |
| **Borders & Rules** | Grid Borders | `#1F2937` | `--border-color` |
| **Interactivity Hover**| Selected States | `#374151` | `--bg-hover` |
| **Accent Indigo** | Primary UI buttons / Active| `#6366F1` | `--accent-indigo` |
| **Accent Violet** | AI Agent identity highlight | `#8B5CF6` | `--accent-agent` |
| **Success Mint** | Solved / Recommendations | `#10B981` | `--accent-success` |
| **Failure Rose** | Compile Error / Rejected test| `#EF4444` | `--accent-error` |
| **Warning Amber** | Unsaved state / Alerts | `#F59E0B` | `--accent-warning` |

#### Typography
- **UI Element Sans**: `Inter`, system-ui, sans-serif (size range: `12px` to `24px`).
- **Code Editor & Console Mono**: `Fira Code`, `Source Code Pro`, monospace (size: `14px`, line-height: `1.6`).

---

## 3. Backend API Specification

FastAPI is the core framework for our API backend, using standard OpenAPI v3 routing models.

### 3.1 REST Routes Overview

#### 3.1.1 Authentication & Profile Management
- `POST /api/v1/auth/register`
  - *Description*: Sign up user.
  - *Payload*: `{"email": "user@domain.com", "password": "secure_password_str"}`
  - *Response*: `201 Created` with JWT access tokens.
- `POST /api/v1/auth/token`
  - *Description*: OAuth2 compatible endpoint returning access token.
  - *Payload*: form-data `username`, `password`.
  - *Response*: `{"access_token": "jwt_str", "token_type": "bearer"}`.

#### 3.1.2 Code Sandbox Runner
- `POST /api/v1/execute`
  - *Description*: Dispatches isolated code execution tasks to Celery pool.
  - *Payload*:
    ```json
    {
      "problem_id": "uuid-str",
      "language": "python",
      "code": "def solution(arr):\n    return sorted(arr)"
    }
    ```
  - *Response*: `202 Accepted` returning a `task_id` for background status polling, or synchronous `200 OK` return for fast runs:
    ```json
    {
      "status": "success",
      "stdout": "Sorted result computed.",
      "stderr": "",
      "execution_time_ms": 14.5,
      "memory_used_mb": 24.3,
      "test_cases_passed": 5,
      "test_cases_total": 5,
      "results": [
        { "input": "[3, 1, 2]", "expected": "[1, 2, 3]", "actual": "[1, 2, 3]", "passed": true }
      ]
    }
    ```

#### 3.1.3 AI Recommendations
- `POST /api/v1/problems/recommend`
  - *Description*: Invokes LangChain/LangGraph agent workflow to fetch a contextually relevant problem path.
  - *Payload*: (Implicit from JWT, fetches profile metrics automatically)
  - *Response*:
    ```json
    {
      "recommended_problem": {
        "id": "uuid-str",
        "title": "Median of Two Sorted Arrays",
        "difficulty": "Hard",
        "tags": ["Array", "Binary Search", "Divide and Conquer"],
        "description_markdown": "### Problem Statement...",
        "template_code": "def findMedianSortedArrays(nums1, nums2):\n    pass"
      },
      "agent_reasoning": "We selected this problem because you recently failed an Array binary search test case and indicated you wanted to focus on interview questions from FAANG companies."
    }
    ```

#### 3.1.4 Mock Interviews
- `POST /api/v1/interviews/start`
  - *Payload*: `{"topic": "Data Structures", "difficulty": "Medium", "llm_provider": "anthropic"}`
  - *Response*: `{"session_id": "session-uuid", "websocket_url": "wss://host/api/v1/interviews/ws/session-uuid"}`
- `WebSocket /api/v1/interviews/ws/{session_id}`
  - *Message Types Received (Client -> Server)*:
    ```json
    {
      "type": "audio_chunk",
      "audio_payload": "base64-string"
    }
    // OR
    {
      "type": "text_message",
      "content": "I think we can solve this using two pointers."
    }
    // OR
    {
      "type": "code_sync",
      "code": "def solve(arr):\n    left, right = 0, len(arr)-1..."
    }
    ```
  - *Message Types Pushed (Server -> Client)*:
    ```json
    {
      "type": "interviewer_speech",
      "text": "Great start. How would you optimize the space complexity of this approach?",
      "audio_url": "https://s3.bucket/path/temp.mp3"
    }
    ```

---

## 4. Agent Logic Specification

This platform implements stateful, multi-agent frameworks using **LangGraph** to allow custom loops and branching logic during mock interview sessions.

### 4.1 Framework Comparison & Justification

| Feature | CrewAI | AutoGen | LlamaIndex | LangGraph (Selected) |
| :--- | :--- | :--- | :--- | :--- |
| **Workflow State Control** | Rigid roleplay | High autonomy | RAG focused | **High control over deterministic states** |
| **Looping & Branching** | Hard to configure | Natural | Linear | **Native execution graph loops (Cycles)** |
| **Conversational Memory**| Basic | Ephemeral | RAG index | **Custom state persistence across turns** |
| **Human-in-the-loop** | Limited | Yes | No | **Native graph interruptions & steps** |

### 4.2 Recommendation Agent Execution Graph

The recommendation agent maps a user's technical gaps by checking historical performance statistics and querying the vector database.

```mermaid
stateDiagram-v2
    [*] --> RetrieveUserHistory
    RetrieveUserHistory --> IdentifyGaps : Extract topics with low pass rate
    IdentifyGaps --> VectorQuery : Embed user skill gaps and query database
    VectorQuery --> FilterAlreadySolved : Drop questions user has already passed
    FilterAlreadySolved --> RankCandidates : Apply LLM ranking using active provider
    RankCandidates --> CreateReasoning : Generate explanation
    CreateReasoning --> [*]
```

#### Vector Similarity Matching Strategy
1. **Embedding Model**: Text descriptions of coding problems are indexed into Chroma Vector Database using `text-embedding-3-small` (OpenAI) or `text-embedding-004` (Gemini).
2. **Metadata Tagging**: Each vector object contains attributes: `{ "difficulty": "Medium", "topics": ["Trees", "BFS"], "id": "uuid" }`.
3. **Similarity Search**: When a user needs a recommendation, their weak topics (e.g., "Dynamic Programming") are combined with their target difficulty to generate a query embedding. We perform a cosine-similarity query on Chroma filtered by metadata:
   $$\text{Similarity} = \frac{A \cdot B}{\|A\| \|B\|}$$
4. **LLM Synthesis**: The top 5 semantic matches are passed to the active LLM to select the most pedagogical next step.

### 4.3 Mock Interview Agent State Machine (LangGraph)

The interview session runs within a structured state machine to simulate a live technical interviewer.

```mermaid
graph TD
    Start([Start Interview]) --> NodeInit[Init State: Select Problem]
    NodeInit --> NodeAsk[Node: Generate & Ask Question]
    NodeAsk --> NodeWait[Wait for User Input]
    NodeWait --> NodeEval{Node: Evaluate Submission}
    
    NodeEval -->|Correct & Good Description| NodeFollowUp[Node: Challenge Optimizations]
    NodeEval -->|Incorrect / Syntax Error| NodeHintCount{Hint count < 2?}
    NodeEval -->|Completely Stuck / Timeout| NodeAnswerExplain[Node: Explain Solution Pattern]
    
    NodeHintCount -->|Yes| NodeHint[Node: Provide Subtle Hint] --> NodeWait
    NodeHintCount -->|No| NodeAnswerExplain
    
    NodeFollowUp --> NodeWait
    NodeAnswerExplain --> NodeGrade[Node: Grade & Terminate]
    NodeFollowUp -->|Optimizations Answered| NodeGrade
    NodeGrade --> End([End Session])
```

#### 4.3.1 Critical Prompts

**Prompt Template: Question Generator / Dialog Engine**
```
You are an expert technical interviewer at a tier-1 technology company. 
You are conducting a live, interactive coding interview with the user.

USER PROFILE:
- Target Role: Software Engineer (Backend)
- Experience Level: Junior (1-3 Years)
- Target Problem: {{problem_title}}
- Problem Context: {{problem_description}}

CURRENT STATE:
- Dialog History: {{chat_history}}
- Code currently written in editor: 
```python
{{user_code}}
```

TASK:
Review the dialogue history and the user's active code workspace.
1. If the interview has just started, introduce yourself professionally and present the problem statement clearly without showing the solution.
2. If the user submitted code, analyze correctness, computational complexities, and style.
3. If they made a logic error, do NOT give the answer. Instead, formulate a guiding question (hint) that points them towards the edge-case they missed.
4. Keep your output concise, professional, and conversational. 

Provide your response in JSON format:
{
  "interviewer_speech": "Your vocal response to show the user.",
  "hint_given": true/false,
  "execution_action": "CONTINUE" // "CONTINUE" | "PROBE_COMPLEXITY" | "TERMINATE"
}
```

**Prompt Template: Scoring & Evaluation Agent**
```
You are the Lead Calibrations Panel member evaluating a completed coding mock interview.
Your job is to provide objective feedback and an overall score.

INTERVIEW DATA:
- Problem: {{problem_title}}
- Transcript: {{chat_history}}
- Final Code Submitted:
```python
{{final_code}}
```

EVALUATION CRITERIA:
1. Problem Solving (5-point scale): Did they find the optimal solution? Did they struggle with basic loops/structures?
2. Coding Performance (5-point scale): Code efficiency, readability, and syntax correctness.
3. Communication (5-point scale): Did they explain their thought process? Did they respond well to feedback/hints?
4. Time Management (5-point scale): Did they solve it within the limits?

Provide the calibration results in JSON format:
{
  "scores": {
    "problem_solving": 4.2,
    "coding": 3.8,
    "communication": 4.5,
    "time_management": 3.0
  },
  "overall_score": 3.88,
  "strengths": ["Excellent verbal flow", "Quick to implement initial brute-force approach"],
  "weaknesses": ["Slow to optimize array lookups", "Missed empty-array edge cases on first run"],
  "detailed_feedback": "Paragraph outlining structural learning suggestions..."
}
```

### 4.4 LLM Failover & API Management Client

To protect against rate-limiting (HTTP 429) or remote service downtime, the application routes all LLM calls through a resilient factory class.

```python
import time
import logging
from typing import Dict, Any

class LLMClientFactory:
    def __init__(self):
        self.providers = ["anthropic", "openai", "gemini"]
        logging.basicConfig(level=logging.INFO)

    def _call_provider_api(self, provider: str, prompt: str, system_instruction: str) -> str:
        # Dummy representation of provider SDK initializations
        if provider == "anthropic":
            # Simulate Anthropic API Client Call
            return "Claude Response"
        elif provider == "openai":
            # Simulate OpenAI Client Call
            return "GPT-4o Response"
        elif provider == "gemini":
            # Simulate Google Gemini Client Call
            return "Gemini 1.5 Pro Response"
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def generate_completion(self, primary_provider: str, prompt: str, system_instruction: str) -> str:
        provider_chain = [primary_provider] + [p for p in self.providers if p != primary_provider]
        
        for provider in provider_chain:
            retries = 3
            backoff = 1.0
            while retries > 0:
                try:
                    logging.info(f"Attempting completion with LLM provider: {provider}")
                    # In production, replace this stub with actual library API calls
                    response = self._call_provider_api(provider, prompt, system_instruction)
                    return response
                except Exception as e:
                    retries -= 1
                    logging.warning(f"Error calling {provider}: {str(e)}. Retries left: {retries}")
                    if retries > 0:
                        time.sleep(backoff)
                        backoff *= 2.0  # Exponential backoff
            logging.error(f"Provider {provider} failed all retries. Falling back to next provider in chain.")
        
        raise RuntimeError("Critical Error: All configured LLM providers failed to execute prompt.")
```

---

## 5. Database Schema

The database architecture maps user identity, problem structures, vector embedding relationships, and state histories.

### 5.1 Relational Entity Diagram

```mermaid
erDiagram
    USERS {
        uuid id PK
        string email UK
        string password_hash
        timestamp created_at
    }
    USER_PROFILES {
        uuid id PK
        uuid user_id FK
        string current_skill_level
        jsonb weak_topics
        timestamp updated_at
    }
    PROBLEMS {
        uuid id PK
        string title
        text description
        string difficulty
        string category
        integer time_limit_ms
        integer memory_limit_mb
        jsonb template_code
    }
    TEST_CASES {
        uuid id PK
        uuid problem_id FK
        text input_data
        text expected_output
        boolean is_hidden
    }
    USER_SUBMISSIONS {
        uuid id PK
        uuid user_id FK
        uuid problem_id FK
        text code
        string language
        string status
        integer execution_time_ms
        integer memory_used_mb
        timestamp created_at
    }
    INTERVIEW_SESSIONS {
        uuid id PK
        uuid user_id FK
        string topic
        string status
        float overall_score
        text final_feedback
        timestamp created_at
        timestamp ended_at
    }
    INTERVIEW_DIALOGUES {
        uuid id PK
        uuid session_id FK
        string speaker
        text message
        text code_submitted
        text code_feedback
        timestamp created_at
    }

    USERS ||--|| USER_PROFILES : "has"
    USERS ||--o{ USER_SUBMISSIONS : "submits"
    USERS ||--o{ INTERVIEW_SESSIONS : "undertakes"
    PROBLEMS ||--o{ TEST_CASES : "contains"
    PROBLEMS ||--o{ USER_SUBMISSIONS : "references"
    INTERVIEW_SESSIONS ||--o{ INTERVIEW_DIALOGUES : "logs"
```

### 5.2 SQL DDL (PostgreSQL Schema Definition)

```sql
-- Enable UUID Extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Users Table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX idx_users_email ON users(email);

-- 2. User Profiles Table
CREATE TABLE user_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    current_skill_level VARCHAR(50) DEFAULT 'Beginner' NOT NULL,
    weak_topics JSONB DEFAULT '[]'::jsonb NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- 3. Problems Table
CREATE TABLE problems (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    difficulty VARCHAR(50) NOT NULL,
    category VARCHAR(100) NOT NULL,
    time_limit_ms INTEGER DEFAULT 2000 NOT NULL,
    memory_limit_mb INTEGER DEFAULT 256 NOT NULL,
    template_code JSONB NOT NULL
);
CREATE INDEX idx_problems_difficulty ON problems(difficulty);
CREATE INDEX idx_problems_category ON problems(category);

-- 4. Test Cases Table
CREATE TABLE test_cases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    problem_id UUID NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    input_data TEXT NOT NULL,
    expected_output TEXT NOT NULL,
    is_hidden BOOLEAN DEFAULT TRUE NOT NULL
);

-- 5. User Submissions Table
CREATE TABLE user_submissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    problem_id UUID NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    language VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL, -- e.g., 'ACCEPTED', 'WRONG_ANSWER', 'COMPILE_ERROR', 'TIME_LIMIT_EXCEEDED'
    execution_time_ms INTEGER NOT NULL,
    memory_used_mb INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX idx_submissions_user_problem ON user_submissions(user_id, problem_id);

-- 6. Interview Sessions Table
CREATE TABLE interview_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'ACTIVE' NOT NULL, -- 'ACTIVE', 'COMPLETED', 'FAILED'
    overall_score NUMERIC(3, 2),
    final_feedback TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    ended_at TIMESTAMP WITH TIME ZONE
);

-- 7. Interview Dialogues Table
CREATE TABLE interview_dialogues (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    speaker VARCHAR(50) NOT NULL, -- 'INTERVIEWER', 'USER'
    message TEXT NOT NULL,
    code_submitted TEXT,
    code_feedback TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX idx_dialogues_session ON interview_dialogues(session_id);
```

---

## 6. Deployment & DevOps Strategy

The system deployment pipeline ensures reliable builds and horizontal auto-scaling components to maintain sub-500ms execution times.

### 6.1 Containerization Design (Docker & Docker Compose)

#### 6.1.1 Backend Production Dockerfile
```dockerfile
# Stage 1: Build virtual environment
FROM python:3.11-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc build-essential

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime image
FROM python:3.11-slim AS runner

WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 6.1.2 Docker Compose Configuration (Development / Staging Stack)
```yaml
version: '3.8'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/placement_db
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - redis

  celery_worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: celery -A app.worker.celery worker --loglevel=info
    environment:
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/placement_db
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      - redis
      - postgres

  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=placement_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  postgres_data:
```

### 6.2 CI/CD Pipeline (GitHub Actions)

This pipeline runs test suites and builds production containers upon merging code changes to `main`.

```yaml
name: Placement Prep Agent CI/CD

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test-and-lint:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install flake8 pytest
          if [ -f backend/requirements.txt ]; then pip install -r backend/requirements.txt; fi

      - name: Lint with flake8
        run: |
          # stop the build if there are Python syntax errors or undefined names
          flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
          # exit-zero treats all errors as warnings
          flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

      - name: Run Backend Unit Tests
        run: |
          pytest backend/tests/

  build-and-deploy:
    needs: test-and-lint
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v3

      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v1
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v1

      - name: Build, tag, and push image to Amazon ECR
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          ECR_REPOSITORY: placement-prep-backend
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG -t $ECR_REGISTRY/$ECR_REPOSITORY:latest -f backend/Dockerfile backend/
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:latest

      - name: Deploy to Amazon ECS Task Definition
        run: |
          aws ecs update-service --cluster placement-prep-cluster --service backend-service --force-new-deployment
```

### 6.3 Cloud Deployment Strategy (AWS Recommendation)

```
                       [ AWS Cloud (us-east-1) ]
                                   │
                                   ▼
                         Route53 DNS Routing
                                   │
                                   ▼
                    AWS CloudFront (CDN Cache Static Frontend)
                                   │
                                   ▼
                     AWS Application Load Balancer
                 ┌─────────────────┴─────────────────┐
                 ▼                                   ▼
         ECS Fargate App Tasks               ECS Fargate Tasks
         (FastAPI Backend APIs)            (Celery Worker Engine)
                 │                                   │
         ┌───────┴───────┬───────────────┐           │
         ▼               ▼               ▼           ▼
   Amazon RDS       ElastiCache     Pinecone     Secure Virtual
  (PostgreSQL)        (Redis)     (Vector DB)     Sandbox Pods
```

#### Multi-Zone Scale Strategy
1. **API Routing**: High scalability managed via AWS Elastic Load Balancing forwarding payloads to **ECS Fargate Tasks** in public subnets across availability zones.
2. **Persistence Integrity**: PostgreSQL database runs on **Amazon RDS Multi-AZ** configured with replication to enable automated failovers.
3. **Sandbox Guarding**: The Celery containers request isolated run nodes configured inside private networks without public routing.

### 6.4 Latency & Execution Performance Optimization

- **Pre-warmed Sandbox Containers**: Celery workers maintain a warm pool of runtime images ready to run code instantly, avoiding container cold-start delays.
- **Cache Strategy**: User progress statistics, daily lists, and vector database lookups are cached directly in Redis with explicit TTLs (Time-To-Live).
- **Audio Streaming Optimization**: Transcripts are streamed chunk-by-chunk using WebSockets, while Text-to-Speech audio is generated asynchronously and sent as small MP3 segments, reducing time-to-first-sound.

---

## 7. Implementation Roadmap

This roadmap breaks down the development phase into 5 execution sprints.

```mermaid
gantt
    title Placement Preparation Agent - 10-Week Implementation Roadmap
    dateFormat  YYYY-MM-DD
    section Phase 1: Foundations
    DB Design & Postgres Schema Init   :active, des1, 2026-07-06, 7d
    Backend Dev Environment & Celery Docker Config :active, des2, 2026-07-09, 6d
    section Phase 2: Code Execution
    Sandboxed Code Execution Microservice :des3, 2026-07-13, 10d
    Monaco Editor UI & Stream Console    :des4, 2026-07-20, 8d
    section Phase 3: AI Agents
    Vector Database indexing & Chroma Integration :des5, 2026-07-27, 7d
    LangGraph Recommendation Flow & Prompts :des6, 2026-07-31, 10d
    Mock Interview Agent State Machine Logic :des7, 2026-08-04, 12d
    section Phase 4: Frontend UI
    Main App Workspace & Zustand Stores   :des8, 2026-08-14, 8d
    Dashboard UI & Analytics Visualization :des9, 2026-08-20, 7d
    section Phase 5: CI/CD & Deploy
    GitHub Actions pipeline Setup          :des10, 2026-08-27, 5d
    AWS Cloud Deployment & System Hardening:des11, 2026-09-01, 7d
```
