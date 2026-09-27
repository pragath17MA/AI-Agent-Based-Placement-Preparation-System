"use client";

import React, { useState, useEffect, useRef } from 'react';
import Editor from '@monaco-editor/react';

interface DialogueMessage {
  speaker: 'INTERVIEWER' | 'USER';
  message: string;
}

interface LiveScores {
  communication: number;
  confidence: number;
  technical_knowledge: number;
  problem_solving: number;
  coding_style: number;
  optimization: number;
  time_complexity: number;
  space_complexity: number;
  edge_cases: number;
  code_quality: number;
  feedback?: string;
}

interface Checklist {
  clarified_requirements: boolean;
  discussed_brute_force: boolean;
  implemented_optimal_code: boolean;
  analyzed_complexity: boolean;
  handled_edge_cases: boolean;
}

export default function InterviewWorkspace() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [activeProblem, setActiveProblem] = useState<any>(null);
  const [chat, setChat] = useState<DialogueMessage[]>([]);
  const [userInput, setUserInput] = useState('');
  const [code, setCode] = useState('');
  const [notes, setNotes] = useState(''); // Notes pad for verbal interviews (system design/hr)
  const [timeRemaining, setTimeRemaining] = useState(2700); // 45 minutes
  const [interviewStatus, setInterviewStatus] = useState<'idle' | 'running' | 'completed'>('idle');
  const [feedbackReport, setFeedbackReport] = useState<any>(null);
  
  // Setup inputs
  const [selectedTopic, setSelectedTopic] = useState('Data Structures & Algorithms');
  const [selectedDifficulty, setSelectedDifficulty] = useState('Easy');
  const [selectedProvider, setSelectedProvider] = useState('openai');
  const [providers, setProviders] = useState<Record<string, boolean>>({});

  // Real-time evaluation scorecard state
  const [liveEvaluation, setLiveEvaluation] = useState<LiveScores>({
    communication: 7.0,
    confidence: 7.0,
    technical_knowledge: 7.0,
    problem_solving: 7.0,
    coding_style: 7.0,
    optimization: 7.0,
    time_complexity: 7.0,
    space_complexity: 7.0,
    edge_cases: 7.0,
    code_quality: 7.0,
    feedback: "Awaiting your first responses to calibrate scores..."
  });
  
  const [checklist, setChecklist] = useState<Checklist>({
    clarified_requirements: false,
    discussed_brute_force: false,
    implemented_optimal_code: false,
    analyzed_complexity: false,
    handled_edge_cases: false
  });

  const [loading, setLoading] = useState(false);
  const [thinking, setThinking] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Scroll chat to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chat, thinking]);

  // Load configured providers list
  useEffect(() => {
    async function loadProviders() {
      try {
        const res = await fetch('http://localhost:8000/api/v1/providers');
        if (res.ok) {
          const list = await res.json();
          setProviders(list);
          const firstAvailable = Object.keys(list).find(k => list[k]);
          if (firstAvailable) {
            setSelectedProvider(firstAvailable);
          }
        }
      } catch (err) {
        console.warn("Could not query providers list.", err);
      }
    }
    loadProviders();
  }, []);

  // Timer Countdown
  useEffect(() => {
    if (interviewStatus !== 'running') return;
    const interval = setInterval(() => {
      setTimeRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          handleConcludeInterview();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [interviewStatus]);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const handleStartInterview = async () => {
    setLoading(true);
    setChat([]);
    setFeedbackReport(null);
    setTimeRemaining(2700);
    setLiveEvaluation({
      communication: 7.0,
      confidence: 7.0,
      technical_knowledge: 7.0,
      problem_solving: 7.0,
      coding_style: 7.0,
      optimization: 7.0,
      time_complexity: 7.0,
      space_complexity: 7.0,
      edge_cases: 7.0,
      code_quality: 7.0,
      feedback: "Interviewer is greeting you. Walk through your problem understanding."
    });
    setChecklist({
      clarified_requirements: false,
      discussed_brute_force: false,
      implemented_optimal_code: false,
      analyzed_complexity: false,
      handled_edge_cases: false
    });

    try {
      const res = await fetch('http://localhost:8000/api/v1/interviews/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: "anonymous",
          topic: selectedTopic,
          difficulty: selectedDifficulty,
          model: selectedProvider
        })
      });

      if (res.ok) {
        const data = await res.json();
        setSessionId(data.session_id);
        setActiveProblem(data.problem);
        setCode(data.problem.template_code?.["python"] || "");
        setNotes("");
        setChat([{ speaker: 'INTERVIEWER', message: data.initial_message }]);
        setInterviewStatus('running');
      } else {
        throw new Error("API call failed");
      }
    } catch (err) {
      console.warn("Backend API offline. Starting local mock interview session.", err);
      setSessionId("mock-session-123");
      setActiveProblem({
        id: "non-coding",
        title: `${selectedTopic} Concept Session`,
        description: `Deep-dive interview on ${selectedTopic} at ${selectedDifficulty} level.`,
        template_code: { "python": "# Offline Mock Sandbox" }
      });
      setCode("# Offline Mock Sandbox");
      setNotes("");
      setChat([{
        speaker: 'INTERVIEWER',
        message: `Hello! Welcome to your technical mock interview on ${selectedTopic}. Let's discuss your experience and problem statement. Walk me through your design patterns or algorithm strategy.`
      }]);
      setInterviewStatus('running');
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async () => {
    if (!userInput.trim() || sendingMessageRef.current) return;
    sendingMessageRef.current = true;
    const currentInput = userInput;
    setUserInput('');

    // Append user response
    setChat((prev) => [...prev, { speaker: 'USER', message: currentInput }]);
    setThinking(true);

    const isNonCoding = activeProblem?.id === "non-coding";
    const userWorkspaceContent = isNonCoding ? notes : code;

    try {
      const res = await fetch('http://localhost:8000/api/v1/interviews/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          user_message: currentInput,
          user_code: userWorkspaceContent,
          model: selectedProvider
        })
      });

      if (res.ok) {
        const data = await res.json();
        setChat((prev) => [...prev, { speaker: 'INTERVIEWER', message: data.response_message }]);
        
        // Sync live scorecard
        if (data.live_evaluation) {
          setLiveEvaluation(data.live_evaluation);
          
          // Map checklist based on metrics
          const scores = data.live_evaluation;
          setChecklist({
            clarified_requirements: scores.problem_solving >= 7.2,
            discussed_brute_force: scores.optimization >= 7.0,
            implemented_optimal_code: scores.code_quality >= 7.2,
            analyzed_complexity: scores.time_complexity >= 7.2,
            handled_edge_cases: scores.edge_cases >= 7.2
          });
        }

        if (data.status === 'COMPLETED') {
          // Trigger final report loading
          await loadFinalReport(sessionId!);
        }
      }
    } catch (err) {
      setTimeout(() => {
        let aiResponse = "Excellent points. How would you explain the time and space complexity constraints of this approach?";
        if (currentInput.toLowerCase().includes("complexity") || currentInput.toLowerCase().includes("big o")) {
          aiResponse = "Exactly! Keeping spatial complexity minimal is key. Go ahead and sketch out your edge case protections.";
        }
        setChat((prev) => [...prev, { speaker: 'INTERVIEWER', message: aiResponse }]);
        
        // Update mock scorecard slightly to show interactivity
        setLiveEvaluation(prev => ({
          ...prev,
          communication: Math.min(10.0, prev.communication + 0.3),
          confidence: Math.min(10.0, prev.confidence + 0.2),
          feedback: "Great conversational flow. Focus on space complexity limits."
        }));
      }, 800);
    } finally {
      setThinking(false);
      sendingMessageRef.current = false;
    }
  };

  const sendingMessageRef = useRef(false);

  const loadFinalReport = async (sessId: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/v1/interviews/${sessId}/report`);
      if (res.ok) {
        const data = await res.json();
        setFeedbackReport(data);
        setInterviewStatus('completed');
      }
    } catch (err) {
      setInterviewStatus('completed');
      setFeedbackReport({
        overall_score: 8.2,
        scores: liveEvaluation,
        strengths: ["Strong problem identification", "Excellent verbal explanation of optimizations"],
        weaknesses: ["Needs faster coding execution", "Missed array size limit bounds initially"],
        final_feedback: "You demonstrated solid Software Engineering readiness. Focus on speed limits and dry-running code constraints.",
        topic_scores: { "Data Structures": 8.0, "Algorithms": 7.8, "Communication": 8.5, "Systems/Core CS": 8.0 },
        recommendations: {
          problems: [
            { "title": "Two Sum", "difficulty": "Easy", "category": "Arrays" },
            { "title": "Binary Search", "difficulty": "Easy", "category": "Searching" }
          ],
          videos: [
            { "title": "Big-O Notation Deep Dive", "url": "https://www.youtube.com/watch?v=TG6418w1" }
          ],
          articles: [
            { "title": "System Design Shortener Patterns", "url": "https://medium.com/tech-prep" }
          ]
        },
        roadmap: [
          "Practice daily Array and Hashmap puzzles under 25-minute targets.",
          "Speak your logic out loud while writing algorithms.",
          "Examine index limits and null pointers beforehand."
        ],
        placement_readiness: 82.0
      });
    }
  };

  const handleConcludeInterview = async () => {
    setLoading(true);
    const isNonCoding = activeProblem?.id === "non-coding";
    const userWorkspaceContent = isNonCoding ? notes : code;

    try {
      const res = await fetch('http://localhost:8000/api/v1/interviews/end', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          user_code: userWorkspaceContent
        })
      });
      if (res.ok) {
        await loadFinalReport(sessionId!);
      }
    } catch (err) {
      await loadFinalReport(sessionId || "mock-session-123");
    } finally {
      setLoading(false);
    }
  };

  const isNonCodingTopic = activeProblem?.id === "non-coding";

  return (
    <div style={{ padding: '1rem', height: 'calc(100vh - 70px)', display: 'flex', flexDirection: 'column', background: 'var(--bg-primary)' }}>
      {/* Control Bar Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '0.75rem 1.5rem',
        backgroundColor: 'var(--bg-secondary)',
        border: '1px solid var(--glass-border)',
        borderRadius: '0.75rem',
        marginBottom: '1rem',
        boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)'
      }}>
        <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 800, background: 'linear-gradient(to right, #fff, #a1a1aa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            🎙️ AI Calibrated Interview Workspace
          </h2>
          {interviewStatus === 'running' && (
            <span style={{
              color: 'var(--accent-error)',
              backgroundColor: 'rgba(239,68,68,0.1)',
              border: '1px solid rgba(239,68,68,0.2)',
              padding: '0.3rem 0.75rem',
              borderRadius: '2rem',
              fontWeight: 700,
              fontFamily: 'var(--font-mono)',
              fontSize: '0.85rem'
            }}>
              ⏱️ Time Left: {formatTime(timeRemaining)}
            </span>
          )}
        </div>
        <div>
          {interviewStatus === 'running' && (
            <button className="btn" onClick={handleConcludeInterview} style={{ backgroundColor: 'var(--accent-error)', color: 'white', border: '1px solid transparent' }}>
              Submit & Conclude Session
            </button>
          )}
        </div>
      </div>

      {/* Start Setup Config Panel */}
      {interviewStatus === 'idle' && (
        <div className="card" style={{ flex: 1, justifyContent: 'center', alignItems: 'center', textAlign: 'center', gap: '2rem', maxWidth: '800px', margin: '0 auto', padding: '3rem' }}>
          <span style={{ fontSize: '4rem', filter: 'drop-shadow(0 0 10px rgba(139, 92, 246, 0.4))' }}>🎙️</span>
          <div>
            <h2 style={{ fontSize: '1.8rem', fontWeight: 800, color: 'white' }}>Mock Interview Panel Simulation</h2>
            <p style={{ color: 'var(--text-secondary)', maxWidth: '550px', margin: '0.5rem auto 0 auto', fontSize: '0.95rem', lineHeight: '1.5' }}>
              Test your proficiency under real-time conditions. The agent acts as a live calibrations engineer, updating your performance scorecard turn-by-turn.
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1.5rem', width: '100%', maxWidth: '650px', margin: '1rem 0' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', textAlign: 'left' }}>
              <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 600 }}>Category Topic</label>
              <select 
                value={selectedTopic} 
                onChange={(e) => setSelectedTopic(e.target.value)}
                style={{ background: '#111827', border: '1px solid var(--glass-border)', padding: '0.6rem 0.8rem', borderRadius: '0.5rem', color: 'white', outline: 'none', cursor: 'pointer' }}
              >
                <option value="Data Structures & Algorithms">DS & Algorithms (Coding)</option>
                <option value="System Design">System Design (Verbal)</option>
                <option value="Low Level Design">Low Level Design (LLD)</option>
                <option value="Behavioral Interview">Behavioral Interview</option>
                <option value="Core CS">Core CS (OS, DBMS, OOP)</option>
              </select>
            </div>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', textAlign: 'left' }}>
              <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 600 }}>Initial Difficulty</label>
              <select 
                value={selectedDifficulty} 
                onChange={(e) => setSelectedDifficulty(e.target.value)}
                style={{ background: '#111827', border: '1px solid var(--glass-border)', padding: '0.6rem 0.8rem', borderRadius: '0.5rem', color: 'white', outline: 'none', cursor: 'pointer' }}
              >
                <option value="Easy">Easy Mode</option>
                <option value="Medium">Medium Mode</option>
                <option value="Hard">Hard Mode</option>
              </select>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', textAlign: 'left' }}>
              <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 600 }}>LLM Provider Core</label>
              <select 
                value={selectedProvider} 
                onChange={(e) => setSelectedProvider(e.target.value)}
                style={{ background: '#111827', border: '1px solid var(--glass-border)', padding: '0.6rem 0.8rem', borderRadius: '0.5rem', color: 'white', outline: 'none', cursor: 'pointer' }}
              >
                <option value="openai">OpenAI GPT-4o</option>
                <option value="gemini">Gemini 1.5 Flash</option>
                <option value="anthropic">Claude 3.5 Sonnet</option>
                <option value="groq">Groq Llama 3.3</option>
                <option value="deepseek">DeepSeek Chat</option>
                <option value="openrouter">OpenRouter Llama</option>
                <option value="ollama">Ollama Local</option>
              </select>
            </div>
          </div>

          <button className="btn btn-primary" onClick={handleStartInterview} style={{ padding: '0.85rem 2.5rem', fontSize: '1rem' }} disabled={loading}>
            {loading ? "Initializing Agent Graph..." : "Initialize Calibration Interview"}
          </button>
        </div>
      )}

      {/* Final Comprehensive Report Dashboard */}
      {interviewStatus === 'completed' && feedbackReport && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1.5rem', overflowY: 'auto', padding: '1rem', animation: 'fadeIn 0.5s ease-out' }}>
          {/* Header Overview Card */}
          <div className="card" style={{ display: 'grid', gridTemplateColumns: '200px 1fr 250px', gap: '2rem', alignItems: 'center', borderLeft: '5px solid var(--accent-success)', background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.05) 0%, var(--glass-bg) 100%)' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', borderRight: '1px solid var(--glass-border)', paddingRight: '2rem' }}>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Overall Score</span>
              <span style={{ fontSize: '3.5rem', fontWeight: 800, color: 'var(--accent-success)', margin: '0.25rem 0' }}>{feedbackReport.overall_score || feedbackReport.score}/10</span>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', textAlign: 'center' }}>Calibrated by AI Panel</span>
            </div>

            <div>
              <h3 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'white' }}>Mock Interview Analysis Complete</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: '1.6', marginTop: '0.5rem' }}>
                {feedbackReport.final_feedback || feedbackReport.feedback}
              </p>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.02)', padding: '1.25rem', borderRadius: '0.75rem', border: '1px solid var(--glass-border)', textAlign: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 600, display: 'block', marginBottom: '0.25rem' }}>PLACEMENT READINESS</span>
              <span style={{ fontSize: '2.5rem', fontWeight: 800, color: 'var(--accent-warning)', display: 'block' }}>{feedbackReport.placement_readiness || 75}%</span>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Based on category benchmarks</span>
            </div>
          </div>

          {/* Detailed Metric Columns */}
          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '1.5rem' }}>
            {/* Left Metrics Details */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              {/* Scorecard Grids */}
              <div className="card">
                <h4 style={{ fontWeight: 700, borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem' }}>Performance Scorecard Breakdown</h4>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '0.5rem' }}>
                  {Object.keys(feedbackReport.scores || {}).filter(k => k !== 'feedback').map((metric) => {
                    const scoreVal = (feedbackReport.scores as any)[metric];
                    return (
                      <div key={metric} style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', textTransform: 'capitalize' }}>
                          <span style={{ color: 'var(--text-secondary)' }}>{metric.replace('_', ' ')}</span>
                          <span style={{ fontWeight: 600, color: 'white' }}>{scoreVal}/10</span>
                        </div>
                        <div style={{ height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '1rem', overflow: 'hidden' }}>
                          <div style={{ width: `${scoreVal * 10}%`, height: '100%', background: scoreVal >= 8 ? 'var(--accent-success)' : (scoreVal >= 6 ? 'var(--accent-warning)' : 'var(--accent-error)'), borderRadius: '1rem' }}></div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Strengths & Weaknesses */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                <div className="card" style={{ borderLeft: '4px solid var(--accent-success)' }}>
                  <h4 style={{ fontWeight: 700, color: 'white' }}>✅ Key Strengths</h4>
                  <ul style={{ paddingLeft: '1.25rem', marginTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.85rem', color: '#e4e4e7', lineHeight: '1.4' }}>
                    {feedbackReport.strengths?.map((str: string, i: number) => (
                      <li key={i}>{str}</li>
                    )) || <li>Good communications and coding flow.</li>}
                  </ul>
                </div>
                <div className="card" style={{ borderLeft: '4px solid var(--accent-error)' }}>
                  <h4 style={{ fontWeight: 700, color: 'white' }}>⚠️ Areas of Improvement</h4>
                  <ul style={{ paddingLeft: '1.25rem', marginTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.85rem', color: '#e4e4e7', lineHeight: '1.4' }}>
                    {feedbackReport.weaknesses?.map((wk: string, i: number) => (
                      <li key={i}>{wk}</li>
                    )) || <li>Optimize complex loop calculations.</li>}
                  </ul>
                </div>
              </div>

              {/* Roadmap */}
              <div className="card" style={{ borderLeft: '4px solid var(--accent-indigo)' }}>
                <h4 style={{ fontWeight: 700 }}>🛤️ Personalized 3-Step Preparation Roadmap</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '0.75rem' }}>
                  {feedbackReport.roadmap?.map((step: string, i: number) => (
                    <div key={i} style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start', background: 'rgba(255,255,255,0.01)', padding: '0.75rem 1rem', borderRadius: '0.5rem', border: '1px solid var(--glass-border)' }}>
                      <span style={{ background: 'var(--accent-indigo)', color: 'white', padding: '0.2rem 0.5rem', borderRadius: '50%', fontSize: '0.8rem', fontWeight: 700 }}>{i + 1}</span>
                      <p style={{ fontSize: '0.85rem', color: '#e4e4e7', lineHeight: '1.4' }}>{step}</p>
                    </div>
                  )) || <div>No steps logged. Focus on dynamic programming.</div>}
                </div>
              </div>
            </div>

            {/* Right Recommendations Column */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              {/* Practice Problems */}
              <div className="card">
                <h4 style={{ fontWeight: 700 }}>🎯 Recommended Practice Challenges</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.75rem' }}>
                  {feedbackReport.recommendations?.problems?.map((prob: any, i: number) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem 1rem', background: 'rgba(255,255,255,0.02)', borderRadius: '0.5rem', border: '1px solid var(--glass-border)', fontSize: '0.85rem' }}>
                      <div>
                        <strong style={{ color: 'white' }}>{prob.title}</strong>
                        <span style={{ display: 'block', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{prob.category}</span>
                      </div>
                      <span style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem', borderRadius: '1rem', background: 'rgba(99,102,241,0.1)', color: '#c7d2fe', fontWeight: 600 }}>
                        {prob.difficulty}
                      </span>
                    </div>
                  )) || <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Solve synthetic Array and dynamic algorithms.</div>}
                </div>
              </div>

              {/* Videos & Articles */}
              <div className="card">
                <h4 style={{ fontWeight: 700 }}>🎥 Educational Videos & Articles</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.75rem' }}>
                  {feedbackReport.recommendations?.videos?.map((vid: any, i: number) => (
                    <a key={i} href={vid.url} target="_blank" rel="noreferrer" style={{ textDecoration: 'none', padding: '0.75rem 1rem', background: 'rgba(255,255,255,0.02)', borderRadius: '0.5rem', border: '1px solid var(--glass-border)', fontSize: '0.85rem', color: 'white', display: 'flex', alignItems: 'center', gap: '0.5rem', transition: 'background 0.2s' }} onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'} onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}>
                      <span>▶️</span>
                      <div>
                        <strong>{vid.title}</strong>
                        <span style={{ display: 'block', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Video Resource</span>
                      </div>
                    </a>
                  ))}
                  {feedbackReport.recommendations?.articles?.map((art: any, i: number) => (
                    <a key={i} href={art.url} target="_blank" rel="noreferrer" style={{ textDecoration: 'none', padding: '0.75rem 1rem', background: 'rgba(255,255,255,0.02)', borderRadius: '0.5rem', border: '1px solid var(--glass-border)', fontSize: '0.85rem', color: 'white', display: 'flex', alignItems: 'center', gap: '0.5rem', transition: 'background 0.2s' }} onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'} onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}>
                      <span>📄</span>
                      <div>
                        <strong>{art.title}</strong>
                        <span style={{ display: 'block', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Tech Article</span>
                      </div>
                    </a>
                  ))}
                </div>
              </div>

              <button className="btn btn-success" onClick={handleStartInterview} style={{ padding: '0.85rem 0', width: '100%', fontSize: '0.95rem' }}>
                Restart New Interview Session
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Active 3-Panel Simulation Workspace */}
      {interviewStatus === 'running' && activeProblem && (
        <div className="interview-container" style={{ flex: 1, minHeight: 0, display: 'grid', gridTemplateColumns: '320px 1fr 300px', gap: '1rem', marginTop: '0.5rem' }}>
          {/* Column 1: Dialogue Chat Panel */}
          <div className="chat-panel" style={{ borderRadius: '0.75rem', border: '1px solid var(--glass-border)', display: 'flex', flexDirection: 'column', background: 'var(--bg-secondary)', overflow: 'hidden' }}>
            {/* Visual Waveform Animation header */}
            <div style={{ background: '#111827', padding: '0.75rem 1rem', borderBottom: '1px solid var(--glass-border)', display: 'flex', alignItems: 'center', gap: '0.5rem', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <div style={{ display: 'flex', gap: '2px', height: '14px', alignItems: 'center' }}>
                  <div className="bar" style={{ width: '2px', height: '8px', background: 'var(--accent-agent)', animation: 'bounce 0.8s infinite alternate' }}></div>
                  <div className="bar" style={{ width: '2px', height: '14px', background: 'var(--accent-agent)', animation: 'bounce 0.5s infinite alternate 0.2s' }}></div>
                  <div className="bar" style={{ width: '2px', height: '10px', background: 'var(--accent-agent)', animation: 'bounce 0.6s infinite alternate 0.4s' }}></div>
                </div>
                <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'white' }}>Interviewer Core</span>
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', textTransform: 'capitalize' }}>Engine: {selectedProvider}</span>
            </div>

            <div className="chat-history" style={{ flex: 1, overflowY: 'auto', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {chat.map((msg, index) => (
                <div key={index} className={`chat-bubble ${msg.speaker.toLowerCase()}`} style={{ padding: '0.85rem 1rem', borderRadius: '0.75rem' }}>
                  <strong>{msg.speaker === 'INTERVIEWER' ? 'AI Panelist' : 'You'}:</strong>
                  <p style={{ marginTop: '0.25rem', whiteSpace: 'pre-wrap', fontSize: '0.88rem', lineHeight: '1.5' }}>{msg.message}</p>
                </div>
              ))}
              {thinking && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', alignSelf: 'flex-start', background: 'rgba(255,255,255,0.02)', padding: '0.5rem 0.85rem', borderRadius: '0.75rem', border: '1px solid var(--glass-border)' }}>
                  <div style={{ width: '6px', height: '6px', background: '#8b5cf6', borderRadius: '50%', animation: 'pulse 1.2s infinite' }}></div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Interviewer is evaluating...</span>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            <div className="chat-input-area" style={{ padding: '0.75rem', borderTop: '1px solid var(--glass-border)', display: 'flex', gap: '0.5rem' }}>
              <input
                type="text"
                className="chat-input"
                placeholder="Discuss solution logic or ask questions..."
                value={userInput}
                onChange={(e) => setUserInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                disabled={thinking}
                style={{ fontSize: '0.85rem', padding: '0.6rem 0.8rem' }}
              />
              <button className="btn btn-primary" onClick={handleSendMessage} disabled={thinking} style={{ padding: '0 1rem' }}>
                Send
              </button>
            </div>
          </div>

          {/* Column 2: Code Editor Workspace or Notes Canvas */}
          <div style={{ display: 'flex', flexDirection: 'column', height: '100%', borderRadius: '0.75rem', border: '1px solid var(--glass-border)', overflow: 'hidden' }}>
            <div style={{
              padding: '1rem',
              backgroundColor: '#111827',
              borderBottom: '1px solid var(--glass-border)',
              overflowY: 'auto',
              maxHeight: '180px'
            }}>
              <h4 style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--accent-agent)' }}>Active Challenge: {activeProblem.title}</h4>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: '0.25rem', lineHeight: '1.4', whiteSpace: 'pre-wrap' }}>{activeProblem.description}</p>
            </div>
            
            <div style={{ flex: 1, backgroundColor: '#09090b', minHeight: 0 }}>
              {isNonCodingTopic ? (
                /* Verbal discussion Notes workspace */
                <div style={{ height: '100%', display: 'flex', flexDirection: 'column', padding: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 600 }}>Design Notes / Scribble Canvas</span>
                    <span style={{ fontSize: '0.7rem', background: 'rgba(99,102,241,0.1)', color: '#c7d2fe', padding: '0.2rem 0.5rem', borderRadius: '0.25rem' }}>Verbal Discussion Active</span>
                  </div>
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Use this workspace to draft system design schemas, database columns, API signatures, or bullet-point structural layouts. Your notes are fed to the evaluation agent..."
                    style={{
                      flex: 1,
                      width: '100%',
                      background: '#111827',
                      color: 'white',
                      border: '1px solid var(--glass-border)',
                      borderRadius: '0.5rem',
                      padding: '1rem',
                      outline: 'none',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.85rem',
                      lineHeight: '1.5',
                      resize: 'none'
                    }}
                  />
                </div>
              ) : (
                /* Monaco Code Canvas */
                <Editor
                  height="100%"
                  language="python"
                  theme="vs-dark"
                  value={code}
                  onChange={(val) => setCode(val || '')}
                  options={{
                    fontSize: 14,
                    minimap: { enabled: false },
                    automaticLayout: true,
                    tabSize: 4
                  }}
                />
              )}
            </div>
          </div>

          {/* Column 3: Live Real-Time Evaluation Dashboard */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', height: '100%', overflowY: 'auto' }}>
            {/* Live Score meters */}
            <div className="card" style={{ padding: '1rem', borderRadius: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <h4 style={{ fontSize: '0.85rem', fontWeight: 700, borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.4rem', color: 'white' }}>
                📊 Real-Time Scorecard
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {[
                  { label: "Problem Solving", val: liveEvaluation.problem_solving },
                  { label: "Technical Knowledge", val: liveEvaluation.technical_knowledge },
                  { label: "Communication", val: liveEvaluation.communication },
                  { label: "Optimization", val: liveEvaluation.optimization },
                  { label: "Edge Cases", val: liveEvaluation.edge_cases }
                ].map((item) => (
                  <div key={item.label} style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem' }}>
                      <span style={{ color: 'var(--text-secondary)' }}>{item.label}</span>
                      <span style={{ fontWeight: 700, color: 'white' }}>{item.val}/10</span>
                    </div>
                    <div style={{ height: '4px', background: 'rgba(255,255,255,0.05)', borderRadius: '1rem', overflow: 'hidden' }}>
                      <div style={{ width: `${item.val * 10}%`, height: '100%', background: 'var(--accent-indigo)', borderRadius: '1rem' }}></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Stage Checklist */}
            <div className="card" style={{ padding: '1rem', borderRadius: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <h4 style={{ fontSize: '0.85rem', fontWeight: 700, borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.4rem', color: 'white' }}>
                📋 Calibration Check
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.8rem' }}>
                {[
                  { label: "Clarify requirements & constraints", done: checklist.clarified_requirements },
                  { label: "Propose brute force & optimize", done: checklist.discussed_brute_force },
                  { label: "Optimal implementation written", done: checklist.implemented_optimal_code },
                  { label: "Analyze time/space complexities", done: checklist.analyzed_complexity },
                  { label: "Inspect boundaries & edge cases", done: checklist.handled_edge_cases }
                ].map((item, idx) => (
                  <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: item.done ? 'white' : 'var(--text-secondary)' }}>
                    <span style={{ fontSize: '1rem', color: item.done ? 'var(--accent-success)' : '#4b5563' }}>
                      {item.done ? "✓" : "○"}
                    </span>
                    <span style={{ textDecoration: item.done ? 'line-through' : 'none' }}>{item.label}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Real-time AI Commentary */}
            <div className="card" style={{ padding: '1rem', borderRadius: '0.75rem', borderLeft: '4px solid var(--accent-warning)', background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.04) 0%, var(--glass-bg) 100%)', flex: 1 }}>
              <h4 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'white' }}>💡 Real-time Evaluation</h4>
              <p style={{ fontSize: '0.8rem', color: '#d1d5db', lineHeight: '1.4', marginTop: '0.5rem', whiteSpace: 'pre-wrap' }}>
                {liveEvaluation.feedback}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Styled animation keyframes */}
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes bounce {
          0% { height: 4px; }
          100% { height: 14px; }
        }
        @keyframes pulse {
          0%, 100% { opacity: 0.4; transform: scale(0.9); }
          50% { opacity: 1; transform: scale(1.1); }
        }
      `}} />
    </div>
  );
}
