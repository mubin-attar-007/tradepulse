"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
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
      <Link
        href="/account"
        className="text-sm text-muted-foreground hover:text-foreground"
        title={user?.email ?? undefined}
      >
        {user?.email ?? "…"}
      </Link>
      <Button variant="outline" size="sm" onClick={logout}>
        Log out
      </Button>
    </div>
  );
}
