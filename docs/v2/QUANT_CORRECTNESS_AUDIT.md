# Quant Correctness Audit — Backtesting Engine, Indicators, Metrics, DSL

**Date:** 2026-08-21
**Scope:** `apps/api/app/modules/backtesting/**`, `apps/api/app/modules/indicators/compute.py`,
`apps/api/app/modules/strategies/spec.py`, `apps/api/app/modules/research/{signal,reference_backtest,public_router}.py`,
`apps/api/tests/test_backtest*.py`
**Audit target:** commit `8b82368` **plus the uncommitted working tree**. This distinction is
load-bearing: `git status` shows modified-but-uncommitted files across `backtesting/`,
`indicators/` (new, untracked), `strategies/spec.py`, `market_data/repository.py`, and a
rename of `market_data/{public_router,reference_backtest,signal}.py` into a new `research/`
package. Every line reference below is to the **working tree**, which is what a v2 branch
would build on. Where a line number is quoted against committed `HEAD` instead, it is
labelled as such.

---

## 1. Scope and method

Each file in scope was read end to end. Every behavioural claim was then verified by
importing the engine in-process from the repository venv (`.venv/Scripts/python.exe`) and
running hand-built bar sequences — no database, no network, no pytest run, no repository
files modified. Claims are therefore one of two kinds, and are never mixed:

- **Code citation** — a `file:line` reference to the working tree.
- **Reproduced result** — a number printed by an in-process probe, quoted verbatim.

Nothing in this document reports the outcome of a command that was not executed. Test-suite
results, coverage percentages, and static-gate outcomes are deliberately absent here; they
belong to the lead's baseline record referenced in the final section.

### 1.1 Headline

The engine is in materially better shape than a first reading of the module layout suggests.
The architectural decisions are sound and, importantly, *enforced* rather than decorative:
one engine implementation shared by backtests, paper trading, live signals and the public
reference; Decimal money end to end; decisions on closed bars with next-open fills; risk
limits that actually block trades; and a spec validator that now **refuses** capabilities the
engine cannot execute instead of silently ignoring them.

A large class of previously-reported quantitative defects has been remediated in the working
tree and each fix was re-verified here rather than taken on trust (§2.2). What remains is a
tail of **medium- and low-severity** issues: one genuine mis-modelled order type, one residual
indicator window-dependency, several silently-degrading or silently-succeeding paths, and a
correctness test suite that has not kept pace with the engine it guards. **No high-severity
quantitative defect survived verification.** That is a real result and it is stated plainly
rather than padded.

---

## 2. Invariants that hold

These are the properties a change to this module must not break. Each is stated with the
evidence that establishes it.

### 2.1 Structural invariants

| # | Invariant | Evidence |
|---|---|---|
| I-1 | **Decisions are made only on closed bars; market orders fill at the next bar's open.** The decision branch is guarded by `if i < len(bars) - 1`, so the final bar never generates an order there is no bar to fill on. | `apps/api/app/modules/backtesting/engine.py:314-330`; fill sites `engine.py:226` (exit) and `engine.py:230-233` (entry) |
| I-2 | **Condition evaluation reads only indices ≤ i.** `evaluate` touches `i` and `i-1` only, and `i-1` is guarded. | `apps/api/app/modules/backtesting/compute.py:287-298` |
| I-3 | **Indicators are causal and warm-up is masked.** Every construct is backward-looking; `min_periods` emits NaN rather than a fabricated number. | `apps/api/app/modules/indicators/compute.py:1-12, 157-216` |
| I-4 | **A NaN operand cannot fire a trade.** `_compare` returns `False` on NaN before any operator is applied, and cross operators additionally guard the previous bar. | `apps/api/app/modules/backtesting/compute.py:265-284` |
| I-5 | **ATR position sizing reads the decision bar, not the fill bar.** Verified by perturbing *only* bar 5's high/low (open and close held identical) with ATR sizing active: `equity[5]` and entry `qty` were byte-identical across the two runs (`214.2857142857142704081632653` in both). | `engine.py:234-240` |
| I-6 | **Trailing stops fill at the trail, not at the open.** The level live at the open is captured *before* the ratchet and only that level can classify a bar as a gap-through. Verified: entry 102, bar `o=102 h=130 l=101`, 10% trail → booked `exit=117.0`, `reason=trailing`. | `engine.py:269-291` |
| I-7 | **Stop takes precedence over target on an ambiguous bar** (`elif`), the conservative tie-break. | `engine.py:285-294` |
| I-8 | **A pending exit at the open pre-empts that bar's bracket.** `close_position` clears `in_pos`, so step 3 is skipped — correct market-on-open semantics. | `engine.py:212-213`, `engine.py:225-227` |
| I-9 | **Risk halts block new entries only; exits always evaluate.** The `if/elif` at `engine.py:316`/`324` is mutually exclusive on `in_pos`, so a halt can never swallow exit evaluation. | `engine.py:314-330` |
| I-10 | **Money is Decimal end to end inside the engine.** Floats appear only in indicator math and display metrics, and the two never mix. | `apps/api/app/modules/backtesting/types.py:1-2`; `apps/api/app/modules/indicators/compute.py:9-11` |
| I-11 | **No leverage, no shorting, no margin, no negative cash.** Sizing fractions are capped at 1 (`spec.py:129-130`), `max_position_pct ≤ 1` (`spec.py:138`), and a commission-inclusive cash clamp bounds the fill. Probe with `fixed_units=100000` against 100k equity: minimum equity over the run was exactly `100000`, never negative. | `engine.py:241-253` |
| I-12 | **Commission is charged on both legs and PnL is net of both.** `entry_gross = notional + commission`; `pnl = (proceeds - exit_commission) - entry_gross`. | `engine.py:247-259`, `engine.py:182-187` |
| I-13 | **One engine, no duplicated fill math.** Paper trading, live signals and the public reference all call `engine.run` or the shared `entry_fill` / `stop_from_fill` / `target_from_fill` / `size_for_entry` helpers. This is the single best structural decision in the module. | `apps/api/app/modules/trading/service.py:81-82`; `apps/api/app/modules/research/signal.py:105-113`; `apps/api/app/modules/research/reference_backtest.py:211` |
| I-14 | **The instrument calendar reaches every calendar-sensitive computation.** `calendar` flows from the instrument into indicator computation, the time-of-day window, and metric annualization. | `engine.py:115-132, 147-151, 348`; `apps/api/app/modules/backtesting/service.py:141` |
| I-15 | **Spec validation is strong.** Indicator id uniqueness, operand ref/output resolution, per-indicator parameter ranges, `extra="forbid"` on every model, and a mandatory exit mechanism. | `apps/api/app/modules/strategies/spec.py:107-118, 166-204`; `apps/api/app/modules/indicators/catalog.py:69-80` |
| I-16 | **The spec refuses what the engine cannot execute.** `_reject_unsupported` raises on `entry_short`, `len(universe) > 1`, `max_open_positions != 1`, and `risk_per_trade` without a stop — the four fields that were previously accepted and silently dropped. | `spec.py:206-245` |
| I-17 | **Undefined is not zero.** Metrics return `None` for undefined or below-floor values, and `BacktestResult.metrics` is typed `dict[str, float | None]`. | `apps/api/app/modules/backtesting/metrics.py:101-122`; `types.py:75-77` |
| I-18 | **Extrapolating statistics are gated on sample size and the gate is explained.** Verified on a 6-bar run: `sharpe=None sortino=None cagr=None calmar=None`, with `sample_size_notes` producing a human-readable reason. | `metrics.py:49-54, 156-178, 208-231` |
| I-19 | **Annualization is calendar-aware.** Verified: `periods_per_year("1h", "XNYS") = 1638.0` vs `("1h", "24x7") = 8760.0`; `("1d","XNYS") = 252.0` vs `365.0`. | `metrics.py:44-70` |
| I-20 | **CAGR uses elapsed wall-clock, not bar count**, so holidays and weekends are handled exactly rather than approximated. | `metrics.py:132-133, 168-175` |
| I-21 | **RSI is 100 with no losses and 0 with no gains.** Verified on monotonic series: rising → `100.0` at indices 14, 20, 39; falling → `0.0`. | `apps/api/app/modules/indicators/compute.py:125-139` |
| I-22 | **RSI/ATR use Wilder's SMA-seeded RMA**, matching TA-Lib/TradingView rather than `ewm(adjust=False)` seeded from the first observation. | `apps/api/app/modules/indicators/compute.py:92-114, 142-154` |
| I-23 | **The data fingerprint is content-addressed over every bar.** Verified: changing only an interior bar's high changes the digest. | `apps/api/app/modules/backtesting/service.py:112-118` |
| I-24 | **The execution configuration is persisted with the result**, so a frictionless run is distinguishable from a costed one in the stored artifact. | `types.py:14-37`; `apps/api/app/modules/backtesting/snapshot.py:193` |
| I-25 | **The closed-bar contract is enforced at the data layer.** `get_bars` drops any bucket whose interval has not fully elapsed and widens the scan so the first bucket is never built from a partial slice of itself. | `apps/api/app/modules/market_data/repository.py:156-186, 219-238` |
| I-26 | **Public surfaces strip annualized metrics server-side.** A genuinely strong mitigation for small-sample statistics on crawlable pages — though see QC-04 for the one key it misses. | `apps/api/app/modules/research/public_router.py:47-52` |
| I-27 | **The engine is deterministic and pure.** No RNG, no clock read, no I/O inside `run`. | `engine.py:115-360` |

