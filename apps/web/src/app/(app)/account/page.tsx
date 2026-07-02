"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api/client";

const INPUT =
  "h-10 w-full rounded-md border border-input bg-transparent px-3 text-sm outline-none focus:ring-2 focus:ring-ring";

export default function AccountPage() {
  const router = useRouter();

  const [cur, setCur] = useState("");
  const [np, setNp] = useState("");
  const [cf, setCf] = useState("");
  const [pwBusy, setPwBusy] = useState(false);
  const [pwMsg, setPwMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const [delOpen, setDelOpen] = useState(false);
  const [delPw, setDelPw] = useState("");
  const [delBusy, setDelBusy] = useState(false);
  const [delErr, setDelErr] = useState<string | null>(null);

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    if (np !== cf) {
      setPwMsg({ ok: false, text: "New passwords don't match." });
      return;
    }
    setPwBusy(true);
    setPwMsg(null);
    try {
      await api.changePassword(cur, np);
      setCur("");
      setNp("");
      setCf("");
      setPwMsg({ ok: true, text: "Password changed." });
    } catch (err) {
      setPwMsg({ ok: false, text: err instanceof ApiError ? err.message : "Could not change password." });
    } finally {
      setPwBusy(false);
    }
  }

  async function deleteAccount(event: FormEvent) {
    event.preventDefault();
    setDelBusy(true);
    setDelErr(null);
    try {
      await api.deleteAccount(delPw);
      router.replace("/login");
      router.refresh();
    } catch (err) {
      setDelErr(err instanceof ApiError ? err.message : "Could not delete account.");
      setDelBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-8 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Account</h1>
        <p className="text-sm text-muted-foreground">Manage your password and account.</p>
      </div>

      <section className="rounded-xl border border-border bg-card p-6">
        <h2 className="font-medium">Change password</h2>
        <form onSubmit={changePassword} className="mt-4 space-y-4">
          <div className="space-y-1">
            <label htmlFor="cur" className="text-sm">Current password</label>
            <input id="cur" type="password" required autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} className={INPUT} />
          </div>
          <div className="space-y-1">
            <label htmlFor="np" className="text-sm">New password</label>
            <input id="np" type="password" required minLength={8} autoComplete="new-password" value={np} onChange={(e) => setNp(e.target.value)} className={INPUT} />
          </div>
          <div className="space-y-1">
            <label htmlFor="cf" className="text-sm">Confirm new password</label>
            <input id="cf" type="password" required minLength={8} autoComplete="new-password" value={cf} onChange={(e) => setCf(e.target.value)} className={INPUT} />
          </div>
          {pwMsg ? (
            <p className={`text-sm ${pwMsg.ok ? "text-profit" : "text-loss"}`}>{pwMsg.text}</p>
          ) : null}
          <Button type="submit" disabled={pwBusy}>
            {pwBusy ? "Updating…" : "Update password"}
          </Button>
        </form>
      </section>

      <section className="rounded-xl border border-loss/30 bg-card p-6">
        <h2 className="font-medium text-loss">Danger zone</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Deactivate your account and sign out. You won&apos;t be able to sign in again.
        </p>
        {!delOpen ? (
          <button
            type="button"
            onClick={() => setDelOpen(true)}
            className="mt-3 rounded-md border border-loss/40 px-4 py-2 text-sm font-medium text-loss hover:bg-loss/10"
          >
            Delete account
          </button>
        ) : (
          <form onSubmit={deleteAccount} className="mt-3 space-y-3">
            <div className="space-y-1">
              <label htmlFor="delpw" className="text-sm">Confirm your password</label>
              <input id="delpw" type="password" required autoComplete="current-password" value={delPw} onChange={(e) => setDelPw(e.target.value)} className={INPUT} />
            </div>
            {delErr ? <p className="text-sm text-loss">{delErr}</p> : null}
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={delBusy}
                className="rounded-md bg-loss px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-60"
              >
                {delBusy ? "Deleting…" : "Permanently delete"}
              </button>
              <Button type="button" variant="outline" onClick={() => { setDelOpen(false); setDelPw(""); }}>
                Cancel
              </Button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
