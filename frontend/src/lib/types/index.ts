// Auth Types
export interface User {
  id: number;
  username: string;
  email: string;
  full_name?: string;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  admin_key: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

// Tool Types
export interface Tool {
  id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  status: 'active' | 'soon' | 'disabled';
  isFavorite?: boolean;
  route: string;
}

// Job Types (for future use)
export interface Job {
  id: number;
  job_uuid: string;
  user_id: number;
  tool_type: string;
  name: string;
  description?: string;
  status: JobStatus;
  priority: JobPriority;
  progress: number;
  input_file_path?: string;
  output_file_path?: string;
  display_filename?: string;
  total_rows: number;
  processed_rows: number;
  successful_rows: number;
  failed_rows: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
}

export type JobStatus = 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'retrying';
export type JobPriority = 'low' | 'normal' | 'high' | 'urgent';
