"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  Check,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Image as ImageIcon,
  Loader2,
  Mail,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { propertiesApi, type Property } from "@/lib/api/properties";
import { cn } from "@/lib/utils";

/** Funda brand glyph (SVG, no external dep). Color matches link tint. */
function FundaIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className}
      aria-hidden="true"
    >
      <path d="M4 21V5a2 2 0 0 1 2-2h6.5a2 2 0 0 1 1.41.59L19.4 9.1a2 2 0 0 1 .6 1.41V21a0 0 0 0 1 0 0H4Zm3-9h6v-2H7v2Zm0 4h10v-2H7v2Z" />
    </svg>
  );
}

/**
 * Row shape consumed by the table.
 */
export type PropertiesTableRow = {
  id: number;
  url: string;
  scrape_date?: string | null;
  address?: string | null;
  listed_since?: string | null;
  days_on_market?: string | null;
  asking_price?: string | null;
  woz_value?: string | null;
  suggested_bid?: string | null;
  bidding_price?: string | null;
  price_per_m2?: string | null;
  living_area?: string | null;
  plot_area?: string | null;
  rooms?: string | null;
  bedrooms?: string | null;
  construction_year?: string | null;
  property_type?: string | null;
  energy_label?: string | null;
  heating?: string | null;
  insulation?: string | null;
  maintenance_inside?: string | null;
  maintenance_outside?: string | null;
  garden?: string | null;
  garden_orientation?: string | null;
  parking?: string | null;
  vve?: string | null;
  erfpacht?: string | null;
  acceptance?: string | null;
  description?: string | null;
  images?: string | null;
  agency_name?: string | null;
  agency_phone?: string | null;
  agency_email?: string | null;
  agency_website?: string | null;
  sheet_tab?: string | null;
  email_status?: string | null;
};

/**
 * Column set mirrors the Google Sheet HEADERS order, with the
 * user-requested adjustment: Listed Since + Days on Market come BEFORE
 * Asking Price (then the rest of the sheet flows).
 */
const COLUMNS: Array<{
  key: keyof PropertiesTableRow;
  label: string;
  sortable?: boolean;
  width?: string;
}> = [
  { key: "scrape_date", label: "Scrape Date", sortable: true, width: "110px" },
  { key: "address", label: "Address", sortable: true, width: "240px" },
  { key: "listed_since", label: "Listed Since", sortable: true, width: "110px" },
  { key: "days_on_market", label: "DOM", sortable: true, width: "70px" },
  { key: "asking_price", label: "Asking", sortable: true, width: "110px" },
  { key: "woz_value", label: "WOZ", sortable: true, width: "110px" },
  { key: "suggested_bid", label: "Suggested", sortable: true, width: "110px" },
  { key: "bidding_price", label: "Bidding (edit)", width: "150px" },
  { key: "price_per_m2", label: "€/m²", width: "80px" },
  { key: "living_area", label: "m²", width: "70px" },
  { key: "plot_area", label: "Plot m²", width: "80px" },
  { key: "rooms", label: "Rooms", width: "70px" },
  { key: "bedrooms", label: "Beds", width: "60px" },
  { key: "construction_year", label: "Year", width: "70px" },
  { key: "property_type", label: "Type", sortable: true, width: "180px" },
  { key: "energy_label", label: "Energy", sortable: true, width: "70px" },
  { key: "heating", label: "Heating", width: "140px" },
  { key: "insulation", label: "Insulation", width: "150px" },
  { key: "maintenance_inside", label: "Maint. In", width: "120px" },
  { key: "maintenance_outside", label: "Maint. Out", width: "120px" },
  { key: "garden", label: "Garden", width: "140px" },
  { key: "garden_orientation", label: "Orient.", width: "120px" },
  { key: "parking", label: "Parking", width: "140px" },
  { key: "vve", label: "VVE", width: "100px" },
  { key: "erfpacht", label: "Erfpacht", width: "120px" },
  { key: "acceptance", label: "Acceptance", width: "140px" },
  { key: "description", label: "Description", width: "260px" },
  { key: "images", label: "Images", width: "110px" },
  { key: "agency_name", label: "Agency", sortable: true, width: "160px" },
  { key: "agency_phone", label: "Phone", width: "130px" },
  { key: "agency_email", label: "Email", width: "180px" },
  { key: "agency_website", label: "Website", width: "180px" },
  { key: "sheet_tab", label: "Range", width: "120px" },
  { key: "email_status", label: "Status", sortable: true, width: "110px" },
];

