import { apiPost } from '../api';

const STORAGE_PREFIX = 'mm_chat_widget';
const LEGACY_STORAGE_CONVERSATION_ID = 'mm_chat_widget_conversation_id';

function conversationKey(scope) {
  return `${STORAGE_PREFIX}_conversation_id:${scope}`;
}

export function getChatStorageScope(user) {
  if (user?.id) return `user:${String(user.id)}`;
  if (user?.email) return `email:${String(user.email).toLowerCase()}`;
  return 'anon';
}

function readConversationId(scope) {
  try {
    const raw = localStorage.getItem(conversationKey(scope));
    return raw && raw.trim() ? raw.trim() : null;
  } catch {
    return null;
  }
}

function writeConversationId(scope, conversationId) {
  try {
    if (conversationId) {
      localStorage.setItem(conversationKey(scope), conversationId);
    }
  } catch {
    // Ignore storage failures.
  }
}

export async function sendChatMessage({ message, conversationId = null, storageScope = 'anon' }) {
  const trimmed = String(message || '').trim();
  if (!trimmed) {
    throw new Error('Message is empty.');
  }

  const payload = {
    message: trimmed,
    conversation_id: conversationId || readConversationId(storageScope),
  };

  const data = await apiPost('/ai/chat', payload);
  const reply = String(data?.reply || '').trim();

  if (!reply) {
    throw new Error('Empty assistant response.');
  }

  const nextConversationId = String(data?.conversation_id || '').trim();
  if (nextConversationId) {
    writeConversationId(storageScope, nextConversationId);
  }

  return {
    reply,
    conversationId: nextConversationId || payload.conversation_id || null,
    actions: Array.isArray(data?.actions) ? data.actions : [],
    needsConfirmation: Boolean(data?.needs_confirmation),
  };
}

export function getStoredConversationId(storageScope = 'anon') {
  return readConversationId(storageScope);
}

export function clearChatStorageForUser(user) {
  const scope = getChatStorageScope(user);
  const scopedKeys = [
    `${STORAGE_PREFIX}_open:${scope}`,
    `${STORAGE_PREFIX}_messages:${scope}`,
    `${STORAGE_PREFIX}_unread:${scope}`,
    conversationKey(scope),
  ];

  try {
    scopedKeys.forEach((key) => localStorage.removeItem(key));

    // Cleanup one-time legacy keys so older shared history is removed.
    localStorage.removeItem(`${STORAGE_PREFIX}_open`);
    localStorage.removeItem(`${STORAGE_PREFIX}_messages`);
    localStorage.removeItem(`${STORAGE_PREFIX}_unread`);
    localStorage.removeItem(LEGACY_STORAGE_CONVERSATION_ID);
  } catch {
    // Ignore storage failures.
  }
}
