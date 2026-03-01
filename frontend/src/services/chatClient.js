import { apiPost } from '../api';

const STORAGE_CONVERSATION_ID = 'mm_chat_widget_conversation_id';

function readConversationId() {
  try {
    const raw = localStorage.getItem(STORAGE_CONVERSATION_ID);
    return raw && raw.trim() ? raw.trim() : null;
  } catch {
    return null;
  }
}

function writeConversationId(conversationId) {
  try {
    if (conversationId) {
      localStorage.setItem(STORAGE_CONVERSATION_ID, conversationId);
    }
  } catch {
    // Ignore storage failures.
  }
}

export async function sendChatMessage({ message, conversationId = null }) {
  const trimmed = String(message || '').trim();
  if (!trimmed) {
    throw new Error('Message is empty.');
  }

  const payload = {
    message: trimmed,
    conversation_id: conversationId || readConversationId(),
  };

  const data = await apiPost('/ai/chat', payload);
  const reply = String(data?.reply || '').trim();

  if (!reply) {
    throw new Error('Empty assistant response.');
  }

  const nextConversationId = String(data?.conversation_id || '').trim();
  if (nextConversationId) {
    writeConversationId(nextConversationId);
  }

  return {
    reply,
    conversationId: nextConversationId || payload.conversation_id || null,
    actions: Array.isArray(data?.actions) ? data.actions : [],
    needsConfirmation: Boolean(data?.needs_confirmation),
  };
}

export function getStoredConversationId() {
  return readConversationId();
}
