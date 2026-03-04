import time
from datetime import datetime

from config import (
    ACCESS_TOKEN,
    ACTIVE_STRATEGY,
    GLOBAL_CONFIG,
)

from core.utils import log
from core.broker import BrokerClient
from core.risk_engine import RiskEngine
from core.instruments import InstrumentManager
from core.market_data import MarketData
from core.execution_engine import ExecutionEngine
from strategies.strategy_factory import get_strategy


# =========================================================
# INITIALIZE CORE COMPONENTS
# =========================================================

broker = BrokerClient(ACCESS_TOKEN)

risk = RiskEngine(broker)

instrument_manager = InstrumentManager()
market_data = MarketData(broker)

strategy = get_strategy(ACTIVE_STRATEGY)

execution = ExecutionEngine(
    broker=broker,
    risk_engine=risk
)

log(f"Framework Started | Active Strategy: {ACTIVE_STRATEGY}")


# =========================================================
# MAIN LOOP
# =========================================================

try:
    while True:

        # ---------------------------------------------
        # Global Risk Check
        # ---------------------------------------------
        if GLOBAL_CONFIG["enable_global_pnl_guard"]:
            risk.check_global_pnl()

        # ---------------------------------------------
        # Strategy Signal
        # ---------------------------------------------
        # ---------------------------------------------
        # Strategy Handling
        # ---------------------------------------------

        # ---------------------------------------------
        # Strategy Handling
        # ---------------------------------------------

        if ACTIVE_STRATEGY in ["GTT", "AUTO_EXIT_GTT", "COMBINED_GTT"]:

            strategy.run(
                broker=broker,
                market_data=market_data,
                risk_engine=risk,
                instruments=instrument_manager
            )

        else:

            signal = strategy.check_signal(market_data, instrument_manager)

            if signal:
                execution.execute(signal)

                if hasattr(strategy, "reset_session"):
                    strategy.reset_session()
        # signal = strategy.check_signal(market_data, instrument_manager)
        #
        # if signal:
        #     execution.execute(signal)
        #
        #     # Reset strategy session if supported
        #     if hasattr(strategy, "reset_session"):
        #         strategy.reset_session()
        #
        # time.sleep(1)

except Exception as e:
    log(f"CRITICAL SYSTEM ERROR: {e}")
    raise