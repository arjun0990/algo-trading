import time
import keyboard

from core.utils import log, round_to_tick
from config import INSTANT_ENGINE_CONFIG as CONFIG

class PositionExitEngine:


 def __init__(self):

    self.trade_active = False
    self.active_instrument = None

    self.target_order_id = None
    self.sl_order_id = None

    self.last_key_time = 0
    self.key_cooldown = 0.5

    self.processing_instruments = set()
    self.processed_positions = set()

    self.last_entry_price = None
    self.last_entry_instrument = None
    # NEW
    self.auto_exit_enabled = True

    self.partial_fill_time = None
    self.partial_fill_order_id = None
    self.partial_filled_qty = 0

    self.partial_exit_in_progress = False
    self.position_detect_time = None
# -------------------------------------------------
# MAIN LOOP
# -------------------------------------------------

 def run(self, broker, market_data, risk_engine, instruments):

    self._handle_kill_switch(broker)
    self._handle_exit_toggle(broker)
    state_store = broker.data_provider.state_store

    position_changed = state_store.consume_position_changed()
    order_changed = state_store.consume_order_changed()
    if order_changed:

        orders = state_store.get_all_orders()

        for o in orders.values():

            if o.get("transaction_type") != "BUY":
                continue

            order_qty = int(o.get("quantity", 0))
            filled_qty = int(o.get("filled_quantity", 0))
            pending_qty = int(o.get("pending_quantity", 0))

            # Detect partial fill
            if filled_qty > 0 and pending_qty > 0:

                if self.partial_fill_order_id != o.get("order_id"):
                    self.partial_fill_order_id = o.get("order_id")
                    self.partial_fill_time = time.time()
                    self.partial_filled_qty = filled_qty

            if o.get("status", "").lower() != "complete":
                continue

            instrument = o.get("instrument_token")

            if not instrument:
                continue

            price = float(o.get("average_price", 0))

            if price <= 0:
                continue

            self.last_entry_price = price
            self.last_entry_instrument = instrument
    # -----------------------------------
    # Handle partial fill timeout
    # -----------------------------------

    if self.partial_fill_time:

        if time.time() - self.partial_fill_time > 3:

            orders = state_store.get_all_orders()

            order = orders.get(self.partial_fill_order_id)

            if order:

                pending_qty = int(order.get("pending_quantity", 0))
                filled_qty = int(order.get("filled_quantity", 0))

                if pending_qty > 0:

                    log("[EXIT_ENGINE] Partial fill timeout → cancelling remaining qty")

                    broker.cancel_order(self.partial_fill_order_id)

                    instrument = order.get("instrument_token")

                    entry_price = float(order.get("average_price", 0))

                    if filled_qty > 0 and entry_price > 0:
                        self.partial_exit_in_progress = True
                        self._place_bracket_orders(
                            broker,
                            instrument,
                            entry_price,
                            filled_qty,
                            "D"
                        )

            self.partial_fill_time = None
            self.partial_fill_order_id = None
            self.partial_filled_qty = 0

    if self.auto_exit_enabled:
        # fast detection via order stream
        if order_changed and not self.trade_active:
            self._detect_new_position(broker)

        # universal detection via position stream (console trades)
        if position_changed and not self.trade_active:
            self._detect_new_position(broker)

    # monitor exit once trade active
    if position_changed and self.trade_active:
        self._monitor_position(broker)


