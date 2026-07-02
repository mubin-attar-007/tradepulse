"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api/client";
import { BRAND_NAME } from "@/lib/brand";

const INPUT =
  "h-10 w-full rounded-md border border-input bg-transparent px-3 text-sm outline-none focus:ring-2 focus:ring-ring";

function ResetForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (pw !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.passwordResetConfirm(token, pw);
      setDone(true);
      setTimeout(() => router.replace("/login"), 1500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-8">
        <h1 className="text-xl font-semibold">{BRAND_NAME}</h1>
        <p className="mt-1 text-sm text-muted-foreground">Set a new password</p>
        {!token ? (
          <p className="mt-6 text-sm text-muted-foreground">
            This reset link is invalid or incomplete.{" "}
            <Link href="/forgot-password" className="text-foreground hover:underline">
              Request a new one
            </Link>
            .
          </p>
        ) : done ? (
          <p className="mt-6 text-sm text-muted-foreground">
            Password reset — taking you to sign in…
          </p>
        ) : (
          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <div className="space-y-1">
              <label htmlFor="pw" className="text-sm">
                New password
              </label>
              <input
                id="pw"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={pw}
                onChange={(e) => setPw(e.target.value)}
                className={INPUT}
              />
            </div>
            <div className="space-y-1">
              <label htmlFor="pw2" className="text-sm">
                Confirm new password
              </label>
              <input
                id="pw2"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className={INPUT}
              />
            </div>
            {error ? <p className="text-sm text-loss">{error}</p> : null}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Resetting…" : "Reset password"}
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetForm />
    </Suspense>
  );
}
