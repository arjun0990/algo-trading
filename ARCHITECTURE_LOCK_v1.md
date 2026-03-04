Framework Version: Institutional Build v1.0
Status: Core Frozen
Flatten: Centralized via broker.flatten_and_verify()
PnL Guard: Generic Toggle Enabled
SL Shift Rule: Strategy-Defined (Current Bounce Strategy = +20 Fixed)
Single Trade: Enforced
Lot Size: Fixed at 65 (Exchange Validated)

🏛 ALGO NIFTY INSTITUTIONAL FRAMEWORK
🔒 OFFICIAL LOCKED SNAPSHOT — v1.0
1️⃣ CORE PHILOSOPHY

This is a layered, capital-protected, single-trade institutional execution framework for NIFTY options.

Architecture separation is strict:

Strategy Layer      → Signal generation only
Execution Layer     → Trade lifecycle management
Risk Layer          → Account-level capital protection
Broker Layer        → API handling + guaranteed flatten
Market Data Layer   → Quotes & historical retrieval
Instrument Layer    → Contract discovery & expiry resolution
Config Layer        → All runtime controls
Main Loop           → Orchestration only

No cross-layer leakage.

2️⃣ GLOBAL DESIGN RULES (NON-NEGOTIABLE)

These are enforced system-wide:

✅ Single trade at a time

✅ Fixed exchange LOT_SIZE = 65 (validated)

✅ USER_LOTS must be > 0 (validated in ExecutionEngine.init)

✅ Strict lot integrity enforcement everywhere

✅ Entry confirmation must verify position visibility

✅ Stop-loss must be verified active on exchange

✅ SL shift only at +20 (parity preserved)

✅ Partial exit toggle supported

✅ Global PnL guard fully generic

✅ Flatten logic centralized & verified

✅ All exit paths use broker.flatten_and_verify()

✅ Fail-fast philosophy (sys.exit on structural inconsistency)

3️⃣ MODULE-BY-MODULE STRUCTURE
📁 config.py

Contains all runtime controls.

🔹 Access
ACCESS_TOKEN
🔹 Account Risk
ENABLE_GLOBAL_PNL_GUARD
PROFIT_LOCK_ENABLED
LOSS_LIMIT_ENABLED
PROFIT_LOCK
LOSS_LIMIT
CHECK_PNL_BEFORE_ENTRY

Behavior matrix:

Master	Profit	Loss	Result
False	X	X	Guard disabled
True	True	False	Profit only
True	False	True	Loss only
True	True	True	Both active
🔹 Execution Control
LOT_SIZE = 65
USER_LOTS
PARTIAL_EXIT_ENABLED
MAX_ENTRY_CHASE
ENTRY_TIMEOUT_SECONDS
MAX_TRADE_DURATION_MINUTES
SL_BUFFER
USE_SPREAD_FILTER
MAX_SPREAD
🔹 Time Controls
START_HOUR
START_MINUTE
NO_NEW_TRADES_AFTER_HOUR
NO_NEW_TRADES_AFTER_MINUTE
🔹 Bounce Strategy Parameters
STRIKE_OFFSET
BOUNCE_POINTS
ENTRY_BUFFER
MIN_PREMIUM
📁 core/broker.py — BrokerClient

Handles all exchange interaction.

Responsibilities:

safe_request() with retry logic

place_order()

cancel_order()

get_order_status()

get_positions()

get_position_qty()

cancel_all_pending_orders()

exit_all_positions()

🔒 flatten_and_verify()

Centralized flatten guarantee:

Steps:

cancel_all_pending_orders()

exit_all_positions()

Wait up to max_wait_seconds (default 5s)

Verify all positions quantity == 0

Log result

Return True/False

⚠️ No module is allowed to call exit_all_positions() directly.
All flattening must use flatten_and_verify().

📁 core/risk_engine.py — RiskEngine

Fully generic account-level protection.

Constructor Parameters:
enable_guard
profit_lock_enabled
loss_limit_enabled
profit_lock
loss_limit

Validation:

If profit lock enabled → must be > 0

