# strategies/auto_exit_gtt_strategy.py

import time
import keyboard
from config import AUTO_EXIT_GTT_CONFIG as CONFIG
from core.utils import log
from config import AUTO_EXIT_GTT_CONFIG as CONFIG, ACTIVE_INDEX, INDEX_CONFIG

class AutoExitGTTStrategy:

    def __init__(self):

        self.trade_active = False
        self.active_instrument = None

        # Two separate GTT IDs
        self.target_gtt_id = None
        self.sl_gtt_id = None

        # self.last_check_time = 0
        # self.check_interval = CONFIG["position_check_interval"]

        # Kill switch debounce
        self.last_key_time = 0
        self.key_cooldown = 0.5

        self.processing_instruments = set()
        self.processed_positions = set()

    # -------------------------------------------------
    # MAIN LOOP
    # -------------------------------------------------
    def run(self, broker, market_data, risk_engine, instruments):

        self._handle_kill_switch(broker)

        state_store = broker.data_provider.state_store

        # Only react if something changed
        position_changed = state_store.consume_position_changed()
        order_changed = state_store.consume_order_changed()

        if not position_changed and not order_changed:
            return

        if not self.trade_active:
            self._detect_new_position(broker)
        else:
            self._monitor_position(broker)
    # -------------------------------------------------
    # Detect Manual Entry (STREAM-DRIVEN)
    # -------------------------------------------------
    def _detect_new_position(self, broker):
        state_store = broker.data_provider.state_store

        if getattr(state_store, "manual_trade_active", False):
            return
        if self.trade_active:
            return

        # STREAM-DRIVEN POSITIONS
        state_store = broker.data_provider.state_store

        if getattr(state_store, "manual_trade_active", False):
            return

        positions = state_store.get_all_positions()

        if not positions:
            return

        for instrument, qty in positions.items():

            if instrument in self.processing_instruments:
                continue

            if instrument in self.processed_positions:
                continue

            qty = int(qty)

            if qty == 0:
                continue


            # self.processing_instruments.add(instrument)

            product = "D"  # product not available in stream map

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
            log(f"[AUTO_EXIT_GTT] Open Position | Instrument: {instrument} | Qty: {qty}")
            # DEBUG — check if order stream arrived
            print("ORDERS STREAM:", broker.data_provider.state_store.get_all_orders())
            # -------------------------------------------------
            # Fetch entry price safely (still REST-based)
            # -------------------------------------------------
    # -------------------------------------------------------------------------------
            orders = broker.data_provider.state_store.get_all_orders()

            latest_order_price = None

            for o in orders.values():

                if o.get("instrument_token") != instrument:
                    continue

                if o.get("transaction_type") != "BUY":
                    continue

                if o.get("status", "").lower() != "complete":
                    continue

                latest_order_price = float(o.get("average_price", 0))

            if not latest_order_price:
                return

            entry_price = latest_order_price

            if not entry_price or entry_price <= 0:
                log("[AUTO_EXIT_GTT] Could not determine entry price from position")
                continue
    #----------------------------------------------------------------------------------
            # entry_price = self._get_last_completed_buy(
            #     broker,
            #     instrument,
            #     abs(qty)
            # )
            #
            # if not entry_price:
            #     log("[AUTO_EXIT_GTT] Waiting for order stream to determine entry price...")
            #     continue

            log(f"[AUTO_EXIT_GTT] Entry Matched | Price: {entry_price}")
            self.processing_instruments.add(instrument)
            # -------------------------------------------------
            # Stabilization delay
            # -------------------------------------------------
            log("[AUTO_EXIT_GTT] Stabilizing position before GTT placement...")
            # time.sleep(0.5)

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
                self.processed_positions.add(instrument)
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

            if self.target_gtt_id:
                broker.cancel_gtt_order(self.target_gtt_id)

            if self.sl_gtt_id:
                broker.cancel_gtt_order(self.sl_gtt_id)

            broker.cancel_all_pending_orders()
            broker.exit_all_positions()

            log("[AUTO_EXIT_GTT] All GTTs Cancelled")
            log("[AUTO_EXIT_GTT] All Positions Exited")

            self.trade_active = False
            self.active_instrument = None
            self.target_gtt_id = None
            self.sl_gtt_id = None
            self.processing_instruments.clear()
            self.processed_positions.clear()

            log("[AUTO_EXIT_GTT] Strategy State Reset")

    # -------------------------------------------------
    # STRONG Existing Exit GTT Detection (STREAM-DRIVEN)
    # -------------------------------------------------
    def _get_existing_exit_gtts(self, broker, instrument):

        state_store = broker.data_provider.state_store
        all_orders = state_store.get_all_orders()

        if not all_orders:
            return None

        found = {}

        for g in all_orders.values():

            # Only consider GTT updates
            if not g.get("gtt_order_id"):
                continue

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
    # Safe Last Completed BUY Fetch (REST kept intentionally)
    # -------------------------------------------------
    def _get_last_completed_buy(self, broker, instrument_token, open_quantity):

        # STREAM-DRIVEN ORDERS
        orders_dict = broker.data_provider.state_store.get_all_orders()

        if not orders_dict:
            return None

        valid_buys = []

        for order in orders_dict.values():

            if order.get("status", "").lower() != "complete":
                continue

            if order.get("transaction_type") != "BUY":
                continue

            if order.get("instrument_token") != instrument_token:
                continue

            valid_buys.append(order)

        if not valid_buys:
            return None

        # Sort newest first
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
    # Place TWO SINGLE GTTs (UNCHANGED)
    # -------------------------------------------------
    def _place_exit_gtts(self, broker, instrument, entry_price, quantity, product):
        state_store = broker.data_provider.state_store

        if getattr(state_store, "manual_trade_active", False):
            return False
        max_allowed = INDEX_CONFIG[ACTIVE_INDEX]["max_gtt_quantity"]

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

        # -------------------------------------------------
        # TARGET GTT
        # -------------------------------------------------
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
            target_id = broker.place_gtt_order(target_payload)

        if not target_id:
            log("[AUTO_EXIT_GTT] ERROR: Target GTT Placement Failed")

            # Release duplicate protection lock
            self.processing_instruments.discard(instrument)

            return False

        # -------------------------------------------------
        # STOPLOSS GTT
        # -------------------------------------------------
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
            sl_id = broker.place_gtt_order(sl_payload)

        if not sl_id:
            log("[AUTO_EXIT_GTT] ERROR: SL GTT Failed → Cancelling Target")

            broker.cancel_gtt_order(target_id)

            # Release duplicate protection lock
            self.processing_instruments.discard(instrument)

            return False

        # -------------------------------------------------
        # SUCCESS
        # -------------------------------------------------
        self.target_gtt_id = target_id
        self.sl_gtt_id = sl_id

        log(f"[AUTO_EXIT_GTT] Target GTT Placed | ID: {target_id}")
        log(f"[AUTO_EXIT_GTT] SL GTT Placed | ID: {sl_id}")

        # Release duplicate protection lock
        self.processing_instruments.discard(instrument)

        return True
    # def _place_exit_gtts(self, broker, instrument, entry_price, quantity, product):
    #
    #     max_allowed = CONFIG.get("max_gtt_quantity", 1755)
    #
    #     if quantity > max_allowed:
    #         log(f"[AUTO_EXIT_GTT] Quantity {quantity} exceeds max GTT limit {max_allowed}")
    #         quantity = max_allowed
    #
    #     target_price = round(entry_price + CONFIG["target_points"], 2)
    #     sl_price = round(entry_price - CONFIG["sl_points"], 2)
    #
    #     log(
    #         f"[AUTO_EXIT_GTT] Placing Exit GTTs | "
    #         f"Entry: {entry_price} | Target: {target_price} | "
    #         f"SL: {sl_price} | Qty: {quantity}"
    #     )
    #
    #     target_payload = {
    #         "type": "SINGLE",
    #         "quantity": quantity,
    #         "product": product,
    #         "instrument_token": instrument,
    #         "transaction_type": "SELL",
    #         "rules": [{
    #             "strategy": "ENTRY",
    #             "trigger_type": "ABOVE",
    #             "trigger_price": target_price
    #         }]
    #     }
    #
    #     target_id = broker.place_gtt_order(target_payload)
    #
    #     if not target_id:
    #         log("[AUTO_EXIT_GTT] Target GTT failed. Retrying once...")
    #         # time.sleep(0.5)
    #         target_id = broker.place_gtt_order(target_payload)
    #
    #     if not target_id:
    #         log("[AUTO_EXIT_GTT] ERROR: Target GTT Placement Failed")
    #         return False
    #
    #     sl_payload = {
    #         "type": "SINGLE",
    #         "quantity": quantity,
    #         "product": product,
    #         "instrument_token": instrument,
    #         "transaction_type": "SELL",
    #         "rules": [{
    #             "strategy": "ENTRY",
    #             "trigger_type": "BELOW",
    #             "trigger_price": sl_price
    #         }]
    #     }
    #
    #     sl_id = broker.place_gtt_order(sl_payload)
    #
    #     if not sl_id:
    #         log("[AUTO_EXIT_GTT] SL GTT failed. Retrying once...")
    #         # time.sleep(0.5)
    #         sl_id = broker.place_gtt_order(sl_payload)
    #
    #     if not sl_id:
    #         log("[AUTO_EXIT_GTT] ERROR: SL GTT Failed → Cancelling Target")
    #         broker.cancel_gtt_order(target_id)
    #         return False
    #
    #     self.target_gtt_id = target_id
    #     self.sl_gtt_id = sl_id
    #
    #     log(f"[AUTO_EXIT_GTT] Target GTT Placed | ID: {target_id}")
    #     log(f"[AUTO_EXIT_GTT] SL GTT Placed | ID: {sl_id}")
    #
    #     return True

    # -------------------------------------------------
    # Monitor Position (STREAM-DRIVEN)
    # -------------------------------------------------
    def _monitor_position(self, broker):

        positions = broker.data_provider.state_store.get_all_positions()

        qty = positions.get(self.active_instrument, 0)

        still_open = int(qty) != 0

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
            self.processing_instruments.clear()
            self.processed_positions.clear()