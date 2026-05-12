import { api, ApiError } from './client';

// Backend contract: POST /login { email, password } -> { success, token?, name?, email?, role?, message? }
export async function login({ email, password }) {
  const { data } = await api.post('/login', { email, password });

  if (!data?.success || !data?.token) {
    throw new ApiError(data?.message || 'Invalid credentials', {
      status: 401,
      data,
    });
  }

  const user = {
    name: data.name || '',
    email: data.email || email,
    role: (data.role || 'employee').toLowerCase(),
  };

  return { token: data.token, user };
}

// Backend contract: POST /register { email|username, password, role?, name? }
export async function register({ username, email, password, role, name }) {
  const resolvedEmail = (email || username || '').trim();
  const { data } = await api.post('/register', {
    email: resolvedEmail,
    password,
    role,
    name,
  });

  if (!data?.success || !data?.token) {
    throw new ApiError(data?.message || 'Registration failed', {
      status: 400,
      data,
    });
  }

  const user = {
    name: data.name || '',
    email: data.email || resolvedEmail,
    role: (data.role || 'employee').toLowerCase(),
  };

  return { token: data.token, user };
}

