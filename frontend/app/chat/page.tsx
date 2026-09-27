"use client";

import React, { useState, useEffect, useRef } from 'react';

interface ChatSessionObj {
  session_id: string;
  title: string;
  updated_at: string;
}

interface MessageObj {
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export default function ChatAssistant() {
  const [sessions, setSessions] = useState<ChatSessionObj[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageObj[]>([]);
  const [userInput, setUserInput] = useState('');
  const [selectedProvider, setSelectedProvider] = useState('groq');
  const [providers, setProviders] = useState<Record<string, boolean>>({});
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom on message updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load chat history & providers configuration
  useEffect(() => {
    async function loadInitialData() {
      try {
        const resProviders = await fetch('http://localhost:8000/api/v1/providers');
        if (resProviders.ok) {
          const status = await resProviders.json();
          setProviders(status);
          
          // Select first available configured key or default to openai
          const firstAvailable = Object.keys(status).find(k => status[k]);
          if (firstAvailable) {
            setSelectedProvider(firstAvailable);
          }
        }

        const resHist = await fetch('http://localhost:8000/api/v1/chat/history?user_id=anonymous');
        if (resHist.ok) {
          const list = await resHist.json();
          setSessions(list);
          if (list.length > 0) {
            await handleSelectSession(list[0].session_id);
          }
        }
      } catch (err) {
        console.warn("FastAPI backend is offline. Standalone mock assistant mode initiated.", err);
        setSessions([
          { session_id: "mock-chat-1", title: "Array Sorting Questions", updated_at: new Date().toISOString() },
          { session_id: "mock-chat-2", title: "React Component Optimization", updated_at: new Date().toISOString() }
        ]);
        setMessages([
          { role: 'user', content: "Hello! Can you explain Binary Search?", created_at: new Date().toISOString() },
          { role: 'assistant', content: "Binary Search is an O(log N) algorithm that works on sorted arrays. It continuously divides the search interval in half. Here is an implementation:\n\n```python\ndef binary_search(arr, target):\n    low, high = 0, len(arr) - 1\n    while low <= high:\n        mid = (low + high) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            low = mid + 1\n        else:\n            high = mid - 1\n    return -1\n```\n\nWhat other questions do you have?", created_at: new Date().toISOString() }
        ]);
        setActiveSessionId("mock-chat-1");
      } finally {
        setLoadingHistory(false);
      }
    }
    loadInitialData();
  }, []);

  const handleSelectSession = async (sessId: string) => {
    if (sessId.startsWith("mock")) {
      setActiveSessionId(sessId);
      return;
    }
    try {
      const res = await fetch(`http://localhost:8000/api/v1/chat/history/${sessId}`);
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages);
        setActiveSessionId(sessId);
      }
    } catch (err) {
      console.warn("Failed to fetch session messages", err);
    }
  };

