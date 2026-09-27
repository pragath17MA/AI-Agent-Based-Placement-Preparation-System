"use client";

import React, { useEffect, useState } from 'react';

interface Problem {
  id: string;
  title: string;
  difficulty: string;
  category: string;
}

export default function Dashboard() {
  const [problems, setProblems] = useState<Problem[]>([]);
  const [stats, setStats] = useState({
    solved: 0,
    submissions: 0,
    interviews: 0,
    avgScore: 0.0
  });
  const [skillLevel, setSkillLevel] = useState("Beginner");
  const [weakTopics, setWeakTopics] = useState<string[]>(["Arrays", "Searching"]);
  const [resume, setResume] = useState<any>(null);
  const [recommendation, setRecommendation] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  async function loadProblemsAndRecommendations(currentSkill: string, currentWeak: string[]) {
    try {
      const resRec = await fetch('http://localhost:8000/api/v1/problems/recommend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_skill: currentSkill,
          weak_topics: currentWeak
        })
      });
      if (resRec.ok) {
        const recData = await resRec.json();
        setRecommendation(recData);
      }
    } catch (err) {
      console.warn("Failed to fetch recommendation", err);
    }
  }

  useEffect(() => {
    async function loadDashboardData() {
      try {
        // Fetch Problems List
        const resProblems = await fetch('http://localhost:8000/api/v1/problems');
        if (resProblems.ok) {
          const data = await resProblems.json();
          setProblems(data);
        }

        // Fetch User Progress metrics
        const resProgress = await fetch('http://localhost:8000/api/v1/users/anonymous/progress');
        if (resProgress.ok) {
          const progressData = await resProgress.json();
          setStats({
            solved: progressData.solved_count,
            submissions: progressData.total_submissions,
            interviews: progressData.interview_count,
            avgScore: parseFloat(progressData.average_score.toFixed(1))
          });
          setSkillLevel(progressData.current_skill_level);
          setWeakTopics(progressData.weak_topics);
          setResume(progressData.resume);
          
          await loadProblemsAndRecommendations(progressData.current_skill_level, progressData.weak_topics);
        }
      } catch (err) {
        console.warn("FastAPI backend is offline. Rendering interactive mock dashboard view instead.", err);
        // Load static fallback mock data for standalone frontend mode
        setProblems([
          { id: "1", title: "Two Sum", difficulty: "Easy", category: "Arrays" },
          { id: "2", title: "Valid Parentheses", difficulty: "Easy", category: "Stacks" },
          { id: "3", title: "Binary Search", difficulty: "Easy", category: "Searching" }
        ]);
        setRecommendation({
          title: "Two Sum",
          difficulty: "Easy",
          category: "Arrays",
          reasoning: "Selected based on initial profile mapping and algorithm weakness vectoring."
        });
      } finally {
        setLoading(false);
      }
    }
    loadDashboardData();
  }, []);

  const handleResumeUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("http://localhost:8000/api/v1/resume/upload", {
        method: "POST",
        body: formData
      });
      if (res.ok) {
        const data = await res.json();
        setResume(data);
        setSkillLevel(data.current_skill_level);
        setWeakTopics(data.weak_topics);
        
        // Refetch stats to update dashboard info
        const resProgress = await fetch('http://localhost:8000/api/v1/users/anonymous/progress');
        if (resProgress.ok) {
          const progressData = await resProgress.json();
          setStats({
            solved: progressData.solved_count,
            submissions: progressData.total_submissions,
            interviews: progressData.interview_count,
            avgScore: parseFloat(progressData.average_score.toFixed(1))
          });
        }

        // Update recommendation
        await loadProblemsAndRecommendations(data.current_skill_level, data.weak_topics);
      }
    } catch (err) {
      console.error("Resume upload failed", err);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '2.5rem', animation: 'fadeIn 0.5s ease-out' }}>
      <div style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.1), transparent)', padding: '2rem', borderRadius: '1rem', border: '1px solid var(--glass-border)' }}>
        <h1 style={{ fontSize: '2.5rem', fontWeight: 800, marginBottom: '0.5rem', background: 'linear-gradient(to right, #fff, #a1a1aa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>Welcome Back, Developer</h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '1.1rem' }}>Track your algorithm proficiency, practice coding challenges, and ace your technical interviews.</p>
      </div>

      {/* Metrics Row */}
      <div className="dashboard-grid" style={{ padding: 0 }}>
        <div className="card">
          <span className="card-title">Problems Solved</span>
          <span className="card-value" style={{ background: 'linear-gradient(to right, #10b981, #34d399)', WebkitBackgroundClip: 'text' }}>{stats.solved}</span>
        </div>
        <div className="card">
          <span className="card-title">Total Submissions</span>
          <span className="card-value" style={{ background: 'linear-gradient(to right, #6366f1, #818cf8)', WebkitBackgroundClip: 'text' }}>{stats.submissions}</span>
        </div>
        <div className="card">
          <span className="card-title">Mock Interviews</span>
          <span className="card-value" style={{ background: 'linear-gradient(to right, #8b5cf6, #a78bfa)', WebkitBackgroundClip: 'text' }}>{stats.interviews}</span>
        </div>
        <div className="card">
          <span className="card-title">Avg. Interview Score</span>
          <span className="card-value" style={{ background: 'linear-gradient(to right, #f59e0b, #fbbf24)', WebkitBackgroundClip: 'text' }}>{stats.avgScore || "N/A"}{stats.avgScore ? "/10" : ""}</span>
        </div>
      </div>

      {/* Two Column Section: Resume Upload & AI Spotlight */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        {/* Resume Scanner Card */}
        <div className="card" style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.05) 0%, var(--glass-bg) 100%)' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 700, borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.75rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span>📄</span> Resume Skill Scanner
          </h3>
          
          {uploading ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <div style={{ width: '32px', height: '32px', border: '3px solid var(--accent-indigo)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 1rem auto' }}></div>
              Scanning resume & detecting technical skill gaps...
            </div>
          ) : resume ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <strong style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Active Resume: </strong>
                <span style={{ color: 'white', fontWeight: 600 }}>{resume.filename}</span>
              </div>
              <div>
                <strong style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', display: 'block', marginBottom: '0.5rem' }}>Detected Technical Skills:</strong>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                  {resume.skills && resume.skills.length > 0 ? resume.skills.map((skill: string) => (
                    <span key={skill} style={{ fontSize: '0.75rem', background: 'rgba(99, 102, 241, 0.15)', color: '#c7d2fe', border: '1px solid rgba(99, 102, 241, 0.3)', padding: '0.2rem 0.6rem', borderRadius: '2rem', textTransform: 'capitalize' }}>{skill}</span>
                  )) : <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>No matches found.</span>}
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', fontSize: '0.85rem', marginTop: '0.5rem' }}>
                <div style={{ background: 'rgba(255,255,255,0.02)', padding: '0.75rem', borderRadius: '0.5rem', border: '1px solid var(--glass-border)' }}>
                  <strong style={{ color: 'var(--accent-indigo)', display: 'block', marginBottom: '0.25rem' }}>Inferred Level</strong>
                  <span style={{ fontSize: '1rem', fontWeight: 700, color: 'white' }}>{skillLevel}</span>
                </div>
                <div style={{ background: 'rgba(255,255,255,0.02)', padding: '0.75rem', borderRadius: '0.5rem', border: '1px solid var(--glass-border)' }}>
                  <strong style={{ color: 'var(--accent-error)', display: 'block', marginBottom: '0.25rem' }}>Identified Skill Gaps</strong>
                  <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fca5a5' }}>{weakTopics.join(', ')}</span>
                </div>
              </div>
              <label className="btn btn-primary" style={{ alignSelf: 'flex-start', marginTop: '0.5rem', cursor: 'pointer' }}>
                Upload New Resume
                <input type="file" accept=".txt,.pdf,.doc,.docx" onChange={handleResumeUpload} style={{ display: 'none' }} />
              </label>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '2rem', border: '2px dashed var(--glass-border)', borderRadius: '0.75rem', textAlign: 'center', gap: '1rem' }}>
              <div style={{ fontSize: '2.5rem' }}>📥</div>
              <div>
                <h4 style={{ fontWeight: 600, marginBottom: '0.25rem' }}>Align Prep with Your Resume</h4>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Upload your resume (PDF or TXT) to automatically identify skill gaps and customize questions.</p>
              </div>
              <label className="btn btn-primary" style={{ cursor: 'pointer' }}>
                Scan Resume
                <input type="file" accept=".txt,.pdf,.doc,.docx" onChange={handleResumeUpload} style={{ display: 'none' }} />
              </label>
            </div>
          )}
        </div>

        {/* AI Recommendation Spotlight */}
        {recommendation ? (
          <div className="card" style={{ borderLeft: '4px solid var(--accent-agent)', background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.1) 0%, var(--glass-bg) 100%)', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.75rem', padding: '0.3rem 0.75rem', borderRadius: '2rem', background: 'rgba(139, 92, 246, 0.2)', color: '#c4b5fd', border: '1px solid rgba(139, 92, 246, 0.3)', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>⚡ AI Target Challenge</span>
                <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', fontWeight: 500 }}>Target: {recommendation.category}</span>
              </div>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'white', marginTop: '1rem' }}>{recommendation.title} <span style={{ fontSize: '0.9rem', color: 'var(--accent-warning)', fontWeight: 600, marginLeft: '0.5rem' }}>{recommendation.difficulty}</span></h2>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', lineHeight: '1.6', marginTop: '0.5rem', marginBottom: '1rem' }}>{recommendation.reasoning}</p>
            </div>
            <a href={`/practice?id=${recommendation.id || '1'}`} className="btn btn-primary" style={{ alignSelf: 'flex-start', textDecoration: 'none', textAlign: 'center' }}>
              Initialize Challenge
            </a>
          </div>
        ) : (
          <div className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)' }}>
            No recommendations loaded.
          </div>
        )}
      </div>

      {/* Problem Directory */}
      <div className="card" style={{ padding: '2rem' }}>
        <h3 style={{ fontSize: '1.25rem', fontWeight: 700, borderBottom: '1px solid var(--glass-border)', paddingBottom: '1rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span>📚</span> Practice Catalog
        </h3>
        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
            <div style={{ width: '24px', height: '24px', border: '3px solid var(--accent-indigo)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 1rem auto' }}></div>
            Fetching challenges...
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {problems.map((prob) => (
              <div key={prob.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1.25rem', borderRadius: '0.75rem', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--glass-border)', transition: 'all 0.2s ease', cursor: 'pointer' }} onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'} onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <h4 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'white' }}>{prob.title}</h4>
                  <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{prob.category}</span>
                </div>
                <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
                  <span style={{
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    color: prob.difficulty === 'Easy' ? '#10b981' : (prob.difficulty === 'Medium' ? '#f59e0b' : '#ef4444'),
                    backgroundColor: prob.difficulty === 'Easy' ? 'rgba(16,185,129,0.1)' : (prob.difficulty === 'Medium' ? 'rgba(245,158,11,0.1)' : 'rgba(239,68,68,0.1)'),
                    padding: '0.3rem 0.75rem',
                    borderRadius: '2rem',
                    border: `1px solid ${prob.difficulty === 'Easy' ? 'rgba(16,185,129,0.2)' : (prob.difficulty === 'Medium' ? 'rgba(245,158,11,0.2)' : 'rgba(239,68,68,0.2)')}`
                  }}>{prob.difficulty}</span>
                  <a href={`/practice?id=${prob.id}`} className="btn btn-success" style={{ textDecoration: 'none', padding: '0.5rem 1rem' }}>
                    Solve
                  </a>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes spin { 100% { transform: rotate(360deg); } }
      `}} />
    </div>
  );
}
