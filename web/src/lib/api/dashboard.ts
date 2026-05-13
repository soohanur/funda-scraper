import { api } from "../api";

export type LatestProperty = {
  id: number;
  url: string;
  address?: string | null;
  asking_price?: string | null;
  suggested_bid?: string | null;
  property_type?: string | null;
  energy_label?: string | null;
  agency_name?: string | null;
  email_status?: string | null;
  scrape_date?: string | null;
  created_at?: string | null;
};

export type DashboardStats = {
  total_scraped: number;
  scraped_today: number;
  total_emails: number;
  emails_sent: number;
  emails_sent_today: number;
  emails_queued: number;
  emails_failed: number;
  not_emailed: number;
  latest_scrapes: LatestProperty[];
};

export const dashboardApi = {
  async stats(): Promise<DashboardStats> {
    const r = await api.get<DashboardStats>("/dashboard/stats");
    return r.data;
  },
};
