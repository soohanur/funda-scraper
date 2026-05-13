/**
 * Page container — spec mandate "Pages must NOT have heading/paragraph at top —
 * direct to content". So this is just consistent padding + max-width, no titles.
 */
export function PageContainer({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto w-full max-w-[1600px] p-6 md:p-8">{children}</div>;
}
