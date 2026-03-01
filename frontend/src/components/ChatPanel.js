import { useState, useRef, useEffect } from 'react';
import { apiPost } from '../api';

export default function ChatPanel() {
  const [messages, setMessages] = useState([
    { text: "Hello! I'm your AI financial assistant. Ask me anything about your spending and income.", sender: 'ai' },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { text, sender: 'user' }]);
    setInput('');
    setLoading(true);

    try {
      const data = await apiPost('/chat', { message: text });
      setMessages((prev) => [...prev, { text: data.reply, sender: 'ai' }]);
    } catch {
      setMessages((prev) => [...prev, { text: 'Sorry, could not connect to the server.', sender: 'ai' }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') sendMessage();
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        AI Assistant <span className="ai-badge">AI</span>
      </div>
      <div className="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.sender}`}>{m.text}</div>
        ))}
        {loading && <div className="message typing">AI is thinking...</div>}
        <div ref={messagesEndRef} />
      </div>
      <div className="chat-input-area">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your finances..."
          autoComplete="off"
        />
        <button onClick={sendMessage}>Send</button>
      </div>
    </div>
  );
}