If loss limit enabled → must be < 0

calculate_net_pnl()

Adds:

unrealised_pnl

realised_pnl

From all broker positions.

check_global_pnl()

Logic:

if not enable_guard → return

trigger = False

if profit_lock_enabled and pnl >= profit_lock:
    trigger = True

if loss_limit_enabled and pnl <= loss_limit:
    trigger = True

if trigger:
    broker.flatten_and_verify()
    sys.exit()

Fully strategy-agnostic.

📁 core/execution_engine.py — ExecutionEngine

Handles entire trade lifecycle.

🔹 Constructor

Validates:

if USER_LOTS <= 0:
    log("CRITICAL: USER_LOTS must be > 0")
    sys.exit()

Initializes:

total_lots

total_qty

active_trade flag

🔹 Single Trade Enforcement

Before execution:

if self.active_trade or self.has_open_position():
    block trade

has_open_position() checks broker positions.

🔹 Entry Flow

Round entry price to tick.

Place LIMIT BUY.

Entry confirmation loop:

3-attempt position visibility check.

Verify lot integrity.

Detect partial fills.

Enforce ENTRY_TIMEOUT_SECONDS.

Enforce MAX_ENTRY_CHASE.

On failure → flatten_and_verify().

🔹 Initial SL

SL-M placed.

Verify status is OPEN or TRIGGER PENDING.

On failure → flatten_and_verify().

🔹 Trade Management Loop

Every iteration:

risk_engine.check_global_pnl()

manual_exit_pressed() support

Verify lot integrity

External quantity reconciliation:

If qty changed → rebalance SL

Time exit enforcement

Partial exit engine (if enabled)

🔹 Partial Exit Engine

Uses generate_partial_plan()

Lot-based exits only

Strict order completion verification

On rejection → flatten_and_verify()

🔹 +20 SL Shift Rule

Only when points == 20:

Cancel existing SL

Move SL to breakeven

Verify SL active

This rule is currently fixed (not generalized).

📁 strategies/bounce_strategy.py

Signal-only module.

Does NOT:

Place orders

Manage SL

Manage exits

Behavior:

ATM strike ± STRIKE_OFFSET

Historical 10-min low initialization (only once)

Bounce detection

Ready state tracking

Premium filter

Spread filter

Day high filter

Entry level = low + BOUNCE_POINTS + ENTRY_BUFFER

Returns signal:

{
    "instrument_key": key,
    "entry_price": entry_level,
    "initial_sl_reference": low
}

After trade completes:

strategy.state = {}
📁 core/market_data.py

Provides:

get_ltp()

get_full_quote()

get_historical_candles()

No business logic.

📁 core/instruments.py — InstrumentManager

ensure_instrument_file()

get_nearest_expiry()

find_option()

Validates:

lot_size == 65
📁 main.py

Wrapped in:

def main():

Guarded by:

if __name__ == "__main__":
    main()

Loop flow:

Wait for START_HOUR

risk.check_global_pnl()

signal = strategy.check_signal()

If signal → execution.execute(signal)

strategy.state reset

Repeat

4️⃣ SAFETY MATRIX
Risk	Protection
Double trade	active_trade + broker check
SL not placed	verification required
Partial fill	lot validation
External intervention	SL rebalance
API failure	retry + fail-fast
Hanging orders	flatten_and_verify()
Account loss	global guard
Profit overshoot	profit lock toggle
Timeout entry	ENTRY_TIMEOUT_SECONDS
Price runaway	MAX_ENTRY_CHASE
5️⃣ CURRENT LIMITATIONS (INTENTIONAL)

SL shift rule fixed at +20

Only one strategy active at a time

No multi-symbol orchestration

No EOD auto shutdown yet

No equity trailing logic yet

6️⃣ FRAMEWORK STATUS

Institutional Build v1.0 is:

Modular

Capital-protected

Flatten-hardened

Strategy-isolated

Fully generic risk layer

Execution verified

Architecturally stable

This architecture must remain frozen when building new strategies.

🔒 END OF LOCKED SNAPSHOT v1.0