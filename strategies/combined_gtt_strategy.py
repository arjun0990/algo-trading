# strategies/combined_gtt_strategy.py

from strategies.catch_gtt_order_strategy import ManualGTTStrategy
from strategies.auto_exit_gtt_strategy import AutoExitGTTStrategy
from utils import log


class CombinedGTTStrategy:

    def __init__(self):

        # Manual GTT (keyboard-based MULTIPLE GTT logic)
        self.manual = ManualGTTStrategy()

        # Auto Exit GTT (position-detection TWO SINGLE GTT logic)
        self.auto = AutoExitGTTStrategy()


    # -------------------------------------------------
    # MAIN RUN LOOP
    # -------------------------------------------------
    def run(self, broker, market_data, risk_engine, instruments):

        # -------------------------------------------------
        # 1️⃣ Always run Manual GTT monitoring first
        #    (strike monitoring + keypress handling)
        # -------------------------------------------------
        self.manual.run(
            broker=broker,
            market_data=market_data,
            risk_engine=risk_engine,
            instruments=instruments
        )

        # -------------------------------------------------
        # 2️⃣ If manual GTT trade is active,
        #    Auto GTT must NOT interfere
        # -------------------------------------------------
        if self.manual.trade_active:
            # Ensure AutoExit is clean while manual GTT controls trade
            self.auto.trade_active = False
            self.auto.active_instrument = None
            self.auto.target_gtt_id = None
            self.auto.sl_gtt_id = None
            # IMPORTANT: clear processing lock
            self.auto.processing_instruments.clear()
            return
        # else:
            # log("[COMBINED_GTT] Mode: AUTO_MONITORING")

        # -------------------------------------------------
        # 3️⃣ If manual is not active,
        #    Auto GTT can monitor open positions
        # -------------------------------------------------
        self.auto.run(
            broker=broker,
            market_data=market_data,
            risk_engine=risk_engine,
            instruments=instruments
        )