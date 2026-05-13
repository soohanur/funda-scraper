"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  Database,
  Mail,
  Send,
  Calendar,
  AlertCircle,
  TrendingUp,
} from "lucide-react";
import { dashboardApi, type LatestProperty } from "@/lib/api/dashboard";
import { PageContainer } from "@/components/page-container";
import { cn, formatDate, formatNumber } from "@/lib/utils";

export default function DashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard", "stats"],
    queryFn: dashboardApi.stats,
    refetchInterval: 15_000,
  });

  return (
    <PageContainer>
      {/* Top stat grid — every card is a Link to the relevant page (spec). */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard
          href="/emails"
          label="Total emails sent"
          value={formatNumber(data?.emails_sent ?? 0)}
          icon={<CheckCircle2 className="h-4 w-4" />}
          tone="emerald"
          loading={isLoading}
        />
        <StatCard
          href="/emails"
          label="Sent today"
          value={formatNumber(data?.emails_sent_today ?? 0)}
          icon={<Send className="h-4 w-4" />}
          tone="brand"
          loading={isLoading}
        />
        <StatCard
          href="/data"
          label="Total scraped"
          value={formatNumber(data?.total_scraped ?? 0)}
          icon={<Database className="h-4 w-4" />}
          tone="indigo"
          loading={isLoading}
        />
        <StatCard
          href="/data?email_status=not_sent"
          label="Not emailed yet"
          value={formatNumber(data?.not_emailed ?? 0)}
          icon={<Mail className="h-4 w-4" />}
          tone="amber"
          loading={isLoading}
        />
        <StatCard
          href="/data?days_back=1"
          label="Scraped today"
          value={formatNumber(data?.scraped_today ?? 0)}
          icon={<TrendingUp className="h-4 w-4" />}
          tone="brand"
          loading={isLoading}
        />
      </div>

      {/* Sub-stat row */}
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <MiniCard label="Email queued" value={data?.emails_queued ?? 0} icon={<Clock className="h-4 w-4" />} />
        <MiniCard label="Email failed" value={data?.emails_failed ?? 0} icon={<AlertCircle className="h-4 w-4" />} />
        <MiniCard label="Total emails" value={data?.total_emails ?? 0} icon={<Mail className="h-4 w-4" />} />
      </div>

      {/* Latest scrapes */}
      <div className="card mt-6 overflow-hidden">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
          <div>
            <h3 className="text-sm font-semibold">Latest scrapes</h3>
            <p className="text-xs text-[var(--muted-foreground)]">Newest 10 properties</p>
          </div>
          <Link href="/data" className="btn-ghost text-xs">
            View all
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] bg-[var(--surface-2)]">
                <Th>Scraped</Th>
                <Th>Address</Th>
                <Th>Asking</Th>
                <Th>Suggested</Th>
                <Th>Type</Th>
                <Th>Energy</Th>
                <Th>Agency</Th>
                <Th>Status</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {(data?.latest_scrapes ?? []).length === 0 && !isLoading && (
                <tr>
                  <td colSpan={9} className="p-10 text-center text-sm text-[var(--muted-foreground)]">
                    No scrapes yet. Start the <Link href="/scraper" className="text-[var(--color-brand-600)] underline">Funda Scraper</Link>.
                  </td>
                </tr>
              )}
              {(data?.latest_scrapes ?? []).map((p, idx) => (
                <PropertyRow key={p.id} p={p} idx={idx} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </PageContainer>
  );
}

function PropertyRow({ p, idx }: { p: LatestProperty; idx: number }) {
  return (
    <tr
      className={cn(
        "border-b border-[var(--border)] hover:bg-[var(--muted)]",
        idx % 2 === 1 && "bg-[var(--surface-2)]"
      )}
    >
      <Td>
        <span className="inline-flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
          <Calendar className="h-3 w-3" />
          {p.scrape_date ?? formatDate(p.created_at)}
        </span>
      </Td>
      <Td>
        <span className="font-medium">{p.address ?? p.url}</span>
      </Td>
      <Td>{p.asking_price ?? "—"}</Td>
      <Td className="font-semibold text-[var(--color-brand-700)]">{p.suggested_bid ?? "—"}</Td>
      <Td>{p.property_type ?? "—"}</Td>
      <Td>{p.energy_label ?? "—"}</Td>
      <Td>{p.agency_name ?? "—"}</Td>
      <Td>
        <StatusChip status={p.email_status ?? "not_sent"} />
      </Td>
      <Td className="text-right">
        <Link href={`/data/${p.id}`} className="text-xs text-[var(--color-brand-600)] hover:underline">
          Open
        </Link>
      </Td>
    </tr>
  );
}

function StatCard({
  href,
  label,
  value,
  icon,
  tone,
  loading,
}: {
  href: string;
  label: string;
  value: string;
  icon: React.ReactNode;
  tone: "brand" | "emerald" | "amber" | "indigo";
  loading?: boolean;
}) {
  const toneIcon =
    tone === "brand"
      ? "bg-[var(--color-brand-50)] text-[var(--color-brand-700)]"
      : tone === "emerald"
      ? "bg-emerald-50 text-emerald-700"
      : tone === "amber"
      ? "bg-amber-50 text-amber-700"
      : "bg-indigo-50 text-indigo-700";
  return (
    <Link
      href={href}
      className="card group relative flex items-center justify-between p-5 transition-all hover:-translate-y-0.5 hover:shadow-md"
    >
      <div>
        <div className="text-xs font-medium text-[var(--muted-foreground)]">{label}</div>
        <div className="mt-1 text-2xl font-semibold tabular-nums">
          {loading ? <span className="text-[var(--muted-foreground)]">…</span> : value}
        </div>
      </div>
      <div className={cn("grid h-10 w-10 place-items-center rounded-xl", toneIcon)}>{icon}</div>
      <ArrowRight className="absolute right-3 top-3 h-3.5 w-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
    </Link>
  );
}

function MiniCard({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) {
  return (
    <div className="card flex items-center justify-between p-4">
      <div>
        <div className="text-xs font-medium text-[var(--muted-foreground)]">{label}</div>
        <div className="mt-0.5 text-xl font-semibold tabular-nums">{formatNumber(value)}</div>
      </div>
      <div className="grid h-9 w-9 place-items-center rounded-xl bg-[var(--surface-2)] text-[var(--muted-foreground)]">
        {icon}
      </div>
    </div>
  );
}

function Th({ children }: { children?: React.ReactNode }) {
  return (
    <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
      {children}
    </th>
  );
}
function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={cn("px-3 py-2.5", className)}>{children}</td>;
}

function StatusChip({ status }: { status: string }) {
  const tone =
    status === "sent"
      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
      : status === "failed"
      ? "bg-rose-50 text-rose-700 border-rose-200"
      : status === "queued"
      ? "bg-amber-50 text-amber-700 border-amber-200"
      : "bg-[var(--muted)] text-[var(--muted-foreground)] border-[var(--border)]";
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium", tone)}>
      {status}
    </span>
  );
}