### 2.2 Remediated since the pre-v2 baseline

The following were real defects at committed `HEAD` and are **fixed in the working tree**.
They are recorded because the fixes are load-bearing and must not regress — each was
re-verified in-process, not accepted on the strength of a code comment.

| Was | Now | Verification |
|---|---|---|
| Trailing exit booked at the bar's open (`HEAD` `engine.py:239`: `fill = o if o <= stop_price else stop_price`, tested *after* the ratchet) | Pre-ratchet level captured as `stop_at_open` and used for the gap test | Booked `exit=117.0` where the trail was 117; previously would have booked 102 |
| ATR sizing read the fill bar's own high/low | Reads `atr_arr[i-1]`, the decision bar | Perturbing only bar 5's H/L left `equity[5]` and `qty` identical |
| `entry_short`, `universe[1:]`, `max_open_positions > 1` accepted then silently ignored | Rejected at validation with an engine-capability message | `spec.py:225-245` |
| Calendar-blind annualization (365/8760 regardless of instrument) | `periods_per_year(timeframe, calendar)` | `1h` XNYS `1638.0` vs 24x7 `8760.0` |
| No sample-size guard (Sharpe in the thousands on tiny runs) | `None` below documented floors, with notes | 6-bar run returns `None` for all four extrapolating metrics |
| Sortino used the standard deviation of losses about their own mean | Root-mean-square shortfall below target over all observations | `metrics.py:73-84` |
| `profit_factor` returned gross dollar winnings when there were no losses | Returns `None` | `metrics.py:188` |
| RSI returned NaN when there were no losses, silently disabling upside momentum rules | Returns 100 (and 0 for no gains) | Monotonic-series probe |
| Non-Wilder RSI/ATR seeding | SMA-seeded Wilder RMA | `indicators/compute.py:92-114` |
| VWAP cumulative from the first loaded bar | Session-anchored via `groupby(session).cumsum()` | Complete sessions now window-independent — see QC-03 for the residual |
| `data_fingerprint` hashed only count + endpoints | Hashes every bar's OHLCV tuple | Interior-high change alters the digest |
| `ExecutionConfig` absent from the persisted artifact | Serialized via `as_dict()` with `COST_MODEL_VERSION` | `snapshot.py:193` |
| Trailing exits indistinguishable from fixed-stop exits | `exit_reason="trailing"` emitted | Probe returned `reason=trailing` |
| `time_of_day.timezone` accepted and ignored (window matched in UTC) | Converted to exchange-local before comparison | `engine.py:147-151, 318-321` |
| Aggregated timeframes returned a still-forming trailing bucket | `HAVING` clause drops incomplete buckets | `repository.py:230-236` |
| No exposure / turnover / Calmar / holding-period / expectancy metrics | All present | `metrics.py:101-122, 180-203` |

---

## 3. Defects

Severity reflects impact on the correctness of a reported number, weighted by how silently
the failure occurs. **No high-severity defect survived verification**; the highest remaining
band is medium.

### QC-01 — Take-profit exits are charged adverse slippage (MEDIUM)

**Where:** `apps/api/app/modules/backtesting/engine.py:292-294`, via `sell_fill` at `engine.py:177-178`

**What happens.** A take-profit is a limit order, but its fill is passed through the same
adverse-slippage function as a market order. Reproduced with default costs: entry filled at
`101.0101`, the computed target level was `106.060605`, and the engine booked
`exit_price=106.0499989395` — `0.0106060605` worse than the limit, exactly the 1 bp
slippage haircut.

**Why it matters.** A limit order never fills worse than its limit; that is what makes it a
limit order. The error is one basis point per profitable exit and is uniformly pessimistic,
so it understates every take-profit strategy and biases strategy ranking against
target-based exits relative to stop-based ones. It also breaks the module's own
shared-math claim: `research/signal.py:109` advertises `target_from_fill(...)` to the user
on the signal card while the engine books a different number, so the signal card and the
backtest disagree by 1 bp on the same bracket.

**Fix.** Apply slippage only to market-type fills — the open fills at `engine.py:226` and
`engine.py:233`, the stop fill at `engine.py:291`, and the EOD flatten at `engine.py:337`.
Keep the gap-through improvement on targets (a bar that gaps above the limit fills at the
open, `engine.py:293`) but without the adverse nudge.

