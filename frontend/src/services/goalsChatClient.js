import { apiPost } from '../api';

export async function sendGoalsChatMessage({ message, pendingAction = null }) {
  const trimmed = String(message || '').trim();
  if (!trimmed) {
    throw new Error('Message is empty.');
  }

  const payload = {
    message: trimmed,
    pending_action: pendingAction,
  };

  const data = await apiPost('/goals/chat', payload);
  const reply = String(data?.reply || '').trim();
  if (!reply) {
    throw new Error('Empty assistant response.');
  }

  return {
    reply,
    actions: Array.isArray(data?.actions) ? data.actions : [],
    needsConfirmation: Boolean(data?.needs_confirmation),
    pendingAction: data?.pending_action || null,
  };
}
