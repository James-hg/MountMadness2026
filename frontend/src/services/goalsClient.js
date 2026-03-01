import { apiDelete, apiGet, apiPatch, apiPost } from '../api';

export async function getGoals(status = 'active') {
  const query = status ? `?status=${encodeURIComponent(status)}` : '';
  return apiGet(`/goals${query}`);
}

export async function getGoal(goalId) {
  return apiGet(`/goals/${goalId}`);
}

export async function createGoal(payload) {
  return apiPost('/goals', payload);
}

export async function updateGoal(goalId, patch) {
  return apiPatch(`/goals/${goalId}`, patch);
}

export async function deleteGoal(goalId) {
  return apiDelete(`/goals/${goalId}`);
}