---

### QC-02 — `time_exit_bars = N` holds the position for N+1 bars (MEDIUM)

**Where:** `apps/api/app/modules/backtesting/engine.py:296-298`

**What happens.** The exit is *armed* when `(i - entry_i) >= time_exit_bars` and then fills
at the following bar's open, so the position is closed at `entry_i + N + 1`. Reproduced with
`time_exit_bars=1`: entry `2024-01-04`, exit `2024-01-06`, `bars_held=2`.

**Why it matters.** The field name states a holding period and the AI copilot is told it is
one. Every time-exit strategy therefore holds 1 bar longer than authored — a systematic
off-by-one in the single parameter that controls exposure duration, compounding with
`avg_holding_bars` and `exposure` in the metrics block. It is silent: nothing in the result
reports the realised holding period against the requested one.

**Fix.** Either arm at `>= time_exit_bars - 1` so `N` means N bars held, or state the
semantics precisely in `spec.py:104` and the AI prompt: *"exit is submitted after N bars have
elapsed and fills at the following open (N+1 bars held)."* Pick one and add a fixture
asserting the exact exit index.

---

### QC-03 — VWAP's leading partial session is still anchored to the first loaded bar (MEDIUM)

**Where:** `apps/api/app/modules/indicators/compute.py:189-193`

**What happens.** VWAP is now session-anchored via `groupby(session).cumsum()`, which
correctly resets at every session boundary *present in the loaded window*. But the first
session in the window is only ever a partial one when the query starts mid-session, and its
cumulative sums begin at the first loaded bar rather than at the true session open.

Reproduced over three UTC days of minute bars, comparing the full window against the same
data loaded from an offset of 700 minutes (mid-day-1):

| Segment | Values agree? | Sample |
|---|---|---|
| Leading **partial** session (day 1 after the offset) | **No** | full `105.0` vs windowed `105.046512` at index 1000 |
| Later **complete** sessions (days 2-3) | Yes | full `105.0` vs windowed `105.0` at index 2000 |

**Why it matters.** The fix eliminated the unbounded cross-session drift, which was the
larger half of the problem, and every complete session is now window-independent. The
residual is bounded but real: any bar in the first partial session gets a VWAP that depends
on the query start date, so two runs of one strategy over overlapping windows are still not
comparable over that leading segment. This is a hidden window dependency, not look-ahead, so
no canary can detect it — which is precisely what makes it worth an explicit test.

**Fix.** Mask the leading partial session to NaN when the first loaded bar is not the
session's first bar (the honest option, consistent with how warm-up is already handled), or
widen the scan to the containing session boundary the way `get_bars` already widens to
`floor_to_bucket(start)` (`repository.py:242-244`). Add a test asserting VWAP equality on the
overlap of two windows.

---

### QC-04 — `calmar` bypasses the public annualized-metric stripper (MEDIUM)

**Where:** `apps/api/app/modules/research/public_router.py:47`

**What happens.** `_ANNUALIZED_METRICS = frozenset({"cagr", "sharpe", "sortino"})` is a
hardcoded list that was not updated when metrics `2.0.0` added `calmar`. Calmar is
`cagr / |max_drawdown|` (`metrics.py:176-178`) — an annualized ratio derived directly from
the CAGR the policy exists to withhold. Verified against the real function: passing a metrics
dict through `_public_metrics` returns keys `['calmar', 'expectancy', 'max_drawdown',
'profit_factor', 'total_return', 'turnover']` — `calmar` survives.

**Why it matters.** The stripping policy at `public_router.py:42-52` is one of the strongest
honesty mechanisms in the codebase and its rationale applies verbatim to Calmar. The leak is
in the API response from `GET /public/markets/{ticker}` (`public_router.py:175`), which is
unauthenticated and crawlable. The current public ticker page does not render the key
(`apps/web/src/app/markets/[ticker]/market-view.tsx:27` renders a fixed subset), so the
present-day user-visible exposure is nil — but the contract is wrong at the boundary, and the
next frontend change that iterates the metrics map exposes it. The track-record aggregate is
unaffected: it projects a fixed tuple that excludes Calmar (`reference_backtest.py:249`).

**Fix.** Derive the stripped set from a property of the metric rather than a literal — e.g.
declare the extrapolating keys once in `metrics.py` (`cagr`, `sharpe`, `sortino`, `calmar`)
and import that frozenset into `public_router.py`, so a new annualized metric cannot be added
without joining the policy.

---

### QC-05 — ATR sizing hardcodes a 1% risk fraction and silently degrades on a warm-up ATR (MEDIUM)

**Where:** `apps/api/app/modules/backtesting/engine.py:65-70`

**What happens.** Two distinct silent behaviours in five lines:

1. For `method="atr"`, `sizing.value` is used **only** as the ATR multiple; the risk fraction
   is the literal `Decimal("0.01")` (`engine.py:69`). Nothing in `spec.py:121-133` or the AI
   prompt says risk is fixed at 1%.
2. When ATR is NaN (warm-up) or ≤ 0, sizing falls through to `(equity * 0.01) / fill`
   (`engine.py:70`) — a 1%-of-equity *notional*, which is a different quantity in different
   units from the risk-based size the branch above computes, and unrelated to any user input.

**Why it matters.** The sibling defect in this family — `risk_per_trade` without a stop
degrading to percent-of-equity — was correctly promoted to a hard validation error
(`spec.py:241-245`). These two were not, so the same class of silent risk-profile
substitution remains on the ATR path. The warm-up fallback is the sharper of the two: it
takes a position at an arbitrary size at exactly the point in the series where volatility is
least well estimated, and emits no `RiskEvent`.

**Fix.** Add an explicit `risk_pct` field to `PositionSizing` for the ATR method (defaulting
to 0.01 preserves current behaviour) or document the fixed 1% in `spec.py` and the AI prompt.
Separately, skip the entry when the ATR is unavailable rather than substituting a notional
rule, and emit a `RiskEvent` when doing so — an ATR-sized strategy that cannot compute ATR
has no defined size.

---

### QC-06 — The insufficient-cash clamp and the zero-size drop are both silent (MEDIUM)

**Where:** `apps/api/app/modules/backtesting/engine.py:249-253`

**What happens.** When the intended notional plus commission exceeds available cash, size is
clamped to `(cash / (1 + comm)) / fill` with **no** `RiskEvent` — unlike the sibling
`max_position_pct` clamp three lines above, which does emit one (`engine.py:244-246`). If the
clamped size rounds to zero, `if size > 0` at `engine.py:253` drops the signal with no
diagnostic at all. Reproduced with `fixed_units=100000` against 100k of equity: the result
carried exactly one risk event, `('position_clamped', 'max_position_pct')`, while the cash
clamp that also fired left no trace.

