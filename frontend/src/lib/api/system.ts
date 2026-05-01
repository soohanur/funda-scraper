import { apiClient } from './client';

export interface HealthCheck {
  status: string;
  version: string;
  timestamp: string;
  database: string;
  redis: string;
  celery: string;
}

export interface SystemStats {
  cpu_percent: number;
  memory_used: number;
  memory_total: number;
  memory_percent: number;
  disk_used: number;
  disk_total: number;
  disk_percent: number;
  active_jobs: number;
  completed_today: number;
  failed_today: number;
  total_jobs: number;
}

export interface WorkerInfo {
  hostname: string;
  active_tasks: number;
  processed_tasks: number;
  status: string;
}

export interface WorkerConfig {
  max_workers: number;
  max_concurrent_jobs: number;
}

export interface WorkerConfigUpdateResponse {
  success: boolean;
  max_workers: number;
  message: string;
}

export const systemAPI = {
  async getHealth(): Promise<HealthCheck> {
    const response = await apiClient.get<HealthCheck>('/system/health');
    return response.data;
  },

  async getStats(): Promise<SystemStats> {
    const response = await apiClient.get<SystemStats>('/system/stats');
    return response.data;
  },

  async getWorkers(): Promise<WorkerInfo[]> {
    const response = await apiClient.get<WorkerInfo[]>('/system/workers');
    return response.data;
  },

  async getWorkerConfig(): Promise<WorkerConfig> {
    const response = await apiClient.get<WorkerConfig>('/system/config/workers');
    return response.data;
  },

  async updateWorkerConfig(maxWorkers: number): Promise<WorkerConfigUpdateResponse> {
    const response = await apiClient.post<WorkerConfigUpdateResponse>('/system/config/workers', {
      max_workers: maxWorkers
    });
    return response.data;
  },
};
