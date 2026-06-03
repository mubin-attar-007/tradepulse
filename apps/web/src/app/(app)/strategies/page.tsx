"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api/client";

const EXAMPLE = JSON.stringify(
  {
    spec_version: "1.0",
    name: "BTC EMA cross",
    universe: ["BTC/USD"],
    timeframe: "5m",
    indicators: [
      { id: "ema_fast", type: "EMA", params: { period: 20 } },
      { id: "ema_slow", type: "EMA", params: { period: 50 } },
    ],
    entry_long: {
      type: "compare",
      left: { kind: "indicator", ref: "ema_fast" },
      op: "cross_above",
      right: { kind: "indicator", ref: "ema_slow" },
    },
    exit: { stop_loss_pct: 0.02, take_profit_pct: 0.03, time_exit_bars: 24 },
    sizing: { method: "percent_equity", value: 0.5 },
    risk: { max_position_pct: 1.0, max_open_positions: 1 },
  },
  null,
  2,
);

export default function StrategiesPage() {
  const { data: strategies, refetch } = useQuery({
    queryKey: ["strategies"],
    queryFn: () => api.strategies(),
  });

  const [json, setJson] = useState(EXAMPLE);
  const [prompt, setPrompt] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function generate() {
    if (prompt.trim().length < 3) return;
    setBusy(true);
    setMsg(null);
    try {
      const resp = await api.aiStrategy(prompt);
      setJson(JSON.stringify(resp.spec, null, 2));
      setMsg({ kind: "ok", text: `Generated via ${resp.provider} — review and create.` });
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof ApiError ? err.message : "AI unavailable." });
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    setBusy(true);
    setMsg(null);
    try {
      const spec = JSON.parse(json);
      const detail = await api.createStrategy(spec);
      setMsg({ kind: "ok", text: `Created "${detail.strategy.name}".` });
      await refetch();
    } catch (err) {
      if (err instanceof SyntaxError) setMsg({ kind: "err", text: "Invalid JSON." });
      else setMsg({ kind: "err", text: err instanceof ApiError ? err.message : "Create failed." });
    } finally {
      setBusy(false);
    }
  }

  async function deploy(id: string) {
    setMsg(null);
    try {
      await api.deployPaper(id);
      setMsg({ kind: "ok", text: "Deployed to paper trading." });
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof ApiError ? err.message : "Deploy failed." });
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Strategies</h1>

      <div className="space-y-3 rounded-lg border border-border bg-card p-4">
        <div className="flex gap-2">
          <input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe a strategy in plain English (AI fills the spec below)…"
            className="h-9 flex-1 rounded-md border border-input bg-transparent px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
          <Button variant="outline" size="sm" onClick={generate} disabled={busy}>
            {busy ? "…" : "Generate with AI"}
          </Button>
        </div>
        <textarea
          value={json}
          onChange={(e) => setJson(e.target.value)}
          spellCheck={false}
          rows={16}
          className="w-full rounded-md border border-input bg-transparent p-3 font-mono text-xs outline-none focus:ring-2 focus:ring-ring"
        />
        <div className="flex items-center gap-3">
          <Button onClick={create} disabled={busy}>
            Create strategy
          </Button>
          {msg ? (
            <span className={`text-sm ${msg.kind === "ok" ? "text-profit" : "text-loss"}`}>
              {msg.text}
            </span>
          ) : null}
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-card text-left text-muted-foreground">
            <tr>
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Version</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {!strategies?.length ? (
              <tr>
                <td className="px-4 py-3 text-muted-foreground" colSpan={4}>
                  No strategies yet — create one above.
                </td>
              </tr>
            ) : (
              strategies.map((s) => (
                <tr key={s.id} className="border-t border-border">
                  <td className="px-4 py-2 font-medium">{s.name}</td>
                  <td className="px-4 py-2 text-muted-foreground">{s.status}</td>
                  <td className="px-4 py-2 tabular-nums">{s.latest_version}</td>
                  <td className="px-4 py-2 text-right">
                    <Link className="mr-4 text-primary hover:underline" href="/backtests">
                      Backtest
                    </Link>
                    <button
                      type="button"
                      onClick={() => deploy(s.id)}
                      className="text-primary hover:underline"
                    >
                      Deploy to paper
                    </button>
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
