import { useEffect, useMemo, useRef, useState } from 'react';
import { sendChatMessage } from '../services/chatClient';

const STORAGE_OPEN = 'mm_chat_widget_open';
const STORAGE_MESSAGES = 'mm_chat_widget_messages';
const STORAGE_UNREAD = 'mm_chat_widget_unread';

const SUGGESTION_PROMPTS = [
  'How much did I spend this month?',
  'Am I over budget?',
  "What's my biggest expense?",
  'How long will my money last?',
];

function createMessage(role, content) {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    createdAt: new Date().toISOString(),
  };
}

function readBool(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return fallback;
    return raw === 'true';
  } catch {
    return fallback;
  }
}

function readMessages() {
  try {
    const raw = localStorage.getItem(STORAGE_MESSAGES);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((item) => ({
        id: String(item?.id || ''),
        role: item?.role === 'assistant' ? 'assistant' : 'user',
        content: String(item?.content || ''),
        createdAt: String(item?.createdAt || ''),
      }))
      .filter((item) => item.id && item.content && (item.role === 'assistant' || item.role === 'user'));
  } catch {
    return [];
  }
}

function writeStorage(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Ignore persistence errors (private mode, quota, etc).
  }
}

function formatTime(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function ChatToggleButton({ unread, onOpen }) {
  return (
    <button
      type="button"
      className="chat-widget-toggle"
      onClick={onOpen}
      aria-label="Open AI assistant chat"
    >
      <svg viewBox="0 0 24 24" className="chat-widget-toggle-icon" aria-hidden="true">
        <path
          d="M12 3C7.03 3 3 6.58 3 11c0 2.16.97 4.12 2.55 5.56L5 21l4.06-2.07c.92.24 1.9.37 2.94.37 4.97 0 9-3.58 9-8s-4.03-8.3-9-8.3Z"
          fill="currentColor"
        />
      </svg>
      {unread && <span className="chat-widget-unread-dot" aria-hidden="true" />}
      <span className="chat-widget-tooltip">AI Assistant</span>
    </button>
  );
}

function TypingIndicator() {
  return (
    <div className="chat-widget-message chat-widget-message--assistant chat-widget-message--typing" aria-label="Assistant is typing">
      <span className="chat-widget-typing-dot" />
      <span className="chat-widget-typing-dot" />
      <span className="chat-widget-typing-dot" />
    </div>
  );
}

export default function ChatWidget() {
  const [isOpen, setIsOpen] = useState(() => readBool(STORAGE_OPEN, false));
  const [messages, setMessages] = useState(() => readMessages());
  const [unread, setUnread] = useState(() => readBool(STORAGE_UNREAD, false));
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isMobile, setIsMobile] = useState(() => (typeof window !== 'undefined' ? window.innerWidth <= 768 : false));

  const panelRef = useRef(null);
  const inputRef = useRef(null);
  const messagesEndRef = useRef(null);
  const openRef = useRef(isOpen);

  const canSend = useMemo(() => input.trim().length > 0 && !isTyping, [input, isTyping]);

  useEffect(() => {
    openRef.current = isOpen;
  }, [isOpen]);

  useEffect(() => {
    writeStorage(STORAGE_OPEN, isOpen ? 'true' : 'false');
  }, [isOpen]);

  useEffect(() => {
    writeStorage(STORAGE_MESSAGES, JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    writeStorage(STORAGE_UNREAD, unread ? 'true' : 'false');
  }, [unread]);

  useEffect(() => {
    if (isOpen) {
      setUnread(false);
      setTimeout(() => {
        inputRef.current?.focus();
      }, 120);
    }
  }, [isOpen]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    if (!isOpen) return;
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !isMobile) return;

    const onTrapFocus = (event) => {
      if (event.key !== 'Tab') return;
      const panel = panelRef.current;
      if (!panel) return;

      const focusable = Array.from(
        panel.querySelectorAll('button, textarea, input, [href], [tabindex]:not([tabindex="-1"])'),
      ).filter((node) => !node.hasAttribute('disabled'));

      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;

      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onTrapFocus);
    return () => document.removeEventListener('keydown', onTrapFocus);
  }, [isMobile, isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [isOpen, isTyping, messages]);

  const appendAssistantMessage = (content) => {
    const assistantMessage = createMessage('assistant', content);
    setMessages((prev) => [...prev, assistantMessage]);
    if (!openRef.current) {
      setUnread(true);
    }
  };

  const handleSend = async (sourceText) => {
    const text = String(sourceText ?? input).trim();
    if (!text || isTyping) return;

    const userMessage = createMessage('user', text);
    const nextHistory = [...messages, userMessage];

    setMessages((prev) => [...prev, userMessage]);
    if (sourceText == null) {
      setInput('');
    }
    setIsTyping(true);

    try {
      const reply = await sendChatMessage({ message: text, history: nextHistory });
      appendAssistantMessage(reply);
    } catch {
      appendAssistantMessage('Something went wrong. Try again.');
    } finally {
      setIsTyping(false);
    }
  };

  const onInputKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      {isOpen && isMobile && (
        <button
          type="button"
          className="chat-widget-backdrop"
          onClick={() => setIsOpen(false)}
          aria-label="Close chat"
        />
      )}

      <div className="chat-widget-root">
        <div
          className={`chat-widget-panel ${isOpen ? 'is-open' : 'is-closed'} ${isMobile ? 'is-mobile' : ''}`}
          role="dialog"
          aria-modal={isMobile ? 'true' : 'false'}
          aria-labelledby="chat-widget-title"
          ref={panelRef}
        >
          <div className="chat-widget-header">
            <div className="chat-widget-header-info">
              <div className="chat-widget-avatar">AI</div>
              <div>
                <h3 id="chat-widget-title">AI Financial Assistant</h3>
                <p>Ask about your spending and budget</p>
              </div>
            </div>
            <div className="chat-widget-header-actions">
              <button
                type="button"
                className="chat-widget-icon-btn"
                onClick={() => setIsOpen(false)}
                aria-label="Minimize chat"
              >
                &#8211;
              </button>
              <button
                type="button"
                className="chat-widget-icon-btn"
                onClick={() => setIsOpen(false)}
                aria-label="Close chat"
              >
                &#10005;
              </button>
            </div>
          </div>

          <div className="chat-widget-body">
            {messages.length === 0 && (
              <div className="chat-widget-welcome">
                <div className="chat-widget-message chat-widget-message--assistant">
                  Hi! I'm your AI financial assistant. Ask me anything about your spending, budget, or runway.
                </div>
                <div className="chat-widget-suggestions">
                  {SUGGESTION_PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      className="chat-widget-suggestion-chip"
                      onClick={() => handleSend(prompt)}
                      disabled={isTyping}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="chat-widget-messages">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`chat-widget-message ${message.role === 'assistant' ? 'chat-widget-message--assistant' : 'chat-widget-message--user'}`}
                >
                  <p>{message.content}</p>
                  <span className="chat-widget-message-time">{formatTime(message.createdAt)}</span>
                </div>
              ))}
              {isTyping && <TypingIndicator />}
              <div ref={messagesEndRef} />
            </div>
          </div>

          <div className="chat-widget-footer">
            <textarea
              ref={inputRef}
              className="chat-widget-input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={onInputKeyDown}
              placeholder="Ask about your finances..."
              rows={2}
              aria-label="Chat message input"
            />
            <button
              type="button"
              className="chat-widget-send-btn"
              onClick={() => handleSend()}
              disabled={!canSend}
              aria-label="Send message"
            >
              Send
            </button>
          </div>
        </div>

        {!isOpen && <ChatToggleButton unread={unread} onOpen={() => setIsOpen(true)} />}
      </div>
    </>
  );
}