export function PropertiesTable({
  items,
  isLoading,
  isFetching,
  emptyMessage,
  sort,
  order,
  onSort,
  onEmail,
  showBiddingEdit = true,
  className,
}: {
  items: PropertiesTableRow[];
  isLoading?: boolean;
  isFetching?: boolean;
  emptyMessage?: React.ReactNode;
  sort?: string;
  order?: "asc" | "desc";
  onSort?: (key: string) => void;
  onEmail?: (row: PropertiesTableRow) => void;
  showBiddingEdit?: boolean;
  /** Extra classes for the outer card. Use `flex-1 min-h-0` to fill parent. */
  className?: string;
}) {
  void isFetching;

  // Lightbox state — clicking the Images cell opens this for the row.
  const [lightbox, setLightbox] = useState<{ images: string[]; address: string } | null>(null);

  return (
    <div className={cn("card flex min-h-0 flex-col overflow-hidden", className)}>
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-[var(--surface)]">
            <tr className="border-b border-[var(--border)]">
              {COLUMNS.map((c) => (
                <th
                  key={c.key as string}
                  style={{ minWidth: c.width }}
                  className="px-3 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]"
                >
                  {c.sortable && onSort ? (
                    <button
                      type="button"
                      onClick={() => onSort(c.key as string)}
                      className="inline-flex items-center gap-1 hover:text-[var(--foreground)]"
                    >
                      {c.label}
                      {sort === c.key &&
                        (order === "asc" ? (
                          <ArrowUp className="h-3 w-3" />
                        ) : (
                          <ArrowDown className="h-3 w-3" />
                        ))}
                    </button>
                  ) : (
                    c.label
                  )}
                </th>
              ))}
              <th
                className="sticky right-0 bg-[var(--surface)] px-3 py-3 text-right text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]"
                style={{ minWidth: "140px" }}
              >
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && !isLoading && (
              <tr>
                <td
                  colSpan={COLUMNS.length + 1}
                  className="p-10 text-center text-sm text-[var(--muted-foreground)]"
                >
                  {emptyMessage ?? "No properties to show."}
                </td>
              </tr>
            )}
            {items.map((p, idx) => (
              <tr
                key={p.id}
                className={cn(
                  "border-b border-[var(--border)] hover:bg-[var(--muted)]",
                  idx % 2 === 1 && "bg-[var(--surface-2)]",
                )}
              >
                {COLUMNS.map((c) => (
                  <td key={c.key as string} className="px-3 py-2.5 align-top">
                    {c.key === "bidding_price" && showBiddingEdit ? (
                      <BiddingCell property={p} />
                    ) : c.key === "images" ? (
                      <ImagesCell
                        property={p}
                        onOpen={(images) =>
                          setLightbox({ images, address: p.address ?? "Property" })
                        }
                      />
                    ) : (
                      renderCell(p, c.key)
                    )}
                  </td>
                ))}
                <td className="sticky right-0 bg-[var(--surface)] px-3 py-2.5 text-right align-top">
                  <div className="flex justify-end gap-1">
                    {p.url && (
                      <a
                        href={p.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="rounded-lg p-1.5 text-[var(--color-brand-700)] hover:bg-[var(--color-brand-50)]"
                        title="Open on funda.nl"
                      >
                        <FundaIcon className="h-4 w-4" />
                      </a>
                    )}
                    {onEmail && (
                      <button
                        type="button"
                        onClick={() => onEmail(p)}
                        className="rounded-lg p-1.5 text-[var(--color-brand-600)] hover:bg-[var(--color-brand-50)]"
                        title="Send email"
                      >
                        <Mail className="h-4 w-4" />
                      </button>
                    )}
                    <Link
                      href={`/data/${p.id}`}
                      className="rounded-lg p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--muted)]"
                      title="View profile"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </Link>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {lightbox && (
        <Lightbox
          images={lightbox.images}
          address={lightbox.address}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
}

// ── Inline editable bidding price ────────────────────────────────
function BiddingCell({ property }: { property: PropertiesTableRow }) {
  const qc = useQueryClient();
  const [value, setValue] = useState<string>(property.bidding_price ?? "");
  const [original, setOriginal] = useState<string>(property.bidding_price ?? "");

  useEffect(() => {
    const v = property.bidding_price ?? "";
    if (v !== original) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setOriginal(v);
      setValue(v);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [property.bidding_price]);

  const saveM = useMutation({
    mutationFn: (v: string) => propertiesApi.update(property.id, { bidding_price: v }),
    onSuccess: (updated) => {
      setOriginal(updated.bidding_price ?? "");
      qc.invalidateQueries({ queryKey: ["properties"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Bidding price saved");
    },
    onError: () => toast.error("Save failed"),
  });

  const dirty = value !== original;

  return (
    <div className="flex items-center gap-1">
      <input
        type="text"
        inputMode="numeric"
        className="input h-8 w-full px-2 py-1 text-sm"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            if (dirty) saveM.mutate(value);
          }
          if (e.key === "Escape") setValue(original);
        }}
        placeholder="€ —"
      />
      {dirty && (
        <button
          type="button"
          className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[var(--color-brand-600)] text-white hover:bg-[var(--color-brand-700)]"
          onClick={() => saveM.mutate(value)}
          disabled={saveM.isPending}
          title="Save"
        >
          {saveM.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
        </button>
      )}
    </div>
  );
}

// ── Images cell — thumbnail + hover preview + click → lightbox ───
function parseImages(raw?: string | null): string[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((u) => u.trim())
    .filter((u) => u.length > 0);
}

function ImagesCell({
  property,
  onOpen,
}: {
  property: PropertiesTableRow;
  onOpen: (images: string[]) => void;
}) {
  const images = parseImages(property.images);
  if (images.length === 0) {
    return <span className="text-[var(--muted-foreground)]">—</span>;
  }
  return (
    <button
      type="button"
      onClick={() => onOpen(images)}
      className="group relative flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 py-1 hover:border-[var(--color-brand-400)]"
      title={`${images.length} image${images.length === 1 ? "" : "s"}`}
    >
      <span className="relative h-10 w-14 shrink-0 overflow-hidden rounded-md bg-[var(--muted)]">
        {/* Use plain img for arbitrary remote hosts to avoid Next config noise. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={images[0]}
          alt=""
          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-110"
          loading="lazy"
        />
      </span>
      <span className="flex items-center gap-1 text-xs">
        <ImageIcon className="h-3.5 w-3.5" />
        {images.length}
      </span>
    </button>
  );
}

// ── Lightbox / carousel ──────────────────────────────────────────
function Lightbox({
  images,
  address,
  onClose,
}: {
  images: string[];
  address: string;
  onClose: () => void;
}) {
  const [idx, setIdx] = useState(0);

  // ESC to close, ←/→ to navigate.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") setIdx((i) => (i + 1) % images.length);
      if (e.key === "ArrowLeft") setIdx((i) => (i - 1 + images.length) % images.length);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [images.length, onClose]);

  if (images.length === 0) return null;

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/85 p-4"
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[90vh] w-full max-w-5xl flex-col gap-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between text-white">
          <div className="truncate text-sm font-medium">
            {address} · {idx + 1} / {images.length}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid h-9 w-9 place-items-center rounded-full bg-white/10 hover:bg-white/20"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="relative flex h-[70vh] items-center justify-center overflow-hidden rounded-2xl bg-black">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={images[idx]}
            alt={`Image ${idx + 1}`}
            className="max-h-full max-w-full object-contain"
          />

          {images.length > 1 && (
            <>
              <button
                type="button"
                onClick={() => setIdx((i) => (i - 1 + images.length) % images.length)}
                className="absolute left-3 top-1/2 grid h-10 w-10 -translate-y-1/2 place-items-center rounded-full bg-white/15 text-white hover:bg-white/30"
                aria-label="Previous image"
              >
                <ChevronLeft className="h-6 w-6" />
              </button>
              <button
                type="button"
                onClick={() => setIdx((i) => (i + 1) % images.length)}
                className="absolute right-3 top-1/2 grid h-10 w-10 -translate-y-1/2 place-items-center rounded-full bg-white/15 text-white hover:bg-white/30"
                aria-label="Next image"
              >
                <ChevronRight className="h-6 w-6" />
              </button>
            </>
          )}
        </div>

        {/* Thumbnails strip */}
        <div className="flex gap-2 overflow-x-auto pb-1">
          {images.map((src, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setIdx(i)}
              className={cn(
                "h-14 w-20 shrink-0 overflow-hidden rounded-md border-2 transition",
                i === idx ? "border-[var(--color-brand-400)]" : "border-transparent opacity-70 hover:opacity-100",
              )}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={src} alt="" className="h-full w-full object-cover" loading="lazy" />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Cell renderers ───────────────────────────────────────────────
function renderCell(p: PropertiesTableRow, key: keyof PropertiesTableRow) {
  const v = p[key];
  if (v === null || v === undefined || v === "")
    return <span className="text-[var(--muted-foreground)]">—</span>;

  if (key === "email_status") return <StatusChip status={String(v)} />;
  if (key === "scrape_date" || key === "sheet_tab" || key === "listed_since")
    return <span className="text-xs text-[var(--muted-foreground)]">{String(v)}</span>;
  if (key === "address") return <span className="font-medium">{String(v)}</span>;
  if (key === "agency_email") {
    const email = String(v);
    return (
      <a href={`mailto:${email}`} className="text-[var(--color-brand-600)] hover:underline">
        {email}
      </a>
    );
  }
  if (key === "agency_website") {
    const href = String(v);
    return (
      <a
        href={href.startsWith("http") ? href : `https://${href}`}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-[var(--color-brand-600)] hover:underline"
      >
        <span className="max-w-[160px] truncate">{href.replace(/^https?:\/\//, "")}</span>
        <ExternalLink className="h-3 w-3 shrink-0" />
      </a>
    );
  }
  if (key === "agency_phone") {
    return (
      <a href={`tel:${String(v)}`} className="text-[var(--color-brand-600)] hover:underline">
        {String(v)}
      </a>
    );
  }
  if (key === "description") {
    return (
      <span
        className="line-clamp-2 max-w-[260px] text-xs text-[var(--muted-foreground)]"
        title={String(v)}
      >
        {String(v)}
      </span>
    );
  }
  return <span>{String(v)}</span>;
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

// Unused but keeps tree-shaker happy if removed elsewhere.
void Image;

// Re-export for callers.
export type { Property };
