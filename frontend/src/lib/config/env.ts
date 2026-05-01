/**
 * Environment Configuration
 * Automatically adapts to development, staging, and production environments
 */

// Detect environment
const isDevelopment = import.meta.env.DEV;
const isProduction = import.meta.env.PROD;

// API Base URL Detection
function getApiBaseUrl(): string {
  // 1. Use explicit environment variable if set
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }

  // 2. Use VITE_API_BASE_URL if set (for full URL)
  if (import.meta.env.VITE_API_BASE_URL) {
    const baseUrl = import.meta.env.VITE_API_BASE_URL;
    return `${baseUrl}/api/v1`;
  }

  // 3. Production: use same domain
  if (isProduction) {
    const protocol = window.location.protocol;
    const host = window.location.host;
    return `${protocol}//${host}/api/v1`;
  }

  // 4. Development: default to localhost
  return 'http://localhost:8000/api/v1';
}

// WebSocket URL Detection
function getWebSocketUrl(): string {
  const apiUrl = getApiBaseUrl();
  
  // Remove /api/v1 suffix and replace http/https with ws/wss
  const baseUrl = apiUrl.replace('/api/v1', '');
  
  if (baseUrl.startsWith('https://')) {
    return baseUrl.replace('https://', 'wss://');
  }
  
  return baseUrl.replace('http://', 'ws://');
}

export const config = {
  API_BASE_URL: getApiBaseUrl(),
  WS_BASE_URL: getWebSocketUrl(),
  APP_NAME: 'Nicky',
  APP_DESCRIPTION: 'AI Automation Platform',
  ADMIN_SECRET_KEY_LABEL: 'Admin Secret Key',
  ENVIRONMENT: isProduction ? 'production' : 'development',
} as const;
