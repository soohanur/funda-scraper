import { apiClient } from './client';

export interface FileInfo {
  filename: string;
  display_name?: string;
  size: number;
  created_at: string;
  modified_at: string;
}

export interface FileListResponse {
  files: FileInfo[];
  total: number;
}

export interface FileUploadResponse {
  filename: string;
  file_path: string;
  size: number;
  uploaded_at: string;
}

export const filesAPI = {
  async uploadFile(file: File, jobUuid: string): Promise<FileUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await apiClient.post<FileUploadResponse>(
      `/files/upload?job_uuid=${jobUuid}`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response.data;
  },

  async listInputFiles(): Promise<FileListResponse> {
    const response = await apiClient.get<FileListResponse>('/files/inputs');
    return response.data;
  },

  async listOutputFiles(): Promise<FileListResponse> {
    const response = await apiClient.get<FileListResponse>('/files/outputs');
    return response.data;
  },

  async downloadFile(filename: string): Promise<Blob> {
    const response = await apiClient.get(`/files/download/${filename}`, {
      responseType: 'blob',
    });
    return response.data;
  },

  async deleteFile(filename: string, fileType: 'input' | 'output'): Promise<void> {
    await apiClient.delete(`/files/${filename}?file_type=${fileType}`);
  },

  async getCsvHeaders(filename: string): Promise<string[]> {
    const response = await apiClient.get<{ headers: string[] }>(`/files/csv-headers/${filename}`);
    return response.data.headers;
  },
};
