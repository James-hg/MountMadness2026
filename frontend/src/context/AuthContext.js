import React, { createContext, useContext, useState, useCallback } from 'react';
import { apiPost } from '../api';

const AuthContext = createContext(null);

const MOCK_MODE = false;

function getMockUsers() {
  try {
    return JSON.parse(localStorage.getItem('mock_users') || '[]');
  } catch {
    return [];
  }
}

function saveMockUsers(users) {
  localStorage.setItem('mock_users', JSON.stringify(users));
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('user'));
    } catch {
      return null;
    }
  });

  const isAuthenticated = !!localStorage.getItem('access_token');

  const saveSession = useCallback((data) => {
    localStorage.setItem('access_token', data.access_token);
    if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);
    localStorage.setItem('user', JSON.stringify(data.user));
    setUser(data.user);
  }, []);

  const register = useCallback(async (name, email, password) => {
    if (MOCK_MODE) {
      const users = getMockUsers();
      const exists = users.find((u) => u.email === email.toLowerCase());
      if (exists) throw new Error('An account with this email already exists.');
      const newUser = { name, email: email.toLowerCase(), id: Date.now().toString() };
      users.push({ ...newUser, password });
      saveMockUsers(users);
      const data = { access_token: 'mock_token_' + newUser.id, user: newUser };
      saveSession(data);
      return newUser;
    }
    const data = await apiPost('/auth/register', { name, email, password });
    saveSession(data);
    return data.user;
  }, [saveSession]);

  const login = useCallback(async (email, password) => {
    if (MOCK_MODE) {
      const users = getMockUsers();
      const found = users.find(
        (u) => u.email === email.toLowerCase() && u.password === password
      );
      if (!found) throw new Error('Invalid email or password.');
      const { password: _, ...userData } = found;
      const data = { access_token: 'mock_token_' + userData.id, user: userData };
      saveSession(data);
      return userData;
    }
    const data = await apiPost('/auth/login', { email, password });
    saveSession(data);
    return data.user;
  }, [saveSession]);

  const logout = useCallback(() => {
    if (!MOCK_MODE) {
      const token = localStorage.getItem('access_token');
      const refreshToken = localStorage.getItem('refresh_token');
      if (token) {
        fetch('/api/auth/logout', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ refresh_token: refreshToken }),
        }).catch(() => {});
      }
    }
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isAuthenticated, register, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
