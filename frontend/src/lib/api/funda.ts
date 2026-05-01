/**
 * Funda Property Scraper API Client
 */
import { apiClient } from './client';

export interface ScraperStatus {
  status: 'IDLE' | 'RUNNING' | 'PAUSED' | 'STOPPING' | 'COMPLETED' | 'FAILED';
  total_kvk_stored: number;
  kvk_collected_this_session: number;
  total_search_results: number;
  current_batch: number;
  properties_scraped: number;
  properties_filtered: number;
  properties_failed: number;
  current_page: number;
  total_pages_scraped: number;
  batch_progress: number;
  collection_status: string;
  collection_page: number;
  ids_collected: number;
  ids_queued: number;
  duplicate_in_storage: number;
  duplicate_in_retry_queue: number;
  active_workers: number;
  excel_files_created: number;
  sheets_written: number;
  valuations_written: number;
  valuations_failed: number;
  valuations_pending: number;
  valuations_fallback: number;
  elapsed_seconds: number;
  last_error: string;
  browser_restarts: number;
  consecutive_failures: number;
}

export interface ActionResponse {
  success: boolean;
  message: string;
  status: string;
}

export interface KvkStatsResponse {
  total_stored: number;
  sample: string[];
}

export interface PublicationDateOption {
  value: number;
  label: string;
}

export interface PublicationDateOptions {
  options: PublicationDateOption[];
  default: number;
}

/**
 * Get current scraper status
 */
export async function getStatus(): Promise<ScraperStatus> {
  const response = await apiClient.get('/funda/status');
  return response.data;
}

/**
 * Start the scraper with given publication date filter
 */
export async function startScraper(publicationDate: number = 5): Promise<ActionResponse> {
  const response = await apiClient.post('/funda/start', {
    publication_date: publicationDate,
  });
  return response.data;
}

/**
 * Stop the scraper
 */
export async function stopScraper(): Promise<ActionResponse> {
  const response = await apiClient.post('/funda/stop');
  return response.data;
}

/**
 * Pause the scraper
 */
export async function pauseScraper(): Promise<ActionResponse> {
  const response = await apiClient.post('/funda/pause');
  return response.data;
}

/**
 * Resume the scraper
 */
export async function resumeScraper(): Promise<ActionResponse> {
  const response = await apiClient.post('/funda/resume');
  return response.data;
}

/**
 * Get KVK storage stats
 */
export async function getKvkStats(): Promise<KvkStatsResponse> {
  const response = await apiClient.get('/funda/kvk-storage');
  return response.data;
}

/**
 * Clear KVK storage
 */
export async function clearKvkStorage(): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.delete('/funda/kvk-storage');
  return response.data;
}

/**
 * Get publication date options
 */
export async function getPublicationDateOptions(): Promise<PublicationDateOptions> {
  const response = await apiClient.get('/funda/publication-date-options');
  return response.data;
}

/**
 * Get Google Sheets URL
 */
export async function getSheetsUrl(): Promise<{ url: string; spreadsheet_id: string }> {
  const response = await apiClient.get('/funda/sheets-url');
  return response.data;
}

export const fundaAPI = {
  getStatus,
  startScraper,
  stopScraper,
  pauseScraper,
  resumeScraper,
  getKvkStats,
  clearKvkStorage,
  getPublicationDateOptions,
  getSheetsUrl,
};