  const handleCreateNewChat = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/v1/chat/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: 'anonymous', title: 'New Conversation' })
      });
      if (res.ok) {
        const data = await res.json();
        const newSession: ChatSessionObj = {
          session_id: data.session_id,
          title: data.title,
          updated_at: new Date().toISOString()
        };
        setSessions(prev => [newSession, ...prev]);
        setMessages([]);
        setActiveSessionId(data.session_id);
      }
    } catch (err) {
      const mockId = `mock-chat-${Date.now()}`;
      setSessions(prev => [{ session_id: mockId, title: 'New Conversation', updated_at: new Date().toISOString() }, ...prev]);
      setMessages([]);
      setActiveSessionId(mockId);
    }
  };

  const handleDeleteChat = async (e: React.MouseEvent, sessId: string) => {
    e.stopPropagation();
    try {
      const res = await fetch(`http://localhost:8000/api/v1/chat/history/${sessId}`, { method: 'DELETE' });
      if (res.ok) {
        setSessions(prev => prev.filter(s => s.session_id !== sessId));
        if (activeSessionId === sessId) {
          setMessages([]);
          setActiveSessionId(null);
        }
      }
    } catch (err) {
      setSessions(prev => prev.filter(s => s.session_id !== sessId));
      if (activeSessionId === sessId) {
        setMessages([]);
        setActiveSessionId(null);
      }
    }
  };

  const handleSendMessage = async () => {
    if (!userInput.trim() || !activeSessionId || sending) return;
    const currentInput = userInput;
    setUserInput('');
    setSending(true);

    // Save message locally
    const newUserMsg: MessageObj = {
      role: 'user',
      content: currentInput,
      created_at: new Date().toISOString()
    };
    setMessages(prev => [...prev, newUserMsg]);

    try {
      if (activeSessionId.startsWith('mock')) {
        setTimeout(() => {
          const botResponse: MessageObj = {
            role: 'assistant',
            content: "Sorry, I'm temporarily unavailable. Please try again in a moment.",
            created_at: new Date().toISOString()
          };
          setMessages(prev => [...prev, botResponse]);
          setSending(false);
        }, 800);
        return;
      }

      const res = await fetch('http://localhost:8000/api/v1/chat/message/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: activeSessionId,
          message: currentInput,
          provider: selectedProvider
        })
      });

      if (res.ok) {
        const botResponse: MessageObj = {
          role: 'assistant',
          content: '',
          created_at: new Date().toISOString()
        };
        setMessages(prev => [...prev, botResponse]);

        const reader = res.body?.getReader();
        const decoder = new TextDecoder("utf-8");
        let done = false;
        let accumulatedText = "";

        while (!done && reader) {
          const { value, done: readerDone } = await reader.read();
          done = readerDone;
          if (value) {
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split("\n");
            for (const line of lines) {
              if (line.startsWith("data: ")) {
                try {
                  const dataJson = JSON.parse(line.substring(6));
                  if (dataJson && dataJson.content) {
                    accumulatedText += dataJson.content;
                    setMessages(prev => {
                      const next = [...prev];
                      if (next.length > 0) {
                        next[next.length - 1] = {
                          ...next[next.length - 1],
                          content: accumulatedText
                        };
                      }
                      return next;
                    });
                  }
                } catch (e) {
                  // Ignore partial parsing errors
                }
              }
            }
          }
        }
        
        // Update session titles if it was the first message
        const resHist = await fetch('http://localhost:8000/api/v1/chat/history?user_id=anonymous');
        if (resHist.ok) {
          const list = await resHist.json();
          setSessions(list);
        }
      }
    } catch (err) {
      console.error("Failed to send message", err);
    } finally {
      setSending(false);
    }
  };

  // React parser that strips all markdown syntax characters and renders HTML elements with CSS styles
  const parseMarkdown = (text: string) => {
    // 1. Split by triple backticks for code blocks
    const parts = text.split(/(```[\s\S]*?```)/g);
    return parts.map((part, i) => {
      if (part.startsWith('```')) {
        const lines = part.split('\n');
        const language = lines[0].replace('```', '').trim() || 'code';
        const codeContent = lines.slice(1, -1).join('\n');
        return (
          <div key={i} className="code-block-container" style={{ margin: '1.2rem 0', borderRadius: '0.75rem', overflow: 'hidden', border: '1px solid var(--glass-border)', boxShadow: '0 4px 10px rgba(0,0,0,0.15)' }}>
            <div style={{ background: '#111827', padding: '0.5rem 1.25rem', fontSize: '0.8rem', color: '#9ca3af', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--glass-border)', textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>
              <span>{language}</span>
              <button 
                onClick={() => navigator.clipboard.writeText(codeContent)}
                style={{ background: 'transparent', border: 'none', color: '#6366f1', cursor: 'pointer', fontWeight: 600, fontSize: '0.8rem' }}
              >
                Copy Code
              </button>
            </div>
            <pre style={{ margin: 0, padding: '1.25rem', background: '#09090b', overflowX: 'auto', fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: '#f3f4f6', lineHeight: 1.6 }}>
              <code>{codeContent}</code>
            </pre>
          </div>
        );
      }

      // 2. Clean normal text lines: strip bold, italic, code markers, horizontal rules
      const cleanPart = part
        .replace(/\*\*/g, '')  // Strip bold markdown markers
        .replace(/\*/g, '')   // Strip italic markdown markers
        .replace(/`/g, '')    // Strip inline code backticks
        .replace(/---/g, ''); // Strip horizontal rules

      const lines = cleanPart.split('\n');
      return lines.map((line, j) => {
        // Strip # for headers but render using CSS size & weight
        if (line.startsWith('# ')) {
          return <h1 key={`${i}-${j}`} style={{ fontSize: '1.5rem', fontWeight: 800, margin: '1.25rem 0 0.75rem 0', color: 'white', lineHeight: 1.3 }}>{line.substring(2)}</h1>;
        }
        if (line.startsWith('## ')) {
          return <h2 key={`${i}-${j}`} style={{ fontSize: '1.3rem', fontWeight: 800, margin: '1.1rem 0 0.6rem 0', color: 'white', lineHeight: 1.3 }}>{line.substring(3)}</h2>;
        }
        if (line.startsWith('### ')) {
          return <h3 key={`${i}-${j}`} style={{ fontSize: '1.15rem', fontWeight: 700, margin: '0.9rem 0 0.5rem 0', color: 'white', lineHeight: 1.3 }}>{line.substring(4)}</h3>;
        }
        if (line.startsWith('#### ')) {
          return <h4 key={`${i}-${j}`} style={{ fontSize: '1.05rem', fontWeight: 700, margin: '0.75rem 0 0.4rem 0', color: 'white', lineHeight: 1.3 }}>{line.substring(5)}</h4>;
        }

        // Strip blockquote character but style with border & background
        if (line.startsWith('> ')) {
          return (
            <div key={`${i}-${j}`} style={{ borderLeft: '4px solid var(--accent-indigo)', padding: '0.5rem 1rem', margin: '0.75rem 0', background: 'rgba(255,255,255,0.02)', borderRadius: '0.375rem', color: '#d1d5db', fontStyle: 'italic' }}>
              {line.substring(2)}
            </div>
          );
        }

        // List items
        if (line.startsWith('- ') || line.startsWith('* ')) {
          return <li key={`${i}-${j}`} style={{ marginLeft: '1.5rem', listStyleType: 'disc', margin: '0.35rem 0', color: '#e4e4e7', lineHeight: 1.6 }}>{line.substring(2)}</li>;
        }

        // Numbered list items
        const numberedListMatch = line.match(/^(\d+)\.\s(.*)/);
        if (numberedListMatch) {
          return <li key={`${i}-${j}`} style={{ marginLeft: '1.5rem', listStyleType: 'decimal', margin: '0.35rem 0', color: '#e4e4e7', lineHeight: 1.6 }}>{numberedListMatch[2]}</li>;
        }
        
        if (line.trim() === '') return <div key={`${i}-${j}`} style={{ height: '0.6rem' }}></div>;
        
        return <p key={`${i}-${j}`} style={{ margin: '0.5rem 0', lineHeight: 1.6, color: '#e4e4e7' }}>{line}</p>;
      });
    });
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', height: 'calc(100vh - 70px)', background: 'var(--bg-primary)' }}>
      {/* Chats Sidebar */}
      <aside style={{ borderRight: '1px solid var(--glass-border)', display: 'flex', flexDirection: 'column', background: 'var(--bg-secondary)', padding: '1rem', gap: '1rem' }}>
        <button className="btn btn-primary" onClick={handleCreateNewChat} style={{ width: '100%' }}>
          💬 New Conversation
        </button>

        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {loadingHistory ? (
            <div style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '1rem' }}>Loading logs...</div>
          ) : sessions.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '1rem', fontSize: '0.85rem' }}>No conversations yet.</div>
          ) : (
            sessions.map(s => {
              const isActive = s.session_id === activeSessionId;
              return (
                <div 
                  key={s.session_id} 
                  onClick={() => handleSelectSession(s.session_id)}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '0.75rem 1rem',
                    borderRadius: '0.5rem',
                    cursor: 'pointer',
                    background: isActive ? 'rgba(99, 102, 241, 0.1)' : 'transparent',
                    border: `1px solid ${isActive ? 'rgba(99, 102, 241, 0.2)' : 'transparent'}`,
                    transition: 'all 0.2s',
                    color: isActive ? 'white' : 'var(--text-secondary)'
                  }}
                  onMouseEnter={e => !isActive && (e.currentTarget.style.background = 'rgba(255,255,255,0.03)')}
                  onMouseLeave={e => !isActive && (e.currentTarget.style.background = 'transparent')}
                >
                  <span style={{ fontSize: '0.9rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '170px' }}>{s.title}</span>
                  <button 
                    onClick={(e) => handleDeleteChat(e, s.session_id)}
                    style={{ background: 'transparent', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: '1rem' }}
                    onMouseEnter={e => e.currentTarget.style.color = '#ef4444'}
                    onMouseLeave={e => e.currentTarget.style.color = '#9ca3af'}
                  >
                    ×
                  </button>
                </div>
              );
            })
          )}
        </div>
      </aside>

      {/* Main Chat Workspace */}
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minWidth: 0 }}>
        {/* Model Engine Selector Header */}
        <header style={{ padding: '0.75rem 1.5rem', borderBottom: '1px solid var(--glass-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-secondary)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '1.2rem' }}>🤖</span>
            <span style={{ fontWeight: 600 }}>Conversational AI Assistant</span>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', background: 'rgba(255,255,255,0.05)', padding: '0.4rem 0.8rem', borderRadius: '0.5rem', border: '1px solid var(--glass-border)' }}>
            <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Provider:</label>
            <select
              value={selectedProvider}
              onChange={(e) => setSelectedProvider(e.target.value)}
              style={{ background: 'transparent', color: 'white', border: 'none', outline: 'none', fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer' }}
            >
              <option value="openai" style={{ background: 'var(--bg-secondary)', color: 'white' }}>OpenAI GPT-4o {providers.openai ? '✅' : '⚠️'}</option>
              <option value="gemini" style={{ background: 'var(--bg-secondary)', color: 'white' }}>Gemini 2.5 Flash {providers.gemini ? '✅' : '⚠️'}</option>
              <option value="anthropic" style={{ background: 'var(--bg-secondary)', color: 'white' }}>Anthropic Claude {providers.anthropic ? '✅' : '⚠️'}</option>
              <option value="groq" style={{ background: 'var(--bg-secondary)', color: 'white' }}>Groq Llama 3.3 {providers.groq ? '✅' : '⚠️'}</option>
              <option value="deepseek" style={{ background: 'var(--bg-secondary)', color: 'white' }}>DeepSeek Chat {providers.deepseek ? '✅' : '⚠️'}</option>
              <option value="openrouter" style={{ background: 'var(--bg-secondary)', color: 'white' }}>OpenRouter Llama {providers.openrouter ? '✅' : '⚠️'}</option>
              <option value="ollama" style={{ background: 'var(--bg-secondary)', color: 'white' }}>Ollama Local {providers.ollama ? '✅' : '⚠️'}</option>
            </select>
          </div>
        </header>

        {/* Message Feeds */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', background: 'var(--bg-primary)' }}>
          <div style={{ maxWidth: '800px', width: '100%', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {messages.length === 0 ? (
              <div style={{ height: '70vh', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center', gap: '1rem', color: 'var(--text-secondary)' }}>
                <span style={{ fontSize: '3.5rem' }}>💬</span>
                <h2 style={{ color: 'white', fontWeight: 800, fontSize: '1.8rem', background: 'linear-gradient(to right, #fff, #a1a1aa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>How can I help you prepare today?</h2>
                <p style={{ maxWidth: '500px', fontSize: '0.95rem', lineHeight: '1.6', color: 'var(--text-secondary)' }}>
                  Ask me to explain algorithms, debug your code, review your resume, run SQL queries, or practice system design.
                </p>
              </div>
            ) : (
              messages.map((m, index) => {
                const isAssistant = m.role === 'assistant';
                return (
                  <div 
                    key={index} 
                    style={{
                      display: 'flex',
                      justifyContent: isAssistant ? 'flex-start' : 'flex-end',
                      width: '100%',
                      margin: '0.5rem 0'
                    }}
                  >
                    <div 
                      style={{
                        background: isAssistant ? 'rgba(255, 255, 255, 0.03)' : 'linear-gradient(135deg, var(--accent-indigo) 0%, var(--accent-agent) 100%)',
                        border: isAssistant ? '1px solid var(--glass-border)' : '1px solid transparent',
                        borderRadius: '1rem',
                        padding: '1.25rem 1.5rem',
                        color: 'white',
                        maxWidth: '85%',
                        boxShadow: '0 4px 15px -3px rgba(0, 0, 0, 0.2)',
                        fontSize: '1rem',
                        lineHeight: '1.6',
                        wordBreak: 'break-word'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.6rem', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '0.4rem' }}>
                        <span style={{ fontSize: '1.1rem' }}>{isAssistant ? '🤖' : '👤'}</span>
                        <strong style={{ fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: isAssistant ? '#a78bfa' : '#cbd5e1' }}>
                          {isAssistant ? 'PrepAgent AI' : 'You'}
                        </strong>
                      </div>
                      <div style={{ fontSize: '0.98rem', color: '#e4e4e7' }}>
                        {isAssistant ? parseMarkdown(m.content) : <p style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{m.content}</p>}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
            {sending && (
              <div style={{ alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: '0.75rem', background: 'rgba(255,255,255,0.02)', padding: '0.8rem 1.4rem', borderRadius: '1rem', border: '1px solid var(--glass-border)' }}>
                <div style={{ width: '8px', height: '8px', background: '#6366f1', borderRadius: '50%', animation: 'pulse 1.2s infinite' }}></div>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>PrepAgent is formulating a response...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Dock */}
        <footer style={{ padding: '1.5rem 2.5rem', borderTop: '1px solid var(--glass-border)', background: 'var(--bg-secondary)' }}>
          <div style={{ maxWidth: '800px', width: '100%', margin: '0 auto', display: 'flex', gap: '0.75rem' }}>
            <textarea
              className="chat-input"
              rows={1}
              style={{ 
                flex: 1, 
                resize: 'none', 
                padding: '0.8rem 1.2rem', 
                height: '48px', 
                overflowY: 'hidden', 
                background: 'var(--bg-primary)', 
                border: '1px solid var(--glass-border)', 
                borderRadius: '0.75rem', 
                color: 'white',
                outline: 'none',
                fontSize: '0.95rem'
              }}
              placeholder="Ask anything (e.g. 'Explain dynamic programming', 'Review my resume', 'Analyze Two Sum space complexity')..."
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage();
                }
              }}
              disabled={!activeSessionId || sending}
            />
            <button 
              className="btn btn-primary" 
              onClick={handleSendMessage} 
              style={{ height: '48px', padding: '0 1.75rem', borderRadius: '0.75rem', fontWeight: 600 }}
              disabled={!activeSessionId || sending}
            >
              Ask
            </button>
          </div>
        </footer>
      </div>
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes pulse {
          0%, 100% { transform: scale(0.8); opacity: 0.5; }
          50% { transform: scale(1.2); opacity: 1; }
        }
      `}} />
    </div>
  );
}
