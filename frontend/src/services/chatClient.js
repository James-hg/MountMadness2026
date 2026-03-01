import { apiPost } from '../api';

function formatHistory(history) {
  return history
    .slice(-8)
    .map((item) => `${item.role === 'assistant' ? 'Assistant' : 'User'}: ${item.content}`)
    .join('\n');
}

export async function sendChatMessage({ message, history = [] }) {
  const trimmed = String(message || '').trim();
  if (!trimmed) {
    throw new Error('Message is empty.');
  }

  const historyText = formatHistory(history);
  const prompt = [
    'You are an AI financial assistant for a personal finance tracker.',
    'Keep responses concise, practical, and easy to understand.',
    historyText ? `Conversation so far:\n${historyText}` : '',
    `User question: ${trimmed}`,
  ]
    .filter(Boolean)
    .join('\n\n');

  const data = await apiPost('/api/generate', { prompt });
  const text = String(data?.text || '').trim();
  if (!text) {
    throw new Error('Empty assistant response.');
  }
  return text;
}