**Why it matters.** The stated design principle is that risk limits are *enforced, not merely
tracked* (`engine.py:7-8`), and the risk-event stream is how enforcement becomes visible. A
strategy whose sizing is systematically truncated by available cash — the normal condition
for a strategy that compounds into a drawdown — reports a return profile shaped by a
constraint that appears nowhere in its output. The cash invariant itself is sound (I-11);
this is purely an observability gap.

**Fix.** Emit `RiskEvent(kind="cash_clamped")` and `RiskEvent(kind="signal_dropped_zero_size")`,
and extend the `RiskEvent.kind` comment at `types.py:64`. Consider quantizing the clamped size
with `ROUND_DOWN` so `notional + commission <= cash` is provable rather than merely true to
28 significant digits.

---

### QC-07 — The daily-loss halt uses a UTC day boundary while the time-of-day filter uses exchange time (MEDIUM)

**Where:** `apps/api/app/modules/backtesting/engine.py:218` versus `engine.py:318-321`

**What happens.** The time-of-day window is now correctly converted into exchange-local time
before comparison (`local = bar.ts.astimezone(tod_zone)`), but the daily-loss kill-switch
still keys its day on `bar.ts.date()` — the UTC calendar date. Both facts confirmed by
source inspection of `engine.run`.

**Why it matters.** Two session-scoped features in the same loop now disagree about what a
day is. For `XNYS` the mismatch is currently benign — UTC midnight falls after the 20:00/21:00
UTC close, so no US session is cut in half — but the two mechanisms are no longer
consistent, and the value that makes one of them correct (`_CALENDAR_ZONES`, `engine.py:33`)
is already in scope at the point the other is computed. Any calendar whose session straddles
UTC midnight silently resets the loss limit mid-session, which is the failure mode the limit
exists to prevent. On a `1d` timeframe the halt separately degenerates to "skip exactly one
entry", since every bar starts a new day.

**Fix.** Reuse the resolved zone for the day key:
`day = (bar.ts.astimezone(tod_zone) if tod_zone else bar.ts).date()`, hoisting the zone
resolution out of the `time_of_day`-conditional at `engine.py:147-151` so it is available
whenever a calendar is known. Document the `1d` degeneracy in `spec.py:140`.

---

### QC-08 — Intrabar path is unmodelled and unflagged (MEDIUM)

**Where:** `apps/api/app/modules/backtesting/engine.py:269-294`

**What happens.** The engine ratchets the trail from the bar's high (`engine.py:280`) and then
tests it against the same bar's low (`engine.py:285`). For a bar that falls before it rallies,
the trail is derived from a high that printed *after* the low, so an exit can be booked at a
level that did not exist when the low occurred. The same ambiguity applies whenever a single
bar's range spans both the stop and the target: `engine.py:285-294` resolves it conservatively
in favour of the stop (I-7), which is the right default, but the engine has no way to know the
true path and no way to tell the caller that a bar was ambiguous.

**Why it matters.** This is inherent to OHLC backtesting and cannot be fixed without tick
data — the defect is not the approximation but its invisibility. A result whose trades were
mostly resolved on ambiguous bars deserves a different level of confidence from one whose
trades were not, and today the two are indistinguishable in the artifact. The conservative
tie-break also means the bias is one-directional and therefore quantifiable if counted.

**Fix.** Count bars where the resolution was ambiguous — a stop-and-target bar, or a trailing
exit on a bar whose low precedes its ratcheting high in the worst case — and surface a
`path_ambiguous_exits` counter on `BacktestResult`. Document the approximation in the module
docstring alongside the existing gap-aware note at `engine.py:6`.

---

### QC-09 — Sharpe and Sortino are gated on trade count; exposure statistics ignore open and same-bar positions (LOW)

**Where:** `apps/api/app/modules/backtesting/metrics.py:157`, `metrics.py:199-201`

**What happens.** Three small mismatches between what a statistic measures and what gates or
feeds it:

1. Sharpe and Sortino are properties of the **equity curve**, but are gated on
   `len(trades) >= MIN_TRADES_FOR_RATIO` as well as on the number of returns
   (`metrics.py:157`). A low-frequency strategy with 4 trades over two years of bars is
   denied a ratio that its return series fully supports.
2. `exposure` sums `t.bars_held` over closed trades. A same-bar entry-and-exit has
   `bars_held = 0` (QC-11), so a strategy that scalps every bar reports zero exposure.
3. Neither `exposure` nor `avg_holding_bars` sees an open position: with
   `close_at_end=False` the live position is reported via `open_position`
   (`engine.py:340-345`) and never becomes a `Trade`, so paper-trading exposure is
   understated by the entire currently-held position.

**Why it matters.** These are second-order display metrics, not accounting, and the sample
gate errs toward silence rather than toward a false number — the right direction. But
exposure is the metric that makes a 2%-of-the-time strategy comparable with an
always-invested one, which is exactly the comparison the metrics block exists to enable.

**Fix.** Gate ratios on `returns.size` alone and keep the trade-count floor for trade
statistics; count exposure from bars in position during the loop rather than reconstructing
it from trades; include the open position's bars in the paper-trading exposure.

---

### QC-10 — The consecutive-loss kill-switch is terminal for the run and undocumented (LOW)

**Where:** `apps/api/app/modules/backtesting/engine.py:172` (init), `engine.py:203-211` (set)

**What happens.** `halted` is set once and never reset anywhere in the module. Reproduced with
`max_consecutive_losses=2` over a 20-bar series: the run produced exactly 2 trades, emitted
`('max_consecutive_losses', '2')`, and took no further entry for the remaining bars.
A consequence is that `consecutive_losses = 0` on a winning trade (`engine.py:203`) is
unreachable once the switch has fired.

**Why it matters.** A permanent kill-switch is a defensible and arguably correct choice for a
research engine — it makes the limit meaningful rather than a speed bump. But it is nowhere
documented: `spec.py:141` names the field without stating the reset policy, and the
methodology page says only that consecutive-loss limits "run inside the engine". A user
setting `max_consecutive_losses=3` on a two-year backtest may be measuring the first few
months of the strategy and the flat line thereafter, and nothing in the result says so beyond
a single risk event.

**Fix.** Document the terminal semantics on `RiskLimits.max_consecutive_losses` and on the
methodology page. If a cooldown is wanted instead, make it explicit (`halt_cooldown_bars`)
rather than implicit. Either way, surface `halted_at` on the result so the flat tail of the
equity curve is self-explaining.

---

### QC-11 — Same-bar entry and exit produces zero-duration trades (LOW)

**Where:** `apps/api/app/modules/backtesting/engine.py:230-294`

**What happens.** Steps 2 and 3 run in the same loop iteration, so a position entered at bar
*i*'s open can be stopped on bar *i*'s low. Reproduced: `entry_ts` and `exit_ts` both
`2024-01-05T00:00:00+00:00`, `bars_held=0`, entry `102`, exit `99.96`, `reason=stop`.

