import { apiClient } from './client';
import type { LoginRequest, RegisterRequest, AuthResponse, User } from '../types';

export const authAPI = {
  async login(data: LoginRequest): Promise<AuthResponse> {
    const params = new URLSearchParams();
    params.append('username', data.username);
    params.append('password', data.password);
    
    const response = await apiClient.post<AuthResponse>('/auth/login', params, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
    return response.data;
  },

  async register(data: RegisterRequest): Promise<User> {
    const response = await apiClient.post<User>('/auth/register', data);
    return response.data;
  },

  async getCurrentUser(): Promise<User> {
    const response = await apiClient.get<User>('/auth/me');
    return response.data;
  },
};
