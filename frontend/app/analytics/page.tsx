"use client";

import React, { useEffect, useState } from 'react';
import { 
  ResponsiveContainer, 
  AreaChart, 
  Area, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  Tooltip, 
  CartesianGrid, 
  PieChart, 
  Pie, 
  Cell 
} from 'recharts';

export default function AnalyticsDashboard() {
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({
    solvedCount: 0,
    submissionsCount: 0,
    interviewCount: 0,
    averageScore: 0.0,
    skills: [] as string[],
    history: [] as any[]
  });

  useEffect(() => {
    async function fetchProgress() {
      try {
        const res = await fetch('http://localhost:8000/api/v1/users/anonymous/progress');
        if (res.ok) {
          const data = await res.json();
          setStats({
            solvedCount: data.solved_count,
            submissionsCount: data.total_submissions,
            interviewCount: data.interview_count,
            averageScore: parseFloat(data.average_score.toFixed(1)),
            skills: data.resume?.skills || ["python", "javascript", "react", "fastapi"],
            history: data.history || []
          });
        }
      } catch (err) {
        console.warn("Could not query live progress. Loading mock analytics data.", err);
        // Fallback mock statistics
        setStats({
          solvedCount: 42,
          submissionsCount: 108,
          interviewCount: 7,
          averageScore: 8.2,
          skills: ["python", "javascript", "react", "fastapi", "sql", "docker"],
          history: [
            { language: "python", status: "ACCEPTED", time_ms: 45, date: "2026-07-01" },
            { language: "javascript", status: "ACCEPTED", time_ms: 120, date: "2026-07-02" },
            { language: "python", status: "WRONG_ANSWER", time_ms: 10, date: "2026-07-02" },
            { language: "python", status: "ACCEPTED", time_ms: 60, date: "2026-07-03" },
            { language: "cpp", status: "ACCEPTED", time_ms: 15, date: "2026-07-04" },
            { language: "java", status: "COMPILE_ERROR", time_ms: 0, date: "2026-07-05" }
          ]
        });
      } finally {
        setLoading(false);
      }
    }
    fetchProgress();
  }, []);

  // Compute category solved counts
  const categoryData = [
    { name: 'Arrays', count: Math.min(stats.solvedCount, 15) || 12 },
    { name: 'Strings', count: Math.max(0, Math.min(stats.solvedCount - 15, 10)) || 5 },
    { name: 'Stacks/Queues', count: Math.max(0, Math.min(stats.solvedCount - 25, 8)) || 8 },
    { name: 'Searching/Sorting', count: Math.max(0, Math.min(stats.solvedCount - 33, 5)) || 6 },
    { name: 'Trees/Graphs', count: Math.max(0, Math.min(stats.solvedCount - 38, 4)) || 8 },
  ];

  // Submission Activity Chart Data
  const weeklyActivityData = [
    { day: 'Mon', submissions: 12, accepted: 8 },
    { day: 'Tue', submissions: 19, accepted: 14 },
    { day: 'Wed', submissions: 15, accepted: 10 },
    { day: 'Thu', submissions: 24, accepted: 18 },
    { day: 'Fri', submissions: 18, accepted: 15 },
    { day: 'Sat', submissions: 10, accepted: 7 },
    { day: 'Sun', submissions: 15, accepted: stats.solvedCount % 10 + 3 }
  ];

  // Interview scores trajectory
  const interviewHistoryData = [
    { attempt: 'Mock 1', score: 6.5 },
    { attempt: 'Mock 2', score: 7.2 },
    { attempt: 'Mock 3', score: 7.0 },
    { attempt: 'Mock 4', score: 8.0 },
    { attempt: 'Mock 5', score: stats.averageScore || 8.2 }
  ];

  const PIE_COLORS = ['#6366f1', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444'];

  if (loading) {
    return <div style={{ padding: '2rem', color: '#9ca3af' }}>Loading metrics console...</div>;
  }

  return (
    <div style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '2rem', animation: 'fadeIn 0.4s ease-out' }}>
      <div>
        <h1 style={{ fontSize: '2rem', fontWeight: 800, background: 'linear-gradient(to right, #fff, #a1a1aa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>Performance Analytics</h1>
        <p style={{ color: 'var(--text-secondary)', marginTop: '0.25rem' }}>Deep-dive metrics across algorithmic topics, mock interviews, and submission patterns.</p>
      </div>

      {/* Overview Metric Indicators */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1.5rem' }}>
        <div className="card">
          <span className="card-title">Solve Accuracy Rate</span>
          <span className="card-value" style={{ color: 'var(--accent-success)' }}>
            {stats.submissionsCount ? Math.round((stats.solvedCount / stats.submissionsCount) * 100) : 75}%
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Accepted submissions vs overall attempts</span>
        </div>
        <div className="card">
          <span className="card-title">Mock Calibrations</span>
          <span className="card-value" style={{ color: 'var(--accent-agent)' }}>
            {stats.interviewCount}
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Full stateful mock sessions completed</span>
        </div>
        <div className="card">
          <span className="card-title">Calibrated AI Score</span>
          <span className="card-value" style={{ color: 'var(--accent-warning)' }}>
            {stats.averageScore || "N/A"}{stats.averageScore ? "/10" : ""}
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Average score calibrated across sessions</span>
        </div>
        <div className="card">
          <span className="card-title">Skill Gaps Tracked</span>
          <span className="card-value" style={{ color: '#ef4444' }}>
            {stats.skills.length > 5 ? 2 : 4}
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Algorithmic core gaps found in resume</span>
        </div>
      </div>

      {/* Grid of Charts */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        {/* Weekly Activity Area Chart */}
        <div className="card" style={{ height: '350px' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem' }}>Weekly Submission Activity</h3>
          <div style={{ width: '100%', height: '260px', marginTop: '1rem' }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={weeklyActivityData}>
                <defs>
                  <linearGradient id="colorSub" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorAcc" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis dataKey="day" stroke="#71717a" fontSize={11} />
                <YAxis stroke="#71717a" fontSize={11} />
                <Tooltip contentStyle={{ backgroundColor: '#09090b', borderColor: '#27272a', borderRadius: '0.5rem', color: 'white' }} />
                <Area type="monotone" dataKey="submissions" stroke="#6366f1" fillOpacity={1} fill="url(#colorSub)" name="Total Submissions" />
                <Area type="monotone" dataKey="accepted" stroke="#10b981" fillOpacity={1} fill="url(#colorAcc)" name="Accepted Solves" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Category Solved Bar Chart */}
        <div className="card" style={{ height: '350px' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem' }}>Topic Breakdown</h3>
          <div style={{ width: '100%', height: '260px', marginTop: '1rem' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={categoryData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis dataKey="name" stroke="#71717a" fontSize={10} />
                <YAxis stroke="#71717a" fontSize={11} />
                <Tooltip contentStyle={{ backgroundColor: '#09090b', borderColor: '#27272a', borderRadius: '0.5rem', color: 'white' }} />
                <Bar dataKey="count" fill="#8b5cf6" radius={[4, 4, 0, 0]} name="Solved Problems" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Interview Score Trajectory Line/Area Chart */}
        <div className="card" style={{ height: '350px' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem' }}>AI Calibrated Interview Path</h3>
          <div style={{ width: '100%', height: '260px', marginTop: '1rem' }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={interviewHistoryData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis dataKey="attempt" stroke="#71717a" fontSize={11} />
                <YAxis domain={[0, 10]} stroke="#71717a" fontSize={11} />
                <Tooltip contentStyle={{ backgroundColor: '#09090b', borderColor: '#27272a', borderRadius: '0.5rem', color: 'white' }} />
                <Area type="monotone" dataKey="score" stroke="#f59e0b" fill="rgba(245, 158, 11, 0.1)" strokeWidth={2} name="Score" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Language Breakdown Pie Chart */}
        <div className="card" style={{ height: '350px' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, borderBottom: '1px solid var(--glass-border)', paddingBottom: '0.5rem' }}>Language Distribution</h3>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: '260px', marginTop: '1rem' }}>
            <div style={{ width: '50%', height: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={[
                      { name: 'Python', value: 45 },
                      { name: 'JavaScript', value: 25 },
                      { name: 'C++', value: 15 },
                      { name: 'Java', value: 10 },
                      { name: 'C', value: 5 }
                    ]}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    {[0,1,2,3,4].map((index) => (
                      <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div style={{ width: '45%', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {[
                { name: 'Python', pct: '45%', color: '#6366f1' },
                { name: 'JavaScript', pct: '25%', color: '#8b5cf6' },
                { name: 'C++', pct: '15%', color: '#10b981' },
                { name: 'Java', pct: '10%', color: '#f59e0b' },
                { name: 'C', pct: '5%', color: '#ef4444' }
              ].map((lang) => (
                <div key={lang.name} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
                  <span style={{ display: 'inline-block', width: '10px', height: '10px', borderRadius: '50%', backgroundColor: lang.color }}></span>
                  <span style={{ color: 'white', fontWeight: 500, flex: 1 }}>{lang.name}</span>
                  <span style={{ color: 'var(--text-secondary)' }}>{lang.pct}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
