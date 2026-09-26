# What we already tried, and what happened

## 2026-09-26: game-style look for Rapier Desk
- The first design (sidebar with a list of runs next to a content pane) looked like a chat app. It was replaced with a Coolbrador game layout: a header with coloured tabs, a starry hero with Bee Sid, save-slot run cards, a leaderboard, and a speech bubble for run status. The equity chart is now drawn in the app; the report's full matplotlib chart is still one click away.
- Qt stylesheet findings: a `font-size` in the app stylesheet overrides fonts set in code, so all fonts are set in code; and a `QWidget { background: … }` rule also paints every plain container over custom-drawn panels, so window colours come from the app palette instead.
- A clickable `QFrame` only receives the mouse release (its click) if it accepts the press; otherwise clicks on its labels go to the parent.

## 2026-09-26: one-file desktop app (RapierDesk.exe)
- Rapier Desk now builds as a single file with the Bee Sid icon, about 140 MB. On the Linux test machine the window appeared about 4.5 s after launch, because a one-file app unpacks itself on every start; a splash covers the wait.
- That unpack folder is deleted on exit, so the packaged app keeps runs and the market-data cache in the user's data folder instead.
- Clicking through the packaged app found two packaging gaps unit tests could not: pandas loads `tabulate` lazily (so it was not bundled), and `tabulate` 0.10 reads its version from package metadata (also not bundled). Every packaged backtest failed at `summary.md` until both were added. The build's self-test now runs the engine and report writer inside the packaged app, so CI catches this on Windows too.
- Runs are written to a hidden `.partial` folder and moved into place only when complete, so a failed run no longer leaves a half-written saved run.
- Saved-run folder names are unchanged (CLI paths and these docs still work); only the app shows readable names.

## 2026-09-26: Windows token-file permissions
- Windows does not implement POSIX `chmod(600)` for NTFS ACLs; saving Tradara tokens now restricts the DACL to the current user and SYSTEM before writing, and CI checks the resulting ACL. Unix retains mode 0600.

## 2026-09-26: desktop research cockpit
- Added a native Windows/Linux Qt dashboard for existing reports and manual backtest runs; no live-order controls were added.
- Sample reports load without the ignored market-data cache. Fresh cached-only backtests still need that cache; historical short-interval data is not bundled.
- The cached 1h run on the development machine completed and produced `results/latest` (21 trades, +$3,048). This uses its local 1h cache and is not a new strategy result.
- No strategy settings or trading fills were changed.

A log so the next person doesn't repeat work. Newest first. Numbers are from backtests unless noted.

## 2026-09-25: final revision, "can it pay a living unattended?"
- **Income** (`tools/prop_income.py`): about $22.7k/yr per account at backtest quality, and $9.5k/yr if live is half as good.
  - teacher-1m's edge isn't statistically proven yet (95% range −$17..+$117 per trade).
  - scalp-5m's is (+$34..+$158).
  - Details and the go/no-go rule: `docs/PROP_FIRM_INCOME.md`.
- **Doubling size:** doubles income, but at 50% weaker edge it means 0.66 breaches a year. Default size kept.
- **Live bugs that would have broken a long unattended run, now fixed:**
  - brokers kept trading the expiring contract after a quarterly roll;
  - no holiday early-close flatten;
  - no reconnect after IB Gateway's daily restart;
  - a failed cycle left resting orders live and skipped the close flatten;
  - a Yahoo outage stopped the 1h history load.
- **Not changed:** the strategy, since that would be tuning to the same small sample. The backtest also doesn't model holiday early closes (live-only rail, about 9 days a year).

## 2026-09-25: third-party check on FX Replay (18 trading days, 2026-08-28 → 09-23)
- Replayed Rapier's exact orders on fxreplay.com (`tools/fxreplay/`). **37 of 37 trades ended the same way (win or loss)** as the backtest.
- **Found:** market-order entries filled −8 to +17 ticks away from the backtest's price, so a few trades were really 0.87–0.99R, not 1R.
- **Fixed:**
  - the backtest now fills market entries at the next bar's open;
  - the live bot moves the target after the fill (IBKR);
  - Tradara gets a fixed 2-tick pad.
- **Cost:** the 5m run went from +$2,710 to +$2,551, the 1m run from +$2,503 to +$2,454. No wins turned into losses.
- **Considered, not done:** an extra tick of cushion on limit-order targets. Real exchange limits can't fill worse than their price; only FX Replay's slippage setting did that.
- **Tradara has no one-cancels-all across separate orders.** Measured in the simulator: no double fills in that month. It's still a theoretical risk.

## Live-stack replay (engine → executor → simulated broker vs the plain backtest)
- First version reproduced 43 of 44 trades but added **52 extra trades**, because orders ignored the session and daily limits. Fixed.
- Then found and fixed:
  - orders not re-priced when the OTE level moved;
  - signal names changing as the data window slid (caused endless cancel/replace);
  - tick rounding leaving targets 0.25 short of 1R.
- Now: 42 of 43 match with the same win/loss.

## Chasing 75% win rate and a single $11k trade
- Searched 4,600+ settings combinations, always scoring on the worse of in-sample and out-of-sample.
- Settings that showed 75–80% on one half of the data dropped to 20–40% on the other half: curve-fitting.
- The only config with an $11.6k trade lost $5.7k with a $10.2k drawdown on the previous year. Rejected.
- The math behind this:
  - 75% win rate at ≥ 1R means profit factor ≥ 3, while raw OTE touches win about 42–50%;
  - the best filters robustly reach about 55–66%;
  - an $11k trade with ~$400 risk needs roughly 27R, but the biggest move any OTE trade made in 14 months (flat daily) was 13.8R.

## Owner's 1-minute rules (`teacher-1m`)
- Breakeven at 0.5R, as the old bot had it: 25% / 44% win rate on the two halves, because it scratched trades that later won. Removed.
- A fixed 28.75-pt stop was worse than a stop beyond the start of the move. Changed.
- 9EMA "golden belt" confluence on 1m left almost no trades, and those lost. Off.

## Old "Bee Sid" bot's claims (checked, not trusted)
- Its "75% win rate" left out 32 breakeven trades out of 60. Counting them it was 35%, and the filters were picked on the same data.
- Its "1m" data before 2026-08-23 was really 5m/2m bars copied onto a 1-minute grid. Rapier refuses to import such days.
- The owner's real trading journal: 46% win rate, +$28.5k, best trade $4,725, max drawdown $2,575. That's the honest benchmark.

## Data problems
- Yahoo `NQ=F` jumps at every contract roll. Rapier detects and back-adjusts these.
- Yahoo revises old bars now and then, so results can shift with no code change.
