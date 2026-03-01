import { useMemo, useRef, useState } from 'react';
import { sendGoalsChatMessage } from '../services/goalsChatClient';

const SUGGESTION_PROMPTS = [
  'Create a trip goal for me',
  'How much should I save monthly for my tuition goal?',
  'Add $100 to my emergency fund',
  'Can I move my deadline by 2 months?',
];

function createMessage(role, content, actions = []) {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    actions,
    createdAt: new Date().toISOString(),
  };
}

function formatTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

export default function GoalsChatPanel() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const listEndRef = useRef(null);

  const canSend = useMemo(() => input.trim().length > 0 && !isLoading, [input, isLoading]);

  const appendAssistantMessage = (content, actions = []) => {
    setMessages((prev) => [...prev, createMessage('assistant', content, actions)]);
    setTimeout(() => listEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 30);
  };

  const handleSend = async (sourceText) => {
    const text = String(sourceText ?? input).trim();
    if (!text || isLoading) return;

    setMessages((prev) => [...prev, createMessage('user', text)]);
    if (sourceText == null) setInput('');
    setIsLoading(true);

    try {
      const result = await sendGoalsChatMessage({
        message: text,
        pendingAction,
      });
      setPendingAction(result.pendingAction || null);
      appendAssistantMessage(result.reply, result.actions);
    } catch {
      appendAssistantMessage('Something went wrong. Try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirm = () => {
    if (!pendingAction || isLoading) return;
    handleSend('yes');
  };

  const handleCancel = () => {
    if (!pendingAction || isLoading) return;
    setPendingAction(null);
    setMessages((prev) => [...prev, createMessage('assistant', 'Okay, no changes were applied.')]);
  };

  return (
    <section className="card goals-chat-panel">
      <div className="card-title-row">
        <h2 className="card-title">Goals Assistant</h2>
      </div>

      <div className="goals-chat-description">
        Ask for goal planning suggestions or updates to target/saved/deadline.
      </div>

      <div className="goals-chat-messages">
        {messages.length === 0 && (
          <div className="goals-chat-welcome">
            <div className="goals-chat-message goals-chat-message--assistant">
              Hi! I can help you plan and manage your goals. Ask me to create or adjust a goal.
            </div>
            <div className="goals-chat-suggestions">
              {SUGGESTION_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  className="goals-chat-suggestion-chip"
                  onClick={() => handleSend(prompt)}
                  disabled={isLoading}
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={`goals-chat-message ${message.role === 'assistant' ? 'goals-chat-message--assistant' : 'goals-chat-message--user'}`}
          >
            <p>{message.content}</p>
            {message.role === 'assistant' && message.actions?.length > 0 && (
              <ul className="goals-chat-action-list">
                {message.actions.map((action, index) => (
                  <li key={`${message.id}-${index}`}>{action.summary}</li>
                ))}
              </ul>
            )}
            <span className="goals-chat-message-time">{formatTime(message.createdAt)}</span>
          </div>
        ))}

        {isLoading && (
          <div className="goals-chat-message goals-chat-message--assistant goals-chat-message--typing">
            <span className="goals-chat-typing-dot" />
            <span className="goals-chat-typing-dot" />
            <span className="goals-chat-typing-dot" />
          </div>
        )}
        <div ref={listEndRef} />
      </div>

      {pendingAction && (
        <div className="goals-chat-confirm-row">
          <span>Apply this previewed goal change?</span>
          <div className="goals-chat-confirm-actions">
            <button type="button" className="secondary-btn" onClick={handleCancel} disabled={isLoading}>
              Cancel
            </button>
            <button type="button" className="primary-btn" onClick={handleConfirm} disabled={isLoading}>
              Confirm
            </button>
          </div>
        </div>
      )}

      <div className="goals-chat-input-row">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your goals..."
          rows={2}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />
        <button type="button" className="primary-btn" onClick={() => handleSend()} disabled={!canSend}>
          Send
        </button>
      </div>
    </section>
  );
}
