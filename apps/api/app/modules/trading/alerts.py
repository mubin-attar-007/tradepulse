"""Snapshot-diff alerting for paper sessions.

A paper session is advanced by re-running the SAME engine over the whole session
window every ~30s (see ``PaperService.run_session``), so each snapshot is a full,
deterministic recomputation — the same fills and RiskEvents reappear every run.
To alert exactly once per real event we:

  1. enumerate the events implied by the latest snapshot (each completed trade →
     an ``entry`` + an ``exit`` event; an open position → an ``entry`` event; each
     RiskEvent → a ``risk_event``), each with a STABLE ``dedup_key``;
  2. skip any dedup_key already persisted as an Alert row for this session
     (the idempotency guard — the cron runs cross-owner every 30s and must not
     double-fire); the DB unique constraint on (session_id, dedup_key) is the
     hard backstop even under a race;
  3. persist an Alert row per genuinely-new event and dispatch one email via
     ``send_email`` (a graceful no-op when SMTP is unset).
"""

from __future__ import annotations

from typing import Any

from app.core.email import send_email
from app.core.logging import get_logger
from app.modules.trading.models import Alert, PaperSession
from app.modules.trading.repository import AlertRepository

logger = get_logger("paper")


def _events_from_snapshot(symbol: str, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a snapshot into (kind, dedup_key, detail) event dicts."""
    events: list[dict[str, Any]] = []

    for trade in snapshot.get("trades", []):
        entry_ts = trade.get("entry_ts")
        exit_ts = trade.get("exit_ts")
        if entry_ts:
            events.append(
                {
                    "kind": "entry",
                    "dedup_key": f"entry:{entry_ts}",
                    "detail": {
                        "ts": entry_ts,
                        "side": trade.get("side"),
                        "qty": trade.get("qty"),
                        "price": trade.get("entry_price"),
                    },
                }
            )
        if exit_ts:
            events.append(
                {
                    "kind": "exit",
                    "dedup_key": f"exit:{exit_ts}",
                    "detail": {
                        "ts": exit_ts,
                        "qty": trade.get("qty"),
                        "price": trade.get("exit_price"),
                        "pnl": trade.get("pnl"),
                        "reason": trade.get("exit_reason"),
                    },
                }
            )

    # A still-open position is an entry that hasn't produced a trade row yet.
    open_pos = snapshot.get("open_position")
    if open_pos:
        entry_ts = open_pos.get("entry_ts")
        if entry_ts:
            events.append(
                {
                    "kind": "entry",
                    "dedup_key": f"entry:{entry_ts}",
                    "detail": {
                        "ts": entry_ts,
                        "side": "long",
                        "qty": open_pos.get("qty"),
                        "price": open_pos.get("entry_price"),
                        "open": True,
                    },
                }
            )

    for ev in snapshot.get("risk_events", []):
        ts = ev.get("ts")
        kind = ev.get("kind")
        events.append(
            {
                "kind": "risk_event",
                "dedup_key": f"risk:{kind}:{ts}",
                "detail": {"ts": ts, "kind": kind, "detail": ev.get("detail")},
            }
        )

    return events


def _email_body(symbol: str, kind: str, detail: dict[str, Any]) -> tuple[str, str]:
    if kind == "entry":
        subject = f"TradePulse paper alert: entry {symbol}"
        body = (
            f"Paper session entry on {symbol}.\n"
            f"qty={detail.get('qty')} @ {detail.get('price')} ({detail.get('ts')})\n\n"
            "This is a simulated paper-trading fill, not a real order."
        )
    elif kind == "exit":
        subject = f"TradePulse paper alert: exit {symbol}"
        body = (
            f"Paper session exit on {symbol} ({detail.get('reason')}).\n"
            f"qty={detail.get('qty')} @ {detail.get('price')} | pnl={detail.get('pnl')} "
            f"({detail.get('ts')})\n\n"
            "This is a simulated paper-trading fill, not a real order."
        )
    else:  # risk_event
        subject = f"TradePulse risk alert: {detail.get('kind')} {symbol}"
        body = (
            f"Risk control fired on {symbol}: {detail.get('kind')} "
            f"({detail.get('detail')}) at {detail.get('ts')}.\n\n"
            "This is a paper-trading risk event."
        )
    return subject, body


async def dispatch_snapshot_alerts(
    repo: AlertRepository,
    paper: PaperSession,
    snapshot: dict[str, Any],
    *,
    email_to: str | None,
) -> int:
    """Persist an Alert row + email for each genuinely-new event in ``snapshot``.

    Idempotent: keys off already-persisted dedup_keys and de-dups within the batch,
    so the 30s cron never re-fires. Returns the number of new alerts emitted.

    Durability discipline (B1 — never re-spam): the Alert rows are COMMITTED before
    any email leaves the process. Email is a real-world side effect that cannot be
    rolled back, so if we sent first and a later exception rolled back the dedup
    rows, the next 30s tick would re-email everything. By committing the dedup rows
    up front, an email failure (or any later crash) leaves the row persisted and the
    event is never re-sent; the ``(session_id, dedup_key)`` unique constraint remains
    the hard backstop under a race.
    """
    events = _events_from_snapshot(paper.symbol, snapshot)
    if not events:
        return 0

    seen = await repo.existing_dedup_keys(paper.id)
    # Persist the new Alert rows first, remembering what to email once they're durable.
    pending: list[tuple[str, dict[str, Any]]] = []
    for ev in events:
        key = ev["dedup_key"]
        if key in seen:
            continue
        seen.add(key)  # guard against duplicate keys within this same snapshot batch
        alert = Alert(
            session_id=paper.id,
            kind=ev["kind"],
            symbol=paper.symbol,
            dedup_key=key,
            detail=ev["detail"],
        )
        await repo.add(alert)
        pending.append((ev["kind"], ev["detail"]))

    if not pending:
        return 0

    # Commit the dedup rows BEFORE sending any email — the idempotency guard is only
    # durable once flushed to the DB. Only after this can send_email safely fire.
    await repo.session.commit()

    if email_to:
        for kind, detail in pending:
            subject, body = _email_body(paper.symbol, kind, detail)
            await send_email(email_to, subject, body)

    logger.info("paper_alerts_dispatched", session_id=str(paper.id), count=len(pending))
    return len(pending)