# -------------------------------------------------
# Detect New Position (STREAM DRIVEN)
# -------------------------------------------------

 def _detect_new_position(self, broker):

     if self.trade_active or self.partial_exit_in_progress:
         return

     state_store = broker.data_provider.state_store

     positions = state_store.get_all_positions()

     if not positions:
         return

     from datetime import datetime
     self.position_detect_time = datetime.now()

     for instrument, qty in positions.items():

         # Prevent duplicate trigger while trade active
         if instrument == self.active_instrument:
             continue

         if instrument in self.processing_instruments:
             continue

         if instrument in self.processed_positions:
             continue

         qty = int(qty)

         if qty == 0:
             continue

         log(f"[EXIT_ENGINE] Open Position | Instrument: {instrument} | Qty: {qty}")

         # ===============================
         # CASE 1: ENTRY FROM THIS ENGINE
         # ===============================
         if instrument == self.last_entry_instrument and self.last_entry_price is not None:

             orders = state_store.get_all_orders()

             valid_buys = []

             for o in orders.values():

                 if o.get("instrument_token") != instrument:
                     continue

                 if o.get("transaction_type") != "BUY":
                     continue

                 valid_buys.append(o)

             if not valid_buys:
                 return

             valid_buys.sort(
                 key=lambda x: (
                     x.get("exchange_timestamp") or "",
                     x.get("order_timestamp") or ""
                 ),
                 reverse=True
             )

             latest = valid_buys[0]

             if not latest:
                 return

             pending_qty = int(latest.get("pending_quantity", 0))
             filled_qty = int(latest.get("filled_quantity", 0))
             order_qty = int(latest.get("quantity", 0))

             # 🔴 DO NOT PROCEED UNTIL ENTRY FULLY FILLED
             if pending_qty != 0:
                 return

             if filled_qty != order_qty:
                 return

             # 🔴 ALSO ENSURE POSITION MATCHES FULL ORDER
             if filled_qty != abs(qty):
                 return

             entry_price = self.last_entry_price

         # =================================
         # CASE 2: MANUAL / MOBILE / CONSOLE
         # =================================
         else:

             entry_price = None

             orders = state_store.get_all_orders()

             valid_buys = []

             for o in orders.values():

                 if o.get("instrument_token") != instrument:
                     continue

                 if o.get("transaction_type") != "BUY":
                     continue

                 if o.get("status", "").lower() != "complete":
                     continue

                 valid_buys.append(o)

             valid_buys = [
                 o for o in valid_buys
                 if o.get("status", "").lower() == "complete"
             ]

             if not valid_buys:
                 return

             valid_buys.sort(
                 key=lambda x: (
                     x.get("exchange_timestamp") or "",
                     x.get("order_timestamp") or ""
                 ),
                 reverse=True
             )

             latest_buy = None

             position_qty = abs(qty)

             for o in valid_buys:

                 order_qty = int(o.get("quantity", 0))
                 filled_qty = int(o.get("filled_quantity", 0))
                 pending_qty = int(o.get("pending_quantity", 0))

                 # 🔴 Skip partial fills
                 if pending_qty != 0:
                     continue

                 if filled_qty != order_qty:
                     continue

                 if filled_qty != position_qty:
                     continue

                 ts = o.get("exchange_timestamp")

                 if ts and self.position_detect_time:

                     from datetime import datetime, timedelta

                     order_time = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")

                     # 🔴 Ignore old trades
                     if order_time < (self.position_detect_time - timedelta(seconds=60)):
                         continue

                 latest_buy = o
                 break

             if not latest_buy:
                 return
             if int(latest_buy.get("pending_quantity", 0)) != 0:
                 return
             order_qty = int(latest_buy.get("quantity", 0))
             filled_qty = int(latest_buy.get("filled_quantity", 0))
             pending_qty = int(latest_buy.get("pending_quantity", 0))

             if pending_qty != 0:
                 return

             if filled_qty != order_qty:
                 return

             if filled_qty != position_qty:
                 return

             entry_price = float(latest_buy.get("average_price", 0))

             if entry_price <= 0:
                 return

             positions = state_store.get_all_positions()

             if int(positions.get(instrument, 0)) == 0:
                 return

             if not entry_price or entry_price <= 0:
                 log("[EXIT_ENGINE] Could not determine entry price")
                 continue

         log(f"[EXIT_ENGINE] Entry Matched | Price: {entry_price}")

         # 🔒 prevent duplicate exit placements
         if instrument in self.processed_positions:
             return

         self.processing_instruments.add(instrument)

         success = self._place_bracket_orders(
             broker,
             instrument,
             entry_price,
             abs(qty),
             "D"
         )

         if success:
             self.trade_active = True
             self.active_instrument = instrument
             self.processed_positions.add(instrument)

         return

 def _handle_exit_toggle(self, broker):

     now = time.time()

     if now - self.last_key_time < self.key_cooldown:
         return

     # Pause auto exits
     if keyboard.is_pressed("x"):

         self.last_key_time = now
         self.auto_exit_enabled = False

         log("[EXIT_ENGINE] AUTO EXIT PAUSED")

     # Resume auto exits
     elif keyboard.is_pressed("r"):

         self.last_key_time = now
         self.auto_exit_enabled = True

         log("[EXIT_ENGINE] 🚨 KILL SWITCH ACTIVATED")

         if self.target_order_id:
             broker.cancel_order(self.target_order_id)

         if self.sl_order_id:
             broker.cancel_order(self.sl_order_id)

         broker.cancel_all_pending_orders()
         broker.exit_all_positions()

         log("[EXIT_ENGINE] All exits cancelled")
         log("[EXIT_ENGINE] All positions exited")

         self.trade_active = False
         self.active_instrument = None
         self.target_order_id = None
         self.sl_order_id = None
         self.last_entry_price = None
         self.last_entry_instrument = None
         self.processing_instruments.clear()
         self.processed_positions.clear()
         self.position_detect_time = None
         log("[EXIT_ENGINE] AUTO EXIT RESUMED")
