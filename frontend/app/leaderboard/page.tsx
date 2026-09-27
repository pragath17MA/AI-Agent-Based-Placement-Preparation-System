"use client";

import React, { useState, useEffect } from 'react';

interface LeaderboardUser {
  rank: number;
  name: string;
  avatar: string;
  solved: number;
  avgScore: number;
  streak: number;
  language: string;
  status: string;
}

export default function Leaderboard() {
  const [candidates, setCandidates] = useState<LeaderboardUser[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedLanguage, setSelectedLanguage] = useState('All');
  const [loading, setLoading] = useState(true);
  const [userStreak, setUserStreak] = useState(0);

  // Fetch leaderboard data and user's stats
  useEffect(() => {
    async function loadLeaderboard() {
      try {
        const res = await fetch('http://localhost:8000/api/v1/leaderboard');
        if (res.ok) {
          const list = await res.json();
          setCandidates(list);
        }
        
        const resProgress = await fetch('http://localhost:8000/api/v1/users/anonymous/progress');
        if (resProgress.ok) {
          const data = await resProgress.json();
          // Find user's actual streak or default to 0
          if (data && typeof data.solved_count === 'number') {
            // Find "Anonymous (You)" in candidates to sync streak or set from progress
            setUserStreak(data.history?.length > 0 ? 3 : 0); // fallback visual streak indicator
          }
        }
      } catch (err) {
        console.warn("Backend offline. Fallback to mock rankings.", err);
        setCandidates([
          { rank: 1, name: "Arjun Mehta", avatar: "👨‍💻", solved: 184, avgScore: 9.4, streak: 45, language: "Python", status: "Available" },
          { rank: 2, name: "Sophia Chen", avatar: "👩‍💻", solved: 162, avgScore: 9.2, streak: 38, language: "C++", status: "Interviewing" },
          { rank: 3, name: "Pranav Rao", avatar: "👨‍💻", solved: 147, avgScore: 8.9, streak: 21, language: "Java", status: "Available" },
          { rank: 4, name: "Emily Watson", avatar: "👩‍💻", solved: 139, avgScore: 8.8, streak: 14, language: "JavaScript", status: "Available" },
          { rank: 5, name: "Anonymous (You)", avatar: "⚡", solved: 18, avgScore: 8.0, streak: 3, language: "Python", status: "Preparing" },
          { rank: 6, name: "Kabir Dev", avatar: "👨‍💻", solved: 118, avgScore: 8.5, streak: 12, language: "Python", status: "Placed" },
          { rank: 7, name: "Li Wei", avatar: "👩‍💻", solved: 104, avgScore: 8.3, streak: 0, language: "C++", status: "Interviewing" },
          { rank: 8, name: "Sarah Connor", avatar: "👩‍💻", solved: 95, avgScore: 8.1, streak: 8, language: "JavaScript", status: "Available" }
        ]);
        setUserStreak(3);
      } finally {
        setLoading(false);
      }
    }
    loadLeaderboard();
  }, []);

  // Filtering candidates
  const filteredCandidates = candidates.filter(user => {
    const matchesSearch = user.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesLang = selectedLanguage === 'All' || user.language === selectedLanguage;
    return matchesSearch && matchesLang;
  });

  return (
    <div style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '2rem', animation: 'fadeIn 0.4s ease-out' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '2rem', fontWeight: 800, background: 'linear-gradient(to right, #fff, #a1a1aa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>Leaderboard</h1>
          <p style={{ color: 'var(--text-secondary)', marginTop: '0.25rem' }}>Global placement readiness rankings based on verified scores & streak consistency.</p>
        </div>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <div style={{ background: 'rgba(255,255,255,0.03)', padding: '0.5rem 1rem', borderRadius: '0.5rem', border: '1px solid var(--glass-border)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ color: 'var(--accent-warning)', fontSize: '1.25rem' }}>🔥</span>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Your Streak</div>
              <div style={{ fontSize: '0.9rem', fontWeight: 700, color: 'white' }}>{userStreak} Days</div>
            </div>
          </div>
        </div>
      </div>

      {/* Filter and search control bar */}
      <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
        <input 
          type="text" 
          placeholder="Search candidates..." 
          style={{
            flex: 1,
            minWidth: '200px',
            background: 'var(--bg-secondary)',
            border: '1px solid var(--glass-border)',
            padding: '0.75rem 1rem',
            borderRadius: '0.5rem',
            color: 'white',
            outline: 'none',
            fontSize: '0.9rem'
          }}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
        <select
          style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--glass-border)',
            padding: '0.75rem 1rem',
            borderRadius: '0.5rem',
            color: 'white',
            outline: 'none',
            fontSize: '0.9rem',
            cursor: 'pointer',
            minWidth: '150px'
          }}
          value={selectedLanguage}
          onChange={(e) => setSelectedLanguage(e.target.value)}
        >
          <option value="All">All Languages</option>
          <option value="Python">Python</option>
          <option value="C++">C++</option>
          <option value="Java">Java</option>
          <option value="JavaScript">JavaScript</option>
        </select>
      </div>

      {/* Rank list table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)' }}>Loading leaderboard statistics...</div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--glass-border)', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                  <th style={{ padding: '1rem 1.5rem' }}>Rank</th>
                  <th style={{ padding: '1rem 1.5rem' }}>Candidate</th>
                  <th style={{ padding: '1rem 1.5rem' }}>Problems Solved</th>
                  <th style={{ padding: '1rem 1.5rem' }}>Avg Calibrated Score</th>
                  <th style={{ padding: '1rem 1.5rem' }}>Daily Streak</th>
                  <th style={{ padding: '1rem 1.5rem' }}>Primary Language</th>
                  <th style={{ padding: '1rem 1.5rem' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredCandidates.map((user) => {
                  const isCurrentUser = user.name.includes("(You)");
                  return (
                    <tr 
                      key={user.rank} 
                      style={{ 
                        borderBottom: '1px solid rgba(255,255,255,0.03)',
                        background: isCurrentUser ? 'rgba(99, 102, 241, 0.05)' : 'transparent',
                        transition: 'background 0.2s',
                        fontSize: '0.9rem'
                      }}
                    >
                      <td style={{ padding: '1.2rem 1.5rem', fontWeight: 700, color: user.rank <= 3 ? 'var(--accent-warning)' : 'var(--text-secondary)' }}>
                        {user.rank === 1 ? '🥇' : user.rank === 2 ? '🥈' : user.rank === 3 ? '🥉' : `#${user.rank}`}
                      </td>
                      <td style={{ padding: '1.2rem 1.5rem', fontWeight: 600, color: 'white', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <span style={{ fontSize: '1.25rem' }}>{user.avatar}</span>
                        <div>
                          {user.name}
                          {isCurrentUser && <span style={{ fontSize: '0.7rem', background: 'var(--accent-indigo)', color: 'white', padding: '0.1rem 0.4rem', borderRadius: '0.25rem', marginLeft: '0.5rem', fontWeight: 700 }}>YOU</span>}
                        </div>
                      </td>
                      <td style={{ padding: '1.2rem 1.5rem', color: 'white' }}>
                        <span style={{ fontWeight: 600 }}>{user.solved}</span>
                        <span style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>/200</span>
                      </td>
                      <td style={{ padding: '1.2rem 1.5rem', color: 'var(--accent-indigo)', fontWeight: 700 }}>
                        {user.avgScore}/10
                      </td>
                      <td style={{ padding: '1.2rem 1.5rem', color: 'white' }}>
                        {user.streak > 0 ? (
                          <span style={{ color: 'var(--accent-warning)', fontWeight: 600 }}>🔥 {user.streak} days</span>
                        ) : (
                          <span style={{ color: 'var(--text-secondary)' }}>-</span>
                        )}
                      </td>
                      <td style={{ padding: '1.2rem 1.5rem', color: 'var(--text-secondary)' }}>{user.language}</td>
                      <td style={{ padding: '1.2rem 1.5rem' }}>
                        <span 
                          style={{ 
                            fontSize: '0.75rem', 
                            padding: '0.25rem 0.6rem', 
                            borderRadius: '1rem', 
                            fontWeight: 600,
                            background: user.status === "Placed" || user.status === "Available" ? 'rgba(16, 185, 129, 0.1)' : user.status === "Interviewing" ? 'rgba(245, 158, 11, 0.1)' : 'rgba(255,255,255,0.05)',
                            color: user.status === "Placed" || user.status === "Available" ? 'var(--accent-success)' : user.status === "Interviewing" ? 'var(--accent-warning)' : 'var(--text-secondary)',
                            border: `1px solid ${user.status === "Placed" || user.status === "Available" ? 'rgba(16, 185, 129, 0.2)' : user.status === "Interviewing" ? 'rgba(245, 158, 11, 0.2)' : 'rgba(255,255,255,0.08)'}`
                          }}
                        >
                          {user.status}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
