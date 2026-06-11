import { AppNavList } from "@/components/app-nav";
import { BRAND_NAME } from "@/lib/brand";

export function AppSidebar() {
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-card/50 md:flex">
      <div className="flex h-14 items-center gap-2.5 border-b border-border px-5">
        <div className="h-6 w-6 rounded-md gradient-brand" />
        <span className="text-sm font-semibold tracking-tight">{BRAND_NAME}</span>
      </div>
      <AppNavList />
    </aside>
  );
}
