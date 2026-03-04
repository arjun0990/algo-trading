import sys
import time
from datetime import datetime

from core.utils import log, round_to_tick, manual_exit_pressed
from config import (
    ACTIVE_STRATEGY,
    GLOBAL_CONFIG,
    BOUNCE_CONFIG,
    PIVOT_CONFIG
)


class ExecutionEngine:

    def __init__(self, broker, risk_engine):

        self.broker = broker
        self.risk_engine = risk_engine
        self.lot_size = GLOBAL_CONFIG["lot_size"]
        self.active_trade = False

    # =========================================================
    # STRATEGY CONFIG LOADER
    # =========================================================
    def get_strategy_config(self, strategy_name):

        if strategy_name == "BOUNCE":
            return BOUNCE_CONFIG
        elif strategy_name == "PIVOT":
            return PIVOT_CONFIG
        else:
            log(f"CRITICAL: Unknown strategy {strategy_name}")
            sys.exit()

    # =========================================================
    # POSITION CHECK
    # =========================================================
    def has_open_position(self):

        positions = self.broker.get_positions()

        active = [
            p for p in positions
            if int(p.get("quantity", 0)) != 0
        ]

        return len(active) > 0

    # =========================================================
    # EXECUTE
    # =========================================================
    def execute(self, signal):

        strategy_name = signal["strategy_name"]
        strategy_config = self.get_strategy_config(strategy_name)

        total_lots = strategy_config["lots"]
        total_qty = total_lots * self.lot_size

        if self.active_trade or self.has_open_position():
            log("BLOCKED: Existing position detected")
            return

        instrument_key = signal["instrument_key"]
        entry_price = round_to_tick(signal["entry_price"])
        low_reference = signal["initial_sl_reference"]

        if GLOBAL_CONFIG["enable_global_pnl_guard"]:
            self.risk_engine.check_global_pnl()

        log(f"ENTRY ATTEMPT | Strategy: {strategy_name} | Lots: {total_lots}")

        # =====================================================
        # ENTRY ORDER
        # =====================================================

        entry_payload = {
            "quantity": total_qty,
            "product": GLOBAL_CONFIG["product_type"],
            "validity": GLOBAL_CONFIG["validity"],
            "instrument_token": instrument_key,
            "order_type": "LIMIT",
            "transaction_type": "BUY",
            "price": entry_price
        }

        print("ENTRY PAYLOAD:", entry_payload)

        order = self.broker.place_order(entry_payload)

        if order.get("status") != "success":
            log("ENTRY FAILED")
            return

        order_id = order["data"]["order_id"]
        entry_start = datetime.now()

        # =====================================================
        # ENTRY CONFIRMATION LOOP
        # =====================================================
        while True:

            self.risk_engine.check_global_pnl()

            if GLOBAL_CONFIG["manual_exit_enabled"] and manual_exit_pressed():
                try:
                    self.broker.cancel_order(order_id)
                except:
                    pass
                return

            status = self.broker.get_order_status(order_id)

            if status == "COMPLETE":
                break

            if status in ["REJECTED", "CANCELLED"]:
                log("ENTRY REJECTED")
                return

            if status == "OPEN":

                ltp_data = self.broker.safe_request(
                    "GET",
                    f"{self.broker.BASE_URL}/market-quote/ltp",
                    params={"instrument_key": instrument_key}
                )

                if ltp_data.get("status") == "success":
                    ltp = list(ltp_data["data"].values())[0]["last_price"]

                    if ltp > entry_price + GLOBAL_CONFIG["max_entry_chase"]:
                        log("ENTRY CHASE LIMIT BREACHED - CANCELLED")
                        try:
                            self.broker.cancel_order(order_id)
                        except:
                            pass
                        return

            if (datetime.now() - entry_start).total_seconds() > GLOBAL_CONFIG["entry_timeout_seconds"]:
                log("ENTRY TIMEOUT")

                try:
                    current_status = self.broker.get_order_status(order_id)

                    if current_status == "OPEN":
                        self.broker.cancel_order(order_id)
                except:
                    pass

                return

            time.sleep(1)

        self.active_trade = True

        # =====================================================
        # SL CALCULATION
        # =====================================================

        if strategy_config["use_fixed_sl"]:
            sl_price = round_to_tick(
                entry_price - strategy_config["fixed_sl_points"]
            )
        else:
            sl_price = round_to_tick(
                low_reference - GLOBAL_CONFIG["sl_buffer"]
            )

        sl_payload = {
            "quantity": total_qty,
            "product": GLOBAL_CONFIG["product_type"],
            "validity": GLOBAL_CONFIG["validity"],
            "instrument_token": instrument_key,
            "order_type": "SL-M",
            "transaction_type": "SELL",
            "trigger_price": sl_price
        }

        print("SL PAYLOAD:", sl_payload)

        sl_order = self.broker.place_order(sl_payload)

        if sl_order.get("status") != "success":
            log("SL FAILED")
            self.broker.flatten_and_verify()
            return

        sl_id = sl_order["data"]["order_id"]

        partial_enabled = strategy_config["partial_exit_enabled"]
        complete_only = strategy_config["complete_exit_only"]

        trade_start = datetime.now()

        log(f"TRADE ACTIVE | SL: {sl_price}")

        # =====================================================
        # TRADE LOOP
        # =====================================================
        while True:

            self.risk_engine.check_global_pnl()

            live_qty = self.broker.get_position_qty(instrument_key)

            if live_qty <= 0:
                log("TRADE CLOSED")
                self.active_trade = False
                return

            # =================================================
            # TIME EXIT
            # =================================================
            elapsed = (datetime.now() - trade_start).total_seconds() / 60

            if elapsed >= GLOBAL_CONFIG["max_trade_duration_minutes"]:
                log("TIME EXIT")
                self.broker.cancel_order(sl_id)
                self.broker.flatten_and_verify()
                self.active_trade = False
                return

            # =================================================
            # PARTIAL EXIT LOGIC
            # =================================================
            if partial_enabled and not complete_only:

                ltp_data = self.broker.safe_request(
                    "GET",
                    f"{self.broker.BASE_URL}/market-quote/ltp",
                    params={"instrument_key": instrument_key}
                )

                if ltp_data.get("status") != "success":
                    time.sleep(1)
                    continue

                ltp = list(ltp_data["data"].values())[0]["last_price"]

                # Simple example: breakeven shift at +20
                if ltp >= entry_price + 20:

                    log("SL SHIFT TO BREAKEVEN")

                    try:
                        self.broker.cancel_order(sl_id)
                    except:
                        pass

                    sl_price = entry_price

                    sl_payload["trigger_price"] = sl_price

                    sl_order = self.broker.place_order(sl_payload)

                    if sl_order.get("status") != "success":
                        log("SL SHIFT FAILED")
                        self.broker.flatten_and_verify()
                        return

                    sl_id = sl_order["data"]["order_id"]

                    partial_enabled = False  # shift only once

            time.sleep(1)