**Why it matters.** The behaviour is **economically defensible** — the open is the first print
of the bar, so the low necessarily occurs at or after it, and refusing to fill would be the
less realistic choice. The problem is downstream: the trade record is degenerate. A trades
table or CSV export renders `entry_ts == exit_ts`, a duration chart gets a zero, and
`exposure` undercounts (QC-09). It is also undocumented and untested, so a future refactor
could silently remove or duplicate it.

**Fix.** Document the rule in the module docstring next to the existing intrabar note
(`engine.py:6`) and add a regression fixture asserting `bars_held == 0` with the exact fill
prices. Consider carrying an explicit `same_bar: bool` on `Trade` so consumers can render it
deliberately rather than as an artifact.

---

### QC-12 — `engine.run` raises `IndexError` on an empty bar sequence (LOW)

**Where:** `apps/api/app/modules/backtesting/engine.py:163`

**What happens.** `entry_ts = bars[0].ts` executes unconditionally during initialisation,
before the main loop. Reproduced: `engine.run(spec, [], config)` → `IndexError: list index out
of range`.

**Why it matters.** Every production caller guards first — `service.py:138` requires
`len(bars) >= 2`, `reference_backtest.py:199-201` and the paper path do likewise — so this is
not reachable in the running system today. But `run` is the module's public entry point, it is
called directly by tests and would be called directly by any future sweep or research
harness, and an `IndexError` from line 163 is an unhelpful diagnostic for what is simply an
empty input.

**Fix.** Raise `ValueError("engine.run requires at least one bar")` at the top of `run()`.
Two lines, and it converts a confusing traceback into a contract.

---

### QC-13 — `data_fingerprint`'s docstring contradicts its implementation (LOW)

**Where:** `apps/api/app/modules/backtesting/service.py:106-118`

**What happens.** The docstring states the function is *"a summary fingerprint (count +
endpoints + first/last close), not a full content hash — two windows that differ only in the
middle collide"*, and defers the real story to a `DatasetSnapshot`. The implementation
directly below it hashes every bar's full OHLCV tuple (`service.py:114-117`). Verified:
changing only an interior bar's high changes the digest. Separately, `DatasetSnapshot` does
not exist anywhere in the codebase — the only occurrence of the identifier is this docstring.

**Why it matters.** The code is right and the comment is wrong, which is the more dangerous
ordering: a reader deciding whether the reference-backtest cache is safe to trust
(`reference_backtest.py:204-205` uses this digest as the cache key) will read the docstring,
conclude the key is collision-prone, and either work around a solved problem or distrust a
correct result. It also advertises a component that does not exist.

**Fix.** Rewrite the docstring to describe the streaming full-content hash it actually
implements, note that cost is O(n) over bars already in memory, and delete the
`DatasetSnapshot` forward-reference or replace it with a concrete TODO.

---

### QC-14 — `spec_hash` mixes cosmetic identity into logical identity (LOW)

**Where:** `apps/api/app/modules/strategies/spec.py:247-251`

**What happens.** The hash covers `model_dump(mode="json")`, which includes `name`. Verified:
two specs identical in every field except `name` hash to `4f51c3b30572...` and
`1fe774e70331...`.

**Why it matters.** Renaming a strategy changes its logical identity, so a rename breaks
cache lookups, breaks reproducibility comparisons across saved versions, and makes "the same
strategy" un-detectable across two users who named it differently. Conversely the hash says
nothing about *how* the result was produced: `ENGINE_VERSION` and the `ExecutionConfig` are
persisted alongside it (I-24) but are not part of any composite key, so nothing at the type
level prevents comparing two results produced under different cost models.

**Fix.** Hash a logic-only projection (`model_dump(exclude={"name"})`) and treat the
reproducibility key as the explicit quadruple `(spec_hash, engine_version,
execution_config_hash, data_fingerprint)` — see §7.

---

### QC-15 — Snapshot tail-truncates trades and equity while metrics cover the full run (LOW)

**Where:** `apps/api/app/modules/backtesting/snapshot.py:177-182, 213, 217`

**What happens.** The payload keeps the **last** 500 trades and the **last** 5,000 equity
points, while `metrics` was computed over the entire run. The truncation is logged
(`snapshot.py:177-182`) but no flag reaches the payload — `result_to_dict` emits no
`equity_curve_truncated` key and no true first timestamp.

**Why it matters.** A long backtest renders a chart that begins mid-run underneath headline
metrics computed over a longer window, with no way for the UI to say so. Max drawdown in
particular may have occurred entirely outside the rendered segment, making the chart appear
to contradict the number printed above it. Tail-truncation also discards exactly the early
history that a drawdown-recovery narrative needs.

**Fix.** Downsample (stride or LTTB) rather than tail-truncate, so the curve spans the full
run at reduced resolution, and add `equity_curve_truncated` plus the true first timestamp to
the payload so the chart can label itself honestly.

---

### QC-16 — The correctness suite has not kept pace with the engine (MEDIUM)

**Where:** `apps/api/tests/test_backtest.py` (125 lines, the entire quant-correctness suite),
`pyproject.toml:41`, `.github/workflows/ci.yml:59`

**What happens.** Detailed in §8. In summary: no test asserts an exact fill price, commission
amount, or metric value anywhere in the repository; the look-ahead canary
(`test_backtest.py:73-85`) perturbs only bars *after* the cut and exercises only `SMA(3)` with
`>`, so it structurally cannot detect intrabar look-ahead; `metrics.py` and
`indicators/compute.py` have no direct unit tests at all; the four new `_reject_unsupported`
validators have no tests; `hypothesis>=6.100` is declared at `pyproject.toml:41` and used
nowhere; and CI runs coverage without `--cov-fail-under`, so coverage cannot regress-fail.

**Why it matters.** Nearly every fix recorded in §2.2 is a behaviour that the existing suite
would not catch if it regressed. The trailing-stop fix, the ATR decision-bar fix, the RSI
zero-loss fix, the Wilder seeding, the sample-size gates and the calendar-aware
annualization are all currently protected by code comments rather than by assertions. That is
the single largest risk to this module going into v2: the correctness work is real, and it is
undefended.

**Fix.** In priority order: (1) an intrabar canary perturbing bar *i*'s high/low with open and
close held fixed, asserting `equity[i]` is unchanged — this is the test that would have caught
the ATR defect at authoring time; (2) hand-calculated golden fixtures for each exit reason;
(3) direct unit tests for `compute_metrics` and each indicator against known series;
(4) the hypothesis properties the dev dependency already pays for; (5) `--cov-fail-under` in
CI.

---

## 4. Metric definition review

Reviewed against `apps/api/app/modules/backtesting/metrics.py` (`METRICS_VERSION = "2.0.0"`).
Most of this table now reads "no issue", which is the accurate result and is reported as such.

