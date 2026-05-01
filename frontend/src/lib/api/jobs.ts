import { apiClient } from './client';
import type { Job, JobStatus, JobPriority } from '../types';

export interface JobCreate {
  tool_type: string;
  name: string;
  description?: string;
  priority?: JobPriority;
  config?: Record<string, any>;
}

export interface JobUpdate {
  name?: string;
  description?: string;
  priority?: JobPriority;
  config?: Record<string, any>;
}

export interface JobListResponse {
  jobs: Job[];
  total: number;
  page: number;
  page_size: number;
}

export interface JobLog {
  id: number;
  job_id: number;
  level: string;
  message: string;
  timestamp: string;
}

export const jobsAPI = {
  async createJob(data: JobCreate): Promise<Job> {
    const response = await apiClient.post<Job>('/jobs', data);
    return response.data;
  },

  async listJobs(params?: {
    status_filter?: JobStatus;
    page?: number;
    page_size?: number;
  }): Promise<JobListResponse> {
    const response = await apiClient.get<JobListResponse>('/jobs', { params });
    return response.data;
  },

  async getJob(jobUuid: string): Promise<Job> {
    const response = await apiClient.get<Job>(`/jobs/${jobUuid}`);
    return response.data;
  },

  async updateJob(jobUuid: string, data: JobUpdate): Promise<Job> {
    const response = await apiClient.patch<Job>(`/jobs/${jobUuid}`, data);
    return response.data;
  },

  async startJob(jobUuid: string): Promise<Job> {
    const response = await apiClient.post<Job>(`/jobs/${jobUuid}/start`);
    return response.data;
  },

  async cancelJob(jobUuid: string): Promise<Job> {
    const response = await apiClient.post<Job>(`/jobs/${jobUuid}/cancel`);
    return response.data;
  },

  async pauseJob(jobUuid: string): Promise<Job> {
    const response = await apiClient.post<Job>(`/jobs/${jobUuid}/pause`);
    return response.data;
  },

  async resumeJob(jobUuid: string): Promise<Job> {
    const response = await apiClient.post<Job>(`/jobs/${jobUuid}/resume`);
    return response.data;
  },

  async retryJob(jobUuid: string): Promise<Job> {
    const response = await apiClient.post<Job>(`/jobs/${jobUuid}/retry`);
    return response.data;
  },

  async deleteJob(jobUuid: string): Promise<void> {
    await apiClient.delete(`/jobs/${jobUuid}`);
  },

  async getJobLogs(jobUuid: string, limit: number = 100): Promise<JobLog[]> {
    const response = await apiClient.get<JobLog[]>(`/jobs/${jobUuid}/logs`, {
      params: { limit },
    });
    return response.data;
  },

  async downloadJobResult(jobUuid: string): Promise<Blob> {
    const response = await apiClient.get(`/jobs/${jobUuid}/download`, {
      responseType: 'blob',
    });
    return response.data;
  },
};
