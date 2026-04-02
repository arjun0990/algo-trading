import time
from datetime import datetime

from core.state_store import StateStore
from core.stream_manager import StreamManager
from core.data_provider import DataProvider

from config import (
    ACCESS_TOKEN,
    ACTIVE_STRATEGY,
    GLOBAL_CONFIG,
    ENABLE_STREAMING,
    STREAM_CONFIG
)

from core.utils import log
from core.broker import BrokerClient
from core.risk_engine import RiskEngine
from core.instruments import InstrumentManager
from core.market_data import MarketData
from core.execution_engine import ExecutionEngine
from strategies.strategy_factory import get_strategy
from strategies.combined_instant_engine import CombinedInstantEngine

# =========================================================
# INITIALIZE CORE COMPONENTS (CORRECT ORDER)
# =========================================================

# 1️⃣ Broker
broker = BrokerClient(ACCESS_TOKEN)

# 2️⃣ Market Data (needs broker)
market_data = MarketData(broker)

# 3️⃣ State Store
state_store = StateStore()
# -------------------------------------------------
# INITIAL SNAPSHOT LOAD
# -------------------------------------------------

# Load existing positions
positions = broker.get_positions()

for p in positions:
    instrument = p.get("instrument_token")
    qty = int(p.get("quantity", 0))

    state_store.update_position(instrument, qty)

# Load existing orders
orders = broker.get_order_book()

for o in orders:
    order_id = o.get("order_id")
    state_store.update_order(order_id, o)

log("[SYSTEM] StateStore snapshot loaded")

# 4️⃣ Stream Manager (optional)
stream_manager = None
if ENABLE_STREAMING:
    stream_manager = StreamManager(
        state_store=state_store,
        access_token=ACCESS_TOKEN
    )
    stream_manager.start()

# 5️⃣ Data Provider (central abstraction layer)
data_provider = DataProvider(
    broker=broker,
    market_data=market_data,
    state_store=state_store,
    enable_streaming=ENABLE_STREAMING,
    stream_manager=stream_manager
)
broker.data_provider = data_provider
# 6️⃣ Risk Engine (centralized PnL logic)
risk = RiskEngine(
    broker=broker,
    data_provider=data_provider
)

# 7️⃣ Instrument Manager
instrument_manager = InstrumentManager()

# 8️⃣ Strategy
strategy = get_strategy(ACTIVE_STRATEGY)

# 9️⃣ Execution Engine
execution = ExecutionEngine(
    broker=broker,
    risk_engine=risk
)

log(f"Framework Started | Active Strategy: {ACTIVE_STRATEGY}")

import requests
print(requests.get("https://api.ipify.org").text)
# =========================================================
# MAIN LOOP
# =========================================================

try:
    while True:
        # ---------------------------------------------
        # STREAM HEALTH CHECK
        # ---------------------------------------------
        if ENABLE_STREAMING:

            if state_store.is_stream_stale(STREAM_CONFIG["heartbeat_timeout_seconds"]):
                log("[SYSTEM] Stream heartbeat stale → Trading paused")
                time.sleep(1)
                continue

        # ---------------------------------------------
        # Global Risk Check
        # ---------------------------------------------
        # if GLOBAL_CONFIG["enable_global_pnl_guard"]:
        #     risk.check_global_pnl()

        # ---------------------------------------------
        # Strategy Handling
        # ---------------------------------------------

        # Event-driven strategies
        # ---------------------------------------------
        # Strategy Handling
        # ---------------------------------------------
        if ACTIVE_STRATEGY in ["GTT", "AUTO_EXIT_GTT", "COMBINED_GTT", "COMBINED_INSTANT_BRACKET","COMBINED_INSTANT_ENGINE","INSTANT_FIRE","INSTANT_EXPIRY_BLAST"]:

            strategy.run(
                broker=broker,
                market_data=data_provider,
                risk_engine=risk,
                instruments=instrument_manager
            )

        else:

            signal = strategy.check_signal(
                data_provider,
                instrument_manager
            )

            if signal:
                execution.execute(signal)

                if hasattr(strategy, "reset_session"):
                    strategy.reset_session()

except Exception as e:
    log(f"CRITICAL SYSTEM ERROR: {e}")
    raise