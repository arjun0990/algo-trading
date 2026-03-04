import sys
from core.utils import log
from config import GLOBAL_CONFIG


class RiskEngine:

    def __init__(self, broker):

        self.broker = broker

        self.enable_guard = GLOBAL_CONFIG["enable_global_pnl_guard"]
        self.max_daily_loss = GLOBAL_CONFIG["max_daily_loss"]
        self.max_daily_profit = GLOBAL_CONFIG["max_daily_profit"]

        # ------------------------------
        # Configuration Validation
        # ------------------------------
        if self.enable_guard:

            if self.max_daily_loss >= 0:
                log("CRITICAL: max_daily_loss must be negative")
                sys.exit()

            if self.max_daily_profit <= 0:
                log("CRITICAL: max_daily_profit must be positive")
                sys.exit()

    # =========================================================
    # NET PnL CALCULATION
    # =========================================================
    def calculate_net_pnl(self):

        total = 0.0
        positions = self.broker.get_positions()

        for p in positions:
            total += float(p.get("unrealised_pnl", 0))
            total += float(p.get("realised_pnl", 0))

        return total

    # =========================================================
    # GLOBAL PnL GUARD
    # =========================================================
    def check_global_pnl(self):

        if not self.enable_guard:
            return

        pnl = self.calculate_net_pnl()

        # ------------------------------
        # Loss Breach
        # ------------------------------
        if pnl <= self.max_daily_loss:
            log(f"GLOBAL LOSS LIMIT HIT | PnL: {pnl}")
            self.broker.flatten_and_verify()
            sys.exit()

        # ------------------------------
        # Profit Target Breach
        # ------------------------------
        if pnl >= self.max_daily_profit:
            log(f"GLOBAL PROFIT TARGET HIT | PnL: {pnl}")
            self.broker.flatten_and_verify()
            sys.exit()