# -------------------------------------------------
# 🔴 KILL SWITCH
# -------------------------------------------------

 def _handle_kill_switch(self, broker):

    now = time.time()

    if now - self.last_key_time < self.key_cooldown:
        return

    if keyboard.is_pressed("q"):

        self.last_key_time = now

        log("[EXIT_ENGINE] 🚨 KILL SWITCH ACTIVATED")

        if self.target_order_id:
            broker.cancel_order(self.target_order_id)

        if self.sl_order_id:
            broker.cancel_order(self.sl_order_id)

        broker.cancel_all_pending_orders()
        broker.exit_all_positions()

        log("[EXIT_ENGINE] All exits cancelled")
        log("[EXIT_ENGINE] All positions exited")

        self.trade_active = False
        self.active_instrument = None
        self.target_order_id = None
        self.sl_order_id = None
        self.last_entry_price = None
        self.last_entry_instrument = None
        self.processing_instruments.clear()
        self.processed_positions.clear()

        self.position_detect_time = None
# -------------------------------------------------
# Place Bracket Orders (REPLACED GTT)
# -------------------------------------------------

 def _place_bracket_orders(self, broker, instrument, entry_price, quantity, product):
    state_store = broker.data_provider.state_store
    current_positions = state_store.get_all_positions()

    # if int(current_positions.get(instrument, 0)) != quantity:
    #      return False
    qty1 = int(current_positions.get(instrument, 0))

    time.sleep(0.1)

    current_positions = state_store.get_all_positions()
    qty2 = int(current_positions.get(instrument, 0))

    if qty1 != qty2:
        return False

    if qty2 != quantity:
        return False
    target_price = round_to_tick(entry_price + CONFIG["target_points"])
    sl_price = round_to_tick(entry_price - CONFIG["sl_points"])



    log(
        f"[EXIT_ENGINE] Placing Bracket | "
        f"Entry: {entry_price} | Target: {target_price} | "
        f"SL: {sl_price} | Qty: {quantity}"
    )

    # TARGET LIMIT

    payload = {
        "quantity": quantity,
        "product": product,
        "validity": "DAY",
        "price": target_price,
        "instrument_token": instrument,
        "order_type": "LIMIT",
        "transaction_type": "SELL",
        "disclosed_quantity": 0,
        "trigger_price": 0,
        "is_amo": False,
        "slice": True,
        "tag": "TARGET_EXIT"
    }

    target_id = broker.place_order(payload)

    if not target_id:
        log("[EXIT_ENGINE] Target order failed. Retrying...")
        target_id = broker.place_order({
        "quantity": quantity,
        "product": product,
        "validity": "DAY",
        "price": target_price,
        "instrument_token": instrument,
        "order_type": "LIMIT",
        "transaction_type": "SELL",
        "disclosed_quantity": 0,
        "trigger_price": 0,
        "is_amo": False,
        "slice": True,
        "tag": "TARGET_EXIT"
    })

    if not target_id:
        log("[EXIT_ENGINE] ERROR: Target order failed")

        self.processing_instruments.discard(instrument)

        return False

    # STOPLOSS SL-M

    payload = {
        "quantity": quantity,
        "product": product,
        "validity": "DAY",
        # "price": 0,
        "instrument_token": instrument,
        "order_type": "SL-M",
        "transaction_type": "SELL",
        "disclosed_quantity": 0,
        "trigger_price": sl_price,
        "is_amo": False,
        "slice": True,
        "tag": "SL_EXIT"
    }

    # sl_id = broker.place_order(payload)
    sl_id = None

    # if not sl_id:
    #     log("[EXIT_ENGINE] SL order failed. Retrying...")
    #     sl_id = broker.place_order({
    #     "quantity": quantity,
    #     "product": product,
    #     "validity": "DAY",
    #     # "price": 0,
    #     "instrument_token": instrument,
    #     "order_type": "SL-M",
    #     "transaction_type": "SELL",
    #     "disclosed_quantity": 0,
    #     "trigger_price": sl_price,
    #     "is_amo": False,
    #     "slice": True,
    #     "tag": "SL_EXIT"
    #     })

    # if not sl_id:
    #
    #     log("[EXIT_ENGINE] ERROR: SL failed → cancelling target")
    #
    #     broker.cancel_order(target_id)
    #
    #     self.processing_instruments.discard(instrument)
    #
    #     return False

    if target_id and target_id.get("status") == "success":
        self.target_order_id = target_id["data"]["order_ids"][0]
    else:
        self.target_order_id = None
    if sl_id and sl_id.get("status") == "success":
        self.sl_order_id = sl_id["data"]["order_ids"][0]
    else:
        self.sl_order_id = None

    log(f"[EXIT_ENGINE] Target placed | ID: {target_id}")
    log(f"[EXIT_ENGINE] SL placed | ID: {sl_id}")

    self.processing_instruments.discard(instrument)

    return True

