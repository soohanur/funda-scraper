/**
 * Funda scraper API client. Wraps the FastAPI /funda/* endpoints.
 */
import { api } from "../api";

export type ScraperStatus = {
  status: "IDLE" | "RUNNING" | "PAUSED" | "STOPPING" | "COMPLETED" | "FAILED";
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
  collection_status: string;
  collection_page: number;
  ids_collected: number;
  ids_queued: number;
  duplicate_in_storage: number;
  duplicate_in_retry_queue: number;
  consecutive_failures: number;
};

export type PublicationDateOption = { value: number; label: string };

export const fundaApi = {
  async getStatus(): Promise<ScraperStatus> {
    const r = await api.get<ScraperStatus>("/funda/status");
    return r.data;
  },
  async start(publication_date: number) {
    const r = await api.post("/funda/start", { publication_date });
    return r.data;
  },
  async stop() {
    const r = await api.post("/funda/stop");
    return r.data;
  },
  async pause() {
    const r = await api.post("/funda/pause");
    return r.data;
  },
  async resume() {
    const r = await api.post("/funda/resume");
    return r.data;
  },
  async clearKvkStorage() {
    const r = await api.delete("/funda/kvk-storage");
    return r.data;
  },
  async getPublicationDateOptions(): Promise<{
    options: PublicationDateOption[];
    default: number;
  }> {
    const r = await api.get("/funda/publication-date-options");
    return r.data;
  },
  async getSheetsUrl(): Promise<{ url: string }> {
    const r = await api.get("/funda/sheets-url");
    return r.data;
  },
};

export function formatDuration(seconds: number): string {
  if (!seconds || Number.isNaN(seconds)) return "0s";
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}m ${secs}s`;
  }
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${mins}m`;
}
