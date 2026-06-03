"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";

export function UserMenu() {
  const router = useRouter();
  const { data: user } = useQuery({ queryKey: ["me"], queryFn: api.me });

  async function logout() {
    try {
      await api.logout();
    } finally {
      router.replace("/login");
      router.refresh();
    }
  }

  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-muted-foreground">{user?.email ?? "…"}</span>
      <Button variant="outline" size="sm" onClick={logout}>
        Log out
      </Button>
    </div>
  );
}