# -------------------------------------------------
# Monitor Position
# -------------------------------------------------

 def _monitor_position(self, broker):

    positions = broker.data_provider.state_store.get_all_positions()

    qty = positions.get(self.active_instrument, 0)

    still_open = int(qty) != 0

    if not still_open:

        log("[EXIT_ENGINE] Position Closed → Resetting Engine")
        self.position_detect_time = None
        # cancel remaining exit orders if still open
        state_store = broker.data_provider.state_store
        orders = state_store.get_all_orders()

        if self.target_order_id:
            order = orders.get(self.target_order_id)
            if order and order.get("status") == "open":
                broker.cancel_order(self.target_order_id)

        if self.sl_order_id and orders.get(self.sl_order_id, {}).get("status") == "open":
            broker.cancel_order(self.sl_order_id)

        self.last_entry_price = None
        self.last_entry_instrument = None

        # reset exit engine state
        self.trade_active = False
        self.active_instrument = None
        self.target_order_id = None
        self.sl_order_id = None
        self.partial_exit_in_progress = False
        self.partial_fill_time = None
        self.partial_fill_order_id = None
        self.partial_filled_qty = 0
        # release duplicate protection locks
        self.processing_instruments.clear()
        self.processed_positions.clear()

        log("[EXIT_ENGINE] Engine Reset Complete")