| Metric | Current formula (line) | Issue | Recommended definition |
|---|---|---|---|
| `total_return` | `equity[-1]/equity[0] - 1` (`:141`) | None. Descriptive, always reported. | Unchanged |
| `cagr` | `expm1(log(equity[-1]/equity[0]) / years)`, `years` from wall-clock seconds (`:168-175`) | None. Elapsed-time annualization is exact, gated at 180 days, guarded against overflow and non-positive equity. | Unchanged |
| `sharpe` | `mean(excess)/std(excess, ddof=1) * sqrt(ppy)` (`:161-163`) | Gated on trade count as well as return count (QC-09). Undefined when `std == 0` — correctly left `None`. | Gate on `returns.size` only; keep `ddof=1`, keep the annual `risk_free_rate` de-annualized at `:159` |
| `sortino` | `mean(excess)/downside_deviation(excess) * sqrt(ppy)` (`:164-166`) | None. `_downside_deviation` (`:73-84`) is RMS shortfall below target over **all** observations — the standard definition. | Unchanged |
| `calmar` | `cagr / abs(max_drawdown)` (`:176-178`) | Not stripped on public surfaces despite being annualized (QC-04). | Unchanged formula; add to the extrapolating-metric set |
| `max_drawdown` | `min(equity/cummax - 1)` (`:138-140`) | None. | Unchanged |
| `longest_drawdown_bars` | Longest consecutive underwater run (`:143-148`) | None. Bar-denominated, which is honest for a bar-based engine. | Unchanged |
| `recovery_bars` | Bars from deepest trough to a new high, `None` if never recovered (`:150-154`) | None. `None`-when-unrecovered is the correct encoding. | Unchanged |
| `num_trades` | `len(trades)` (`:110`) | None. | Unchanged |
| `win_rate` | `len(wins)/len(trades)` (`:184`) | Break-even trades (`pnl == 0`) count in the denominator but in neither `wins` nor `losses` (`:182-183`). Correct, but undocumented. | Unchanged; document the three-way split |
| `profit_factor` | `gross_win/gross_loss`, else `None` (`:188`) | None. The dollar-amount fallback is gone. | Unchanged |
| `expectancy` | `mean(pnl)` in currency (`:191`) | Currency-denominated while `avg_trade_return` is a fraction; the pair is easy to misread on a UI that shows both. | Unchanged formula; label the unit explicitly |
| `avg_trade_return` | `mean(return_pct)` (`:192`) | Arithmetic mean of per-trade returns — not compounded, and not position-weighted. Correct as labelled. | Unchanged; keep `median_trade_return` beside it, which is the right defence |
| `median_trade_return` | `median(return_pct)` (`:193`) | None. Good addition — robust to the outlier trade that dominates the mean. | Unchanged |
| `avg_holding_bars` | `mean(bars_held)` (`:194`) | Excludes an open position; zero for same-bar trades (QC-09/QC-11). | Count from bars-in-position; include the open position for paper runs |
| `exposure` | `sum(bars_held)/len(equity_curve)`, capped at 1 (`:199-201`) | Same as above — reconstructed from trades rather than measured. The `min(..., 1.0)` cap masks rather than prevents overcounting. | Track a bars-in-position counter in the engine loop and divide by total bars |
| `turnover` | `sum(qty*entry + qty*exit)/equity[0]` (`:202-203`) | Denominated by *starting* equity, so a compounding strategy's later trades are over-weighted relative to the capital actually deployed. | Divide each round trip by equity at the time of the trade, or rename to make the fixed denominator explicit |
| `total_commission` | `sum(t.commission)` (`:195`) | Counts only the **exit** commission recorded on `Trade` (`engine.py:200`); the entry leg is folded into `entry_gross` and appears separately as `BacktestResult.total_commission` (`engine.py:255`). The two keys share a name across different objects and carry different values. | Record both legs on `Trade`, or rename this key `exit_commission` |
| `num_returns`, `span_days` | `returns.size`, elapsed days (`:134-135`) | None. Reporting the sample size next to the gated statistics is exactly right. | Unchanged |

**Absent, and worth adding:** no benchmark of any kind — no buy-and-hold series, alpha, or
beta — so a strategy is never compared against the trivial alternative on the same bars. The
absence is honestly disclosed on the methodology page rather than hidden, but the equity
curve and bar data needed to compute it are already in hand at `engine.py:347`.

---

## 5. Execution, cost and slippage model review

| Component | Implementation | Assessment |
|---|---|---|
| Commission | `commission_bps/10000` per side, default 2 bps (`engine.py:135`, `types.py:24`) | **Correct.** Charged on entry (`:248`) and exit (`:183`), folded into `entry_gross` (`:259`), and PnL is net of both (`:187`). |
| Slippage | `slippage_bps/10000`, default 1 bp, adverse on both legs (`engine.py:74-76, 177-178`) | **Correct in direction** for market orders; **wrong in kind** for take-profit limits (QC-01). |
| Entry fill | `o * (1 + slip)` at the next bar's open (`engine.py:79-85, 233`) | **Correct**, and shared verbatim with the signal service so live and backtested entries agree. |
| Stop fill | Level touched intrabar fills at the level; a genuine gap-through fills at the open (`engine.py:285-291`) | **Correct**, including the pre-ratchet capture that makes the gap test meaningful for trailing stops (I-6). Applying slippage on top of a gapped stop is conservative and defensible — a stop becomes a market order and does slip. |
| Target fill | Level fills at the level, or at the open on a gap above (`engine.py:292-294`) | Gap handling correct; the slippage haircut is not (QC-01). |
| EOD flatten | `sell_fill(bars[-1].close)` when `close_at_end=True` (`engine.py:337`) | **Correct** for backtests. Paper trading passes `close_at_end=False` and reports the live position instead (`trading/service.py:81-82`) — the right split. |
| Return basis | `return_pct = pnl / entry_gross` (`engine.py:197`) | **Defensible and consistently applied** — return on capital-at-risk including the entry commission. Worth one line of documentation since it differs from `pnl / notional`. |
| Position sizing | Four methods (`engine.py:47-71`) | `fixed_units`, `percent_equity`, `risk_per_trade` correct; `atr` carries a hardcoded risk fraction and a silent warm-up fallback (QC-05). |
| Position clamp | `max_position_pct` of equity, with a `RiskEvent` (`engine.py:241-246`) | **Correct and observable.** |
| Cash clamp | `(cash/(1+comm))/fill`, commission-inclusive (`engine.py:249-252`) | **Numerically correct** — minimum equity across the probe run was exactly `100000`, never negative — but silent (QC-06). |
| Leverage / shorting / margin | None (`spec.py:225-229`, single `in_pos`/`qty` pair) | **Correct for the stated scope**, and now enforced at validation rather than assumed. |
| Frictionless mode | `frictionless=True` zeroes commission and slippage (`engine.py:134-135`) | Test-only, loudly flagged (`types.py:27`), and — critically — **persisted** in the artifact (`snapshot.py:193`), so a zero-cost run can no longer masquerade as a costed one. |
| Cost model versioning | `COST_MODEL_VERSION = "1.0.0"` in `as_dict()` (`types.py:11, 29-37`) | **Good.** Old results stay interpretable when cost semantics change. |

