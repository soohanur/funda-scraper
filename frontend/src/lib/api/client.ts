import axios, { type AxiosInstance, type AxiosError } from 'axios';
import { config } from '../config/env';
import { authStore } from '../stores/auth';
import { get } from 'svelte/store';
import { push } from 'svelte-spa-router';

class APIClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: config.API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 30000,
    });

    this.setupInterceptors();
  }

  private setupInterceptors() {
    // Request interceptor
    this.client.interceptors.request.use(
      (config) => {
        const auth = get(authStore);
        if (auth.token) {
          config.headers.Authorization = `Bearer ${auth.token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        if (error.response?.status === 401) {
          authStore.logout();
          push('/');
        }
        return Promise.reject(error);
      }
    );
  }

  get instance() {
    return this.client;
  }
}

export const apiClient = new APIClient().instance;
