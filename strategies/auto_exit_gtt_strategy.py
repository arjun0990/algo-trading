# strategies/auto_exit_gtt_strategy.py

import time
import keyboard
from config import AUTO_EXIT_GTT_CONFIG as CONFIG
from core.utils import log


class AutoExitGTTStrategy:

    def __init__(self):

        self.trade_active = False
        self.active_instrument = None

        # Two separate GTT IDs
        self.target_gtt_id = None
        self.sl_gtt_id = None

        self.last_check_time = 0
        self.check_interval = CONFIG["position_check_interval"]

        # Kill switch debounce
        self.last_key_time = 0
        self.key_cooldown = 0.5

    # -------------------------------------------------
    # MAIN LOOP
    # -------------------------------------------------
    def run(self, broker, market_data, risk_engine, instruments):

        now = time.time()
        self._handle_kill_switch(broker)

        if now - self.last_check_time < self.check_interval:
            return

        self.last_check_time = now

        if not self.trade_active:
            self._detect_new_position(broker)
        else:
            self._monitor_position(broker)

    # -------------------------------------------------
    # Detect Manual Entry
    # -------------------------------------------------
    def _detect_new_position(self, broker):

        if self.trade_active:
            return

        positions = broker.get_positions()
        if not positions:
            return

        for p in positions:

            qty = int(p.get("quantity", 0))
            if qty == 0:
                continue

            instrument = p.get("instrument_token")
            product = p.get("product", "D")

            log(f"[AUTO_EXIT_GTT] Open Position | Instrument: {instrument} | Qty: {qty}")

            # -------------------------------------------------
            # Strong Duplicate Protection
            # -------------------------------------------------
            existing = self._get_existing_exit_gtts(broker, instrument)

            if existing:
                log("[AUTO_EXIT_GTT] Existing Exit GTTs Found → Linking State")
                self.trade_active = True
                self.active_instrument = instrument
                self.target_gtt_id = existing.get("TARGET")
                self.sl_gtt_id = existing.get("STOPLOSS")
                return

            # -------------------------------------------------
            # Fetch entry price safely
            # -------------------------------------------------
            entry_price = self._get_last_completed_buy(
                broker,
                instrument,
                abs(qty)
            )

            if not entry_price:
                log("[AUTO_EXIT_GTT] WARNING: Could not determine entry price safely.")
                return

            log(f"[AUTO_EXIT_GTT] Entry Matched | Price: {entry_price}")

            # -------------------------------------------------
            # Place Exit GTTs
            # -------------------------------------------------
            log("[AUTO_EXIT_GTT] Stabilizing position before GTT placement...")
            time.sleep(0.5)
            success = self._place_exit_gtts(
                broker,
                instrument,
                entry_price,
                abs(qty),
                product
            )

            if success:
                self.trade_active = True
                self.active_instrument = instrument

            return

    # -------------------------------------------------
    # 🔴 KILL SWITCH (Force Exit Everything)
    # -------------------------------------------------
    def _handle_kill_switch(self, broker):

        now = time.time()

        if now - self.last_key_time < self.key_cooldown:
            return

        if keyboard.is_pressed("q"):

            self.last_key_time = now

            log("[AUTO_EXIT_GTT] 🚨 KILL SWITCH ACTIVATED")

            # Cancel Target GTT
            if self.target_gtt_id:
                broker.cancel_gtt_order(self.target_gtt_id)

            # Cancel SL GTT
            if self.sl_gtt_id:
                broker.cancel_gtt_order(self.sl_gtt_id)

            # Cancel ALL pending orders
            broker.cancel_all_pending_orders()

            # Exit ALL positions
            broker.exit_all_positions()

            log("[AUTO_EXIT_GTT] All GTTs Cancelled")
            log("[AUTO_EXIT_GTT] All Positions Exited")

            # Reset state
            self.trade_active = False
            self.active_instrument = None
            self.target_gtt_id = None
            self.sl_gtt_id = None

            log("[AUTO_EXIT_GTT] Strategy State Reset")

    # -------------------------------------------------
    # STRONG Existing Exit GTT Detection
    # -------------------------------------------------
    def _get_existing_exit_gtts(self, broker, instrument):

        gtts = broker.get_all_gtt_orders()
        if not gtts:
            return None

        found = {}

        for g in gtts:

            status = g.get("status", "").upper()
            if status not in ["ACTIVE", "TRIGGER_PENDING"]:
                continue

            if g.get("instrument_token") != instrument:
                continue

            rules = g.get("rules", [])
            if not rules:
                continue

            rule = rules[0]
            trigger_type = rule.get("trigger_type")

            if trigger_type == "ABOVE":
                found["TARGET"] = g.get("gtt_order_id")

            elif trigger_type == "BELOW":
                found["STOPLOSS"] = g.get("gtt_order_id")

        return found if found else None

    # -------------------------------------------------
    # Safe Last Completed BUY Fetch
    # -------------------------------------------------
    def _get_last_completed_buy(self, broker, instrument_token, open_quantity):

        orders = broker.get_order_book()
        if not orders:
            return None

        valid_buys = []

        for order in orders:

            if order.get("status", "").lower() != "complete":
                continue

            if order.get("transaction_type") != "BUY":
                continue

            if order.get("instrument_token") != instrument_token:
                continue

            valid_buys.append(order)

        if not valid_buys:
            return None

        valid_buys.sort(
            key=lambda x: x.get("exchange_timestamp", ""),
            reverse=True
        )

        latest_buy = valid_buys[0]
        entry_price = latest_buy.get("average_price")

        if not entry_price or float(entry_price) <= 0:
            return None

        return float(entry_price)

    # -------------------------------------------------
    # Place TWO SINGLE GTTs
    # -------------------------------------------------
    def _place_exit_gtts(self, broker, instrument, entry_price, quantity, product):

        max_allowed = CONFIG.get("max_gtt_quantity", 1755)

        if quantity > max_allowed:
            log(f"[AUTO_EXIT_GTT] Quantity {quantity} exceeds max GTT limit {max_allowed}")
            quantity = max_allowed

        target_price = round(entry_price + CONFIG["target_points"], 2)
        sl_price = round(entry_price - CONFIG["sl_points"], 2)

        log(
            f"[AUTO_EXIT_GTT] Placing Exit GTTs | "
            f"Entry: {entry_price} | Target: {target_price} | "
            f"SL: {sl_price} | Qty: {quantity}"
        )

        # TARGET GTT
        target_payload = {
            "type": "SINGLE",
            "quantity": quantity,
            "product": product,
            "instrument_token": instrument,
            "transaction_type": "SELL",
            "rules": [{
                "strategy": "ENTRY",
                "trigger_type": "ABOVE",
                "trigger_price": target_price
            }]
        }

        target_id = broker.place_gtt_order(target_payload)

        if not target_id:
            log("[AUTO_EXIT_GTT] Target GTT failed. Retrying once...")
            time.sleep(0.5)
            target_id = broker.place_gtt_order(target_payload)

        if not target_id:
            log("[AUTO_EXIT_GTT] ERROR: Target GTT Placement Failed")
            return False

        # STOPLOSS GTT
        sl_payload = {
            "type": "SINGLE",
            "quantity": quantity,
            "product": product,
            "instrument_token": instrument,
            "transaction_type": "SELL",
            "rules": [{
                "strategy": "ENTRY",
                "trigger_type": "BELOW",
                "trigger_price": sl_price
            }]
        }

        sl_id = broker.place_gtt_order(sl_payload)

        if not sl_id:
            log("[AUTO_EXIT_GTT] SL GTT failed. Retrying once...")
            time.sleep(0.5)
            sl_id = broker.place_gtt_order(sl_payload)

        if not sl_id:
            log("[AUTO_EXIT_GTT] ERROR: SL GTT Failed → Cancelling Target")
            broker.cancel_gtt_order(target_id)
            return False

        self.target_gtt_id = target_id
        self.sl_gtt_id = sl_id

        log(f"[AUTO_EXIT_GTT] Target GTT Placed | ID: {target_id}")
        log(f"[AUTO_EXIT_GTT] SL GTT Placed | ID: {sl_id}")

        return True

    # -------------------------------------------------
    # Monitor Position
    # -------------------------------------------------
    def _monitor_position(self, broker):

        positions = broker.get_positions()

        still_open = False

        for p in positions:
            if (
                p.get("instrument_token") == self.active_instrument
                and int(p.get("quantity", 0)) != 0
            ):
                still_open = True
                break

        # Position closed (Target / SL / Manual)
        if not still_open:

            log("[AUTO_EXIT_GTT] Position Closed → Resetting Strategy State")

            if self.target_gtt_id:
                broker.cancel_gtt_order(self.target_gtt_id)

            if self.sl_gtt_id:
                broker.cancel_gtt_order(self.sl_gtt_id)

            self.trade_active = False
            self.active_instrument = None
            self.target_gtt_id = None
            self.sl_gtt_id = None