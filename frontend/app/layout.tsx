"use client";

import React, { useState, useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import './globals.css';

interface FloatingMessage {
  role: 'user' | 'assistant';
  content: string;
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [aiCore, setAiCore] = useState('groq');

  // Floating Chatbot States
  const [isWidgetOpen, setIsWidgetOpen] = useState(false);
  const [widgetSessionId, setWidgetSessionId] = useState<string | null>(null);
  const [widgetMessages, setWidgetMessages] = useState<FloatingMessage[]>([]);
  const [widgetInput, setWidgetInput] = useState('');
  const [widgetLoading, setWidgetLoading] = useState(false);
  const widgetMessagesEndRef = useRef<HTMLDivElement>(null);

  // Load preferred AI model on mount
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const savedCore = localStorage.getItem('selected_ai_core');
      if (savedCore) {
        setAiCore(savedCore);
      }
    }
  }, []);

  // Initialize Floating Widget Chat Session
  useEffect(() => {
    async function initFloatingSession() {
      if (typeof window !== 'undefined') {
        const savedSession = localStorage.getItem('floating_widget_session_id');
        if (savedSession) {
          setWidgetSessionId(savedSession);
          try {
            const res = await fetch(`http://localhost:8000/api/v1/chat/history/${savedSession}`);
            if (res.ok) {
              const data = await res.json();
              setWidgetMessages(data.messages || []);
            }
          } catch (e) {
            console.warn("Offline fallback for floating widget history query.");
          }
        } else {
          try {
            const res = await fetch('http://localhost:8000/api/v1/chat/start', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ user_id: 'anonymous', title: 'Global Doubts Chat' })
            });
            if (res.ok) {
              const data = await res.json();
              setWidgetSessionId(data.session_id);
              localStorage.setItem('floating_widget_session_id', data.session_id);
            }
          } catch (e) {
            setWidgetSessionId('mock-widget-session');
          }
        }
      }
    }
    initFloatingSession();
  }, []);

  // Auto-scroll floating widget
  useEffect(() => {
    widgetMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [widgetMessages, widgetLoading]);

  // Save preferred AI model on change
  const handleAiCoreChange = (val: string) => {
    setAiCore(val);
    if (typeof window !== 'undefined') {
      localStorage.setItem('selected_ai_core', val);
    }
  };

  const handleSendWidgetMessage = async () => {
    if (!widgetInput.trim() || widgetLoading || !widgetSessionId) return;
    const currentInput = widgetInput;
    setWidgetInput('');
    setWidgetLoading(true);

    const newUserMsg: FloatingMessage = { role: 'user', content: currentInput };
    setWidgetMessages(prev => [...prev, newUserMsg]);

    try {
      if (widgetSessionId.startsWith('mock')) {
        setTimeout(() => {
          setWidgetMessages(prev => [...prev, {
            role: 'assistant',
            content: "Sorry, I'm temporarily unavailable. Please try again in a moment."
          }]);
          setWidgetLoading(false);
        }, 800);
        return;
      }

      const res = await fetch('http://localhost:8000/api/v1/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: widgetSessionId,
          message: currentInput,
          provider: aiCore
        })
      });

      if (res.ok) {
        const data = await res.json();
        setWidgetMessages(prev => [...prev, { role: 'assistant', content: data.content }]);
      }
    } catch (err) {
      console.error("Widget message failed to send", err);
    } finally {
      setWidgetLoading(false);
    }
  };

  // Pure React simplified markdown renderer for widget
  const parseWidgetMarkdown = (text: string) => {
    const parts = text.split(/(```[\s\S]*?```)/g);
    return parts.map((part, i) => {
      if (part.startsWith('```')) {
        const lines = part.split('\n');
        const codeContent = lines.slice(1, -1).join('\n');
        return (
          <pre key={i} style={{ margin: '0.5rem 0', padding: '0.5rem', background: '#09090b', borderRadius: '0.25rem', overflowX: 'auto', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: '#a78bfa', border: '1px solid var(--glass-border)', lineHeight: 1.4 }}>
            <code>{codeContent}</code>
          </pre>
        );
      }
      return <span key={i} style={{ whiteSpace: 'pre-wrap' }}>{part}</span>;
    });
  };

  const menuItems = [
    { name: 'Dashboard', path: '/', icon: '📊' },
    { name: 'Practice Arena', path: '/practice', icon: '💻' },
    { name: 'Mock Interview', path: '/interview', icon: '🤖' },
    { name: 'AI Assistant', path: '/chat', icon: '💬' },
    { name: 'Analytics', path: '/analytics', icon: '📈' },
    { name: 'Leaderboard', path: '/leaderboard', icon: '🏆' },
    { name: 'Settings', path: '/settings', icon: '⚙️' },
  ];

  return (
    <html lang="en">
      <head>
        <title>Placement Preparation Agent IDE</title>
        <meta name="description" content="AI-Powered Coding and Stateful Mock Interview Arena" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet" />
      </head>
      <body>
        <div className="app-container">
          <aside className="sidebar">
            <div className="sidebar-title">
              <span style={{ background: 'linear-gradient(135deg, var(--accent-indigo), var(--accent-agent))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', fontSize: '1.75rem', marginRight: '0.25rem' }}>⚡</span>
              PrepAgent
            </div>
            <ul className="sidebar-menu" style={{ marginTop: '1rem' }}>
              {menuItems.map((item) => {
                const isActive = pathname === item.path;
                return (
                  <li key={item.path}>
                    <a href={item.path} className={`menu-item ${isActive ? 'active' : ''}`}>
                      <span style={{ fontSize: '1.25rem' }}>{item.icon}</span> {item.name}
                    </a>
                  </li>
                );
              })}
            </ul>
            <div style={{ marginTop: 'auto', fontSize: '0.75rem', color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.03)', padding: '0.75rem', borderRadius: '0.5rem', border: '1px solid var(--glass-border)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                <span style={{ display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent-success)', boxShadow: '0 0 5px var(--accent-success)' }}></span>
                <span style={{ fontWeight: 600, color: 'white' }}>System Online</span>
              </div>
              v1.1.0 Premium Core
            </div>
          </aside>
          <div className="main-content" style={{ position: 'relative' }}>
            <header className="header">
              <div className="header-status">
                <div className="status-indicator">
                  <span className="indicator-dot"></span>
                  Local Database Connected
                </div>
              </div>
              <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'rgba(255,255,255,0.05)', padding: '0.4rem 0.8rem', borderRadius: '0.5rem', border: '1px solid var(--glass-border)' }}>
                  <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 500 }}>AI Core:</label>
                  <select 
                    style={{
                      background: 'transparent', 
                      color: 'white', 
                      border: 'none',
                      outline: 'none',
                      fontSize: '0.85rem',
                      fontWeight: 600,
                      cursor: 'pointer'
                    }}
                    value={aiCore}
                    onChange={(e) => handleAiCoreChange(e.target.value)}
                  >
                    <option value="openai" style={{ background: 'var(--bg-secondary)', color: 'white' }}>GPT-4o</option>
                    <option value="gemini" style={{ background: 'var(--bg-secondary)', color: 'white' }}>Gemini 1.5 Flash</option>
                    <option value="anthropic" style={{ background: 'var(--bg-secondary)', color: 'white' }}>Claude 3.5 Sonnet</option>
                    <option value="groq" style={{ background: 'var(--bg-secondary)', color: 'white' }}>Groq Llama 3.3</option>
                    <option value="deepseek" style={{ background: 'var(--bg-secondary)', color: 'white' }}>DeepSeek Chat</option>
                    <option value="openrouter" style={{ background: 'var(--bg-secondary)', color: 'white' }}>OpenRouter Llama</option>
                    <option value="ollama" style={{ background: 'var(--bg-secondary)', color: 'white' }}>Ollama Local</option>
                  </select>
                </div>
              </div>
            </header>
            <main style={{ flex: 1 }}>
              {children}
            </main>

            {/* Global Floating AI Chatbot Button */}
            <div style={{ position: 'fixed', bottom: '2rem', right: '2rem', zIndex: 1000, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '1rem' }}>
              {/* Slide-out Chat Window */}
              {isWidgetOpen && (
                <div style={{
                  width: '380px',
                  height: '480px',
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--glass-border)',
                  borderRadius: '1rem',
                  display: 'flex',
                  flexDirection: 'column',
                  boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.4), 0 10px 10px -5px rgba(0, 0, 0, 0.4)',
                  overflow: 'hidden',
                  animation: 'slideUp 0.3s ease-out'
                }}>
                  {/* Header widget */}
                  <div style={{ background: 'linear-gradient(135deg, var(--accent-indigo) 0%, var(--accent-agent) 100%)', padding: '0.85rem 1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'white' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{ fontSize: '1.2rem' }}>⚡</span>
                      <strong style={{ fontSize: '0.9rem', fontWeight: 700 }}>PrepAgent Doubt Solver</strong>
                    </div>
                    <button 
                      onClick={() => setIsWidgetOpen(false)}
                      style={{ background: 'transparent', border: 'none', color: 'white', fontSize: '1.2rem', cursor: 'pointer', opacity: 0.8 }}
                      onMouseEnter={e => e.currentTarget.style.opacity = '1'}
                      onMouseLeave={e => e.currentTarget.style.opacity = '0.8'}
                    >
                      ×
                    </button>
                  </div>

                  {/* Message feed widget */}
                  <div style={{ flex: 1, overflowY: 'auto', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem', background: '#0c0c0e' }}>
                    {widgetMessages.length === 0 ? (
                      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', color: 'var(--text-secondary)', textAlign: 'center', padding: '1rem', fontSize: '0.8rem', gap: '0.5rem' }}>
                        <span>💡</span>
                        <p>Ask quick doubt clarifications, algorithm lookups, or system design layouts while reading placement material!</p>
                      </div>
                    ) : (
                      widgetMessages.map((m, idx) => {
                        const isAssistant = m.role === 'assistant';
                        return (
                          <div 
                            key={idx} 
                            style={{
                              alignSelf: isAssistant ? 'flex-start' : 'flex-end',
                              maxWidth: '85%',
                              background: isAssistant ? 'rgba(255,255,255,0.03)' : 'var(--accent-indigo)',
                              border: isAssistant ? '1px solid var(--glass-border)' : '1px solid transparent',
                              padding: '0.65rem 0.85rem',
                              borderRadius: isAssistant ? '0.75rem 0.75rem 0.75rem 0' : '0.75rem 0.75rem 0 0.75rem',
                              fontSize: '0.82rem',
                              color: 'white',
                              boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                            }}
                          >
                            {isAssistant ? parseWidgetMarkdown(m.content) : <span>{m.content}</span>}
                          </div>
                        );
                      })
                    )}
                    {widgetLoading && (
                      <div style={{ alignSelf: 'flex-start', background: 'rgba(255,255,255,0.02)', padding: '0.5rem 0.75rem', borderRadius: '0.75rem', border: '1px solid var(--glass-border)', fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <div style={{ width: '4px', height: '4px', background: '#6366f1', borderRadius: '50%', animation: 'pulse 1.2s infinite' }}></div>
                        <span>Formulating steps...</span>
                      </div>
                    )}
                    <div ref={widgetMessagesEndRef} />
                  </div>

                  {/* Input widget */}
                  <div style={{ padding: '0.75rem', borderTop: '1px solid var(--glass-border)', background: 'var(--bg-secondary)', display: 'flex', gap: '0.5rem' }}>
                    <input
                      type="text"
                      className="chat-input"
                      placeholder="Solve a programming doubt..."
                      value={widgetInput}
                      onChange={(e) => setWidgetInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSendWidgetMessage()}
                      style={{ padding: '0.5rem 0.75rem', fontSize: '0.82rem', height: '35px' }}
                      disabled={widgetLoading}
                    />
                    <button 
                      className="btn btn-primary" 
                      onClick={handleSendWidgetMessage}
                      style={{ fontSize: '0.8rem', height: '35px', padding: '0 0.75rem' }}
                      disabled={widgetLoading}
                    >
                      Ask
                    </button>
                  </div>
                </div>
              )}

              {/* Floating Action Button */}
              <button 
                onClick={() => setIsWidgetOpen(!isWidgetOpen)}
                style={{
                  width: '60px',
                  height: '60px',
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, var(--accent-indigo) 0%, var(--accent-agent) 100%)',
                  border: 'none',
                  boxShadow: '0 10px 15px -3px rgba(139, 92, 246, 0.4), 0 4px 6px -2px rgba(139, 92, 246, 0.4)',
                  cursor: 'pointer',
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'center',
                  fontSize: '1.5rem',
                  color: 'white',
                  transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)'
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.transform = 'scale(1.1) rotate(15deg)';
                  e.currentTarget.style.boxShadow = '0 15px 20px -3px rgba(139, 92, 246, 0.6)';
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.transform = 'scale(1) rotate(0deg)';
                  e.currentTarget.style.boxShadow = '0 10px 15px -3px rgba(139, 92, 246, 0.4)';
                }}
              >
                {isWidgetOpen ? '×' : '💬'}
              </button>
            </div>
          </div>
        </div>
        <style dangerouslySetInnerHTML={{__html: `
          @keyframes slideUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
          }
          @keyframes pulse {
            0%, 100% { opacity: 0.5; }
            50% { opacity: 1; }
          }
        `}} />
      </body>
    </html>
  );
}
