import { api } from './client';

// Backend contract: POST /chat { message } (+ Bearer token) -> { reply }
// We keep token-in-body optional for backwards-compat.
export async function sendChatMessage({ message, token }) {
  const payload = token ? { message, token } : { message };
  const { data } = await api.post('/chat', payload);
  return { reply: data?.reply ?? '' };
}