**Not modelled, and undisclosed in the result:** market impact, partial fills, borrow costs,
financing, spread (slippage is a flat symmetric proxy), queue position, and exchange fee
tiers. For a bar-resolution long-only research engine these are reasonable omissions; the
recommendation is to enumerate them once in the methodology page so the cost model's scope is
stated rather than inferred.

---

## 6. Event ordering within a bar

The exact order as implemented in `engine.run`'s loop
(`apps/api/app/modules/backtesting/engine.py:215-330`), per bar `i`:

| Step | Action | Lines |
|---|---|---|
| 0 | Unpack `o, h, low_, c` from bar `i`. | `:216` |
| 1 | **Day rollover.** If `bar.ts.date()` differs from `current_day`, set `current_day`, snapshot `day_start_equity = cash + qty*o` (marked at *this* bar's open), and clear `day_halted`. Uses the **UTC** date (QC-07). | `:218-222` |
| 2 | **Pending exit fills at this open.** If in a position and a signal/time exit was armed on a previous bar, close at `sell_fill(o)` and clear the flag. Runs *before* step 3, so a market-on-open exit pre-empts this bar's bracket. | `:225-227` |
| 3 | **Pending entry fills at this open.** Only if flat. Equity for sizing is `cash` — which already includes step 2's proceeds, so a flip re-uses realized capital rather than stale equity. Fill is `o*(1+slip)`. ATR is read from bar `i-1`, the **decision** bar. Apply the `max_position_pct` clamp (emits a `RiskEvent`), then the cash clamp (silent). If `size > 0`: debit cash, set `in_pos`, and arm the bracket — `highest = fill` (the entry price, **not** this bar's high), `stop_price`, `target_price`. | `:230-267` |
| 4 | **Intrabar bracket.** Only if in a position — so a position closed in step 2 is skipped, and a position opened in step 3 **is** eligible on its own entry bar (QC-11). Capture `stop_at_open = stop_price` *before* any ratchet. If trailing: `highest = max(highest, h)`, recompute the trail, and raise `stop_price` (setting `stop_reason = "trailing"`). Then: **if** `low_ <= stop_price` → `gapped = stop_at_open is not None and o <= stop_at_open`; fill at `o` if gapped else at `stop_price`. **elif** `h >= target_price` → fill at `o` if the bar gapped above, else at `target_price`. Stop is tested before target, so an ambiguous bar resolves conservatively. | `:269-294` |
| 5 | **Arm the time exit.** If still in a position and `(i - entry_i) >= time_exit_bars`, set `pending_exit = "time"` for the *next* open (QC-02). Re-tests `in_pos`, so a position closed in step 2 or 4 cannot arm. | `:296-298` |
| 6 | **Mark to market at close.** `equity = cash + qty*c`; append one `EquityPoint` per bar, unconditionally. | `:300-302` |
| 7 | **Daily-loss check.** If not already halted for the day and `equity - day_start_equity < -(day_start_equity * max_daily_loss_pct)`, set `day_halted` and emit a `RiskEvent`. Evaluated *after* step 6, so it sees this bar's close, and *before* step 8, so it can suppress this bar's decision. | `:304-312` |
| 8 | **Decisions at close for the next bar** — skipped entirely on the last bar (`i < len(bars) - 1`). If **flat, not halted, not day-halted**: evaluate the time-of-day window (converted to exchange-local time when `timezone="exchange"`), then `evaluate(entry_long, arrays, i)`; if true, set `pending_entry`. **elif in a position** and no exit is already pending and `exit_conditions` evaluates true: set `pending_exit = "signal"`. The two branches are mutually exclusive on `in_pos`, which is why a halt cannot suppress exit evaluation (I-9). | `:314-330` |

**After the loop:** if still in a position — with `close_at_end=True`, flatten at
`sell_fill(bars[-1].close)` and **overwrite** the final equity point with `cash`
(`:336-338`); with `close_at_end=False` (paper), leave it open and report `open_position`
(`:340-345`). Then compute metrics over the full curve with the instrument calendar (`:348`).

**Ordering properties worth preserving:** exit-before-entry at the open (step 2 before 3);
clamp-before-debit (step 3); mark-to-market before the daily-loss test (6 before 7); and the
daily-loss test before the decision (7 before 8). Each is currently correct and each is
load-bearing.

---

## 7. Reproducibility review

`BacktestResult` carries `spec_hash`, `engine_version` and `data_fingerprint`
(`types.py:81-83`), populated at `service.py:142-143` and persisted at `snapshot.py:195-197`
alongside `metrics_version` and the execution config.

### 7.1 Spec-hash canonicalization

`spec_hash()` is `sha256` over `canonical_json()`, which is
`json.dumps(model_dump(mode="json"), sort_keys=True, separators=(",", ":"))`
(`spec.py:247-251`). Verified properties:

| Property | Status | Evidence |
|---|---|---|
| Key order is normalized | Yes | `sort_keys=True` |
| Whitespace is normalized | Yes | compact separators; sample output `{"entry_long":{"conditions":[{"left":{"field":null,...` |
| Numeric types are normalized | Yes | `IndicatorSpec.params` is `dict[str, float]` (`catalog.py:67`), so `{"period": 20}` canonicalizes to `20.0` — `2` vs `2.0` is not a hazard |
| Defaults are always emitted | Yes | `"multiplier":1.0,"offset":0.0,"output":null` present in the sample output |
| Unknown fields cannot enter | Yes | `extra="forbid"` on every model |
| `universe` order significant | Yes, and now moot | `len(universe) > 1` is rejected (`spec.py:230-235`) |
| Cosmetic fields excluded | **No** | `name` is included; a rename changes the hash (QC-14) |

The canonicalization itself is sound. The only defect is *what* is fed into it.

### 7.2 Engine version

`ENGINE_VERSION = "0.1.0"` is a hand-maintained constant at `spec.py:27`, imported by the
engine (`engine.py:28`) and stamped onto every result (`engine.py:359`). Three gaps:

- Nothing enforces a bump when engine semantics change. Every fix in §2.2 alters the numbers
  a given spec produces, and all of them ship under `0.1.0` — so two results bearing the same
  `(spec_hash, engine_version, data_fingerprint)` triple can legitimately differ.
- It lives in `strategies/spec.py` rather than in `backtesting/`, an odd coupling for a value
  that describes the engine.
- There is no version-pinned replay path: nothing can re-run a stored spec under the engine
  version that produced it, which ADR-0008's requirement that "saved versions backtest
  identically forever" implies.

