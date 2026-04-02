import sys
from core.utils import log
from config import INSTANT_ENGINE_CONFIG, GLOBAL_CONFIG
import time

class RiskEngine:

    def __init__(self, broker, data_provider=None):
        self.broker = broker
        self.data_provider = data_provider

        self.enable_global_guard = INSTANT_ENGINE_CONFIG["enable_global_pnl_guard"]
        self.enable_trade_guard = INSTANT_ENGINE_CONFIG["enable_trade_loss_guard"]
        self.max_daily_loss = INSTANT_ENGINE_CONFIG["max_daily_loss"]
        self.max_daily_profit = INSTANT_ENGINE_CONFIG["max_daily_profit"]
        self.max_trade_loss = INSTANT_ENGINE_CONFIG["max_trade_loss"]
        self._last_pnl = 0.0
        self._last_fetch_time = 0

        # Smart TTL config
        self._ttl_idle = 1.0  # no trade → slow
        self._ttl_active = 0.2  # during trade → fast
        self._ttl_burst = 0.05  # rapid events → ultra fast

        # event tracking
        self._last_event_time = 0
        # ------------------------------
        # Configuration Validation
        # ------------------------------
        if self.enable_global_guard:

            if self.max_daily_loss >= 0:
                log("CRITICAL: max_daily_loss must be negative")
                sys.exit()

            if self.max_daily_profit <= 0:
                log("CRITICAL: max_daily_profit must be positive")
                sys.exit()

        if self.enable_trade_guard:

            if self.max_trade_loss >= 0:
                log("CRITICAL: max_trade_loss must be negative")
                sys.exit()

    def calculate_net_pnl(self):

        now = time.time()

        # -------------------------------------------------
        # DETERMINE TTL (SMART)
        # -------------------------------------------------
        ttl = self._ttl_idle

        # If trade active → faster checks
        if self.data_provider:
            positions = self.data_provider.state_store.get_all_positions()
            if any(int(qty) != 0 for qty in positions.values()):
                ttl = self._ttl_active

        # If rapid events → ultra fast
        if now - self._last_event_time < 0.2:
            ttl = self._ttl_burst

        # -------------------------------------------------
        # CACHE CHECK
        # -------------------------------------------------
        if now - self._last_fetch_time < ttl:
            log(f"[RISK] Using cached PnL: {self._last_pnl} | TTL: {ttl}")
            return self._last_pnl

        # -------------------------------------------------
        # FETCH FROM BROKER
        # -------------------------------------------------
        log(f"[RISK] Fetching PnL from broker...")

        positions = self.broker.get_positions()

        total = 0.0

        for p in positions:
            pnl = float(p.get("pnl", 0))

            log(f"[RISK DEBUG] Positions is :{p}")
            log(f"[RISK DEBUG] PnL: {pnl}")

            total += pnl

        log(f"[RISK DEBUG] Total PnL: {round(total, 2)}")

        # -------------------------------------------------
        # UPDATE CACHE
        # -------------------------------------------------
        self._last_pnl = total
        self._last_fetch_time = now

        return total

    def check_trade_level_risk(self, instrument, entry_price, quantity):

        if not self.enable_global_guard:
            return

        if not self.enable_trade_guard:
            return

        # get LTP from data provider
        ltp = self.data_provider.get_ltp(instrument)

        if not ltp or entry_price or self.data_provider is None:
            return

        pnl = (ltp - entry_price) * quantity

        log(f"[MICRO RISK] Trade PnL: {pnl}")

        if pnl <= GLOBAL_CONFIG["max_trade_loss"]:
            log(f"[MICRO RISK] TRADE LOSS LIMIT HIT | PnL: {pnl}")

            # cancel all open orders
            orders = self.broker.get_order_book()
            for o in orders:
                if o.get("status") == "open":
                    try:
                        self.broker.cancel_order(o.get("order_id"))
                    except Exception as e:
                        log(f"[MICRO RISK] Cancel failed: {e}")

            # flatten positions
            self.broker.flatten_and_verify()
            log("[RISK] TRADE SYSTEM EXIT INITIATED")
            sys.exit()


    # =========================================================
    # GLOBAL PnL GUARD
    # =========================================================
    def check_global_pnl(self):

        if not self.enable_global_guard:
            return

        pnl = self.calculate_net_pnl()

        # ------------------------------
        # Loss Breach
        # ------------------------------
        if pnl <= self.max_daily_loss:
            log(f"GLOBAL LOSS LIMIT HIT | PnL: {pnl}")

            # Cancel all open orders first
            orders = self.broker.get_order_book()

            for o in orders:
                if o.get("status") == "open":

                    order_id = o.get("order_id")
                    if not order_id:
                        continue

                    try:
                        self.broker.cancel_order(order_id)
                    except Exception as e:
                        log(f"[RISK] Cancel failed | Order: {order_id} | {e}")

            # Then flatten
            self.broker.flatten_and_verify()
            log("[RISK] LOSS SYSTEM EXIT INITIATED")
            sys.exit()

        # ------------------------------
        # Profit Target Breach
        # ------------------------------
        if pnl >= self.max_daily_profit:
            log(f"GLOBAL PROFIT TARGET HIT | PnL: {pnl}")

            # Cancel all open orders first
            orders = self.broker.get_order_book()

            for o in orders:
                if o.get("status") == "open":

                    order_id = o.get("order_id")
                    if not order_id:
                        continue

                    try:
                        self.broker.cancel_order(order_id)
                    except Exception as e:
                        log(f"[RISK] Cancel failed | Order: {order_id} | {e}")

            # Then flatten
            self.broker.flatten_and_verify()
            log("[RISK] PROFIT SYSTEM EXIT INITIATED")
            sys.exit()