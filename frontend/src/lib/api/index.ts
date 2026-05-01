// Export all API services
export { authAPI } from './auth';
export { jobsAPI } from './jobs';
export { filesAPI } from './files';
export { systemAPI } from './system';
export { apiClient } from './client';
export { fundaAPI } from './funda';

// Export types
export type { LoginRequest, RegisterRequest, AuthResponse, User } from '../types';
export type { JobCreate, JobUpdate, JobListResponse, JobLog } from './jobs';
export type { FileInfo, FileListResponse, FileUploadResponse } from './files';
export type { HealthCheck, SystemStats, WorkerInfo } from './system';
export type { ScraperStatus, ActionResponse, KvkStatsResponse, PublicationDateOption, PublicationDateOptions } from './funda';