`METRICS_VERSION = "2.0.0"` (`metrics.py:40`) and `COST_MODEL_VERSION = "1.0.0"`
(`types.py:11`) are better: both are separately versioned and both are persisted. Applying
the same discipline to `ENGINE_VERSION` — and bumping it now, given §2.2 — is the single
highest-value reproducibility change available.

### 7.3 Data fingerprint

Now a streaming SHA-256 over `instrument|timeframe|len(bars)` plus every bar's
`ts,open,high,low,close,volume` (`service.py:112-118`). Verified to change when only an
interior bar's high changes. This closes the collision class that made the reference-backtest
memo cache (`reference_backtest.py:204-205`) able to serve a stale public number after a
vendor correction. The remaining issue is documentation, not behaviour (QC-13).

### 7.4 The reproducibility key

Recommended composite, none of which requires new storage — all four values are already
computed:

```
(spec_hash_logic_only, engine_version, execution_config_hash, data_fingerprint)
```

`execution_config_hash` is a hash of `ExecutionConfig.as_dict()` (`types.py:29-37`), which
already includes `COST_MODEL_VERSION` and the `frictionless` flag. Today the config is
persisted but not part of any key, so two artifacts produced under different cost models are
comparable only by manual inspection.

---

## 8. Test coverage gap table

`apps/api/tests/test_backtest.py` (125 lines) is the entire quant-correctness suite;
`test_backtest_run.py` covers persistence, engine parity on `final_equity` and `num_trades`,
owner scoping, and endpoint auth — not quantitative correctness.

> **Note on the requirement column.** `docs/v2/` currently contains only
> `BASELINE_VERIFICATION.md`; the v2 brief is not checked into the repository at the time of
> writing. The requirement rows below are reproduced from §17 of the brief as supplied with
> this audit's remit and should be reconciled against the canonical document before being
> treated as a contract.

| # | v2 brief §17 requirement | Exists? | Evidence / gap |
|---|---|---|---|
| 1 | Look-ahead canary (future bars cannot change past equity) | **Yes** | `test_backtest.py:73-85`. Proves indicator computation is causal. |
| 2 | **Intrabar** look-ahead canary (bar *i*'s H/L cannot change equity at *i*) | **No** | The critical gap. The existing canary perturbs only bars after the cut, so the ATR defect passed it trivially. Verified manually in this audit (I-5); nothing asserts it in CI. |
| 3 | Cash conservation | **Partial** | `test_backtest.py:88-92`. Near-tautological: `close_at_end=True` overwrites the last equity point with `cash` (`engine.py:338`), which is by construction `initial + Σpnl`. Catches accounting drift; validates no fill price or commission amount. |
| 4 | Determinism | **Yes** | `test_backtest.py:95-101`. Real but cheap — the engine has no RNG or clock read. |
| 5 | Cost realism (frictionless ≥ realistic) | **Partial** | `test_backtest.py:104-110`. Not a theorem — costs can change the trade path — but passes empirically and is a reasonable smoke test. |
| 6 | Stop-loss fires | **Partial** | `test_backtest.py:113-119`. Asserts only that *a* stop exists with `pnl < 0`. No exact fill price. |
| 7 | Exact fill prices for every exit reason (golden fixtures) | **No** | No test in the repository asserts an exact fill price, commission amount, or metric value. |
| 8 | Trailing-stop exit level and `exit_reason` | **No** | `grep -rn "trailing" apps/api/tests` returns nothing. The §2.2 fix is entirely undefended. |
| 9 | Take-profit exit level | **No** | Untested; QC-01 lives here. |
| 10 | Time-exit bar index | **No** | Untested; QC-02 lives here. |
| 11 | Same-bar entry-and-exit | **No** | Untested (QC-11). |
| 12 | Gap-through vs touched-intrabar stop fills | **No** | Untested — the distinction the `stop_at_open` fix turns on. |
| 13 | Daily-loss halt | **No** | Untested. |
| 14 | Consecutive-loss kill-switch (including terminal semantics) | **No** | Untested (QC-10). |
| 15 | `max_position_pct` clamp emits a `RiskEvent` | **No** | Untested. |
| 16 | Insufficient-cash clamp / non-negative cash | **No** | Untested (QC-06). |
| 17 | Time-of-day filter with `timezone="exchange"` | **No** | Untested — a §2.2 fix with no regression guard. |
| 18 | Spec validators reject `entry_short`, multi-symbol `universe`, `max_open_positions > 1`, `risk_per_trade` without a stop | **No** | Four brand-new validators (`spec.py:225-245`), zero tests. `grep` over `test_strategies.py` finds no reference to any of them. |
| 19 | `compute_metrics` unit tests against known series | **No** | No test imports `compute_metrics`, `periods_per_year`, or `sample_size_notes`. `test_backtest.py:122-125` only asserts key presence and `max_drawdown <= 0`. |
| 20 | Sample-size gating returns `None` below the floors | **No** | Untested. Verified manually here (I-18). |
| 21 | Calendar-aware annualization (XNYS vs 24x7) | **No** | Untested. Verified manually here (I-19). |
| 22 | Indicator fidelity vs a reference implementation (RSI/ATR/EMA/BBANDS/MACD/VWAP) | **No** | No test references `_rsi`, `_atr`, Wilder seeding, or VWAP. The canary exercises `SMA(3)` and `>` only. |
| 23 | RSI boundary behaviour (no losses → 100, no gains → 0) | **No** | Untested. Verified manually here (I-21). |
| 24 | VWAP window-independence across overlapping queries | **No** | Untested — and QC-03 shows a residual failure that such a test would pin down. |
| 25 | `cross_above` / `cross_below` semantics | **No** | Never exercised by any engine test. |
| 26 | Warm-up NaN cannot fire a trade | **Partial** | Implied by the canary's indicator choice; never asserted directly. |
| 27 | Property-based invariants (cash ≥ 0, Σpnl == final − initial, qty ≥ 0, entry_ts ≤ exit_ts, low ≤ fill ≤ high for non-gapped fills) | **No** | `hypothesis>=6.100` declared at `pyproject.toml:41`, used nowhere. |
| 28 | Reproducibility: identical `(spec, bars, config)` → identical `spec_hash` / `data_fingerprint` | **No** | Determinism of the equity curve is tested; the hashes are not. |
| 29 | Empty / degenerate bar inputs | **No** | Untested; QC-12 lives here. |
| 30 | Coverage floor enforced in CI | **No** | `.github/workflows/ci.yml:59` runs `pytest --cov=app --cov-report=term-missing` with no `--cov-fail-under`, so coverage cannot regress-fail. |

**Summary:** 3 of 30 requirements are met, 4 partially, 23 not at all. The concentration is
telling — every requirement that would defend a §2.2 fix sits in the "No" column.

---

## Baseline Verification (see BASELINE_VERIFICATION.md)
