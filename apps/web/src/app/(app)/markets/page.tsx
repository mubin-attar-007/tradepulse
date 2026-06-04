"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { LivePrice } from "@/components/live-price";
import { api } from "@/lib/api/client";

export default function MarketsPage() {
  const { data: instruments, isLoading } = useQuery({
    queryKey: ["instruments"],
    queryFn: () => api.instruments(),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Markets</h1>
      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-card text-left text-muted-foreground">
            <tr>
              <th className="px-4 py-2 font-medium">Symbol</th>
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">Class</th>
              <th className="px-4 py-2 text-right font-medium">Last</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td className="px-4 py-3 text-muted-foreground" colSpan={5}>
                  Loading…
                </td>
              </tr>
            ) : (
              (instruments ?? []).map((instrument) => (
                <tr key={instrument.id} className="border-t border-border">
                  <td className="px-4 py-2 font-medium tabular-nums">{instrument.symbol}</td>
                  <td className="px-4 py-2 text-muted-foreground">{instrument.name}</td>
                  <td className="px-4 py-2 text-muted-foreground">{instrument.asset_class}</td>
                  <td className="px-4 py-2 text-right">
                    <LivePrice instrumentId={instrument.id} />
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Link className="text-primary hover:underline" href={`/chart/${instrument.id}`}>
                      Open chart →
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
