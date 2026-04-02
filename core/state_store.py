# core/state_store.py

import threading
import time


class StateStore:
    """
    Thread-safe in-memory state container.
    Used by WebSocket streams to update market and order data.
    Strategies read from here instead of polling REST.
    """

    def __init__(self):

        self._lock = threading.RLock()

        # -----------------------------
        # Market Data
        # -----------------------------
        self._ltp_map = {}              # { instrument_key: price }
        self._ltp_timestamp = {}        # { instrument_key: last_update_time }

        # -----------------------------
        # Orders
        # -----------------------------
        self._orders = {}               # { order_id: full_order_payload }
        self._order_timestamp = {}      # { order_id: last_update_time }

        # -----------------------------
        # Positions
        # -----------------------------
        self._positions = {}            # { instrument_key: quantity }
        self._position_timestamp = {}   # { instrument_key: last_update_time }

        # -----------------------------
        # Stream Health
        # -----------------------------
        self._stream_connected = False
        self._last_stream_heartbeat = None

        self._position_changed = False
        self._order_changed = False

    # =========================================================
    # STREAM STATUS
    # =========================================================

    def set_stream_status(self, status: bool):
        with self._lock:
            self._stream_connected = status
            if status:
                self._last_stream_heartbeat = time.time()

    def update_heartbeat(self):
        with self._lock:
            self._last_stream_heartbeat = time.time()

    def is_stream_connected(self):
        with self._lock:
            return self._stream_connected

    def get_last_heartbeat(self):
        with self._lock:
            return self._last_stream_heartbeat



    # =========================================================
    # LTP MANAGEMENT
    # =========================================================

    def update_ltp(self, instrument_key: str, price: float):
        with self._lock:
            self._ltp_map[instrument_key] = price
            self._ltp_timestamp[instrument_key] = time.time()

    def get_ltp(self, instrument_key: str):
        with self._lock:
            return self._ltp_map.get(instrument_key)

    def get_ltp_timestamp(self, instrument_key: str):
        with self._lock:
            return self._ltp_timestamp.get(instrument_key)

    # =========================================================
    # ORDER MANAGEMENT
    # =========================================================

    def update_order(self, order_id: str, order_data: dict):
        with self._lock:
            self._orders[order_id] = order_data
            self._order_timestamp[order_id] = time.time()
        #================================================================================================
            # ------------------------------------------
            # Mark order update for exit engine polling
            # ------------------------------------------
            self._order_changed = True

            # ------------------------------------------
            # FAST ENTRY FILL DETECTION (SAFE)
            # ------------------------------------------
            tag = order_data.get("tag")
            status = order_data.get("status", "").lower()
            pending = int(order_data.get("pending_quantity", 0))
            filled = int(order_data.get("filled_quantity", 0))
            qty = int(order_data.get("quantity", 0))

            # Trigger position check ONLY when entry fully filled
            if tag == "ENTRY" and status == "complete" and pending == 0 and filled == qty:
                self._position_changed = True
        #=====================================================================================================

    def get_order(self, order_id: str):
        with self._lock:
            return self._orders.get(order_id)

    def get_all_orders(self):
        with self._lock:
            return dict(self._orders)

    # =========================================================
    # POSITION MANAGEMENT
    # =========================================================

    def update_position(self, instrument_key: str, quantity: int):
        with self._lock:
            self._positions[instrument_key] = quantity
            self._position_timestamp[instrument_key] = time.time()
        # =====================================================================================================
            # ------------------------------------------
            # Notify strategies that position changed
            # ------------------------------------------
            self._position_changed = True
        # =====================================================================================================

    def get_position(self, instrument_key: str):
        with self._lock:
            return self._positions.get(instrument_key, 0)

    def get_all_positions(self):
        with self._lock:
            return dict(self._positions)

    def get_position_timestamp(self, instrument_key: str):
        with self._lock:
            return self._position_timestamp.get(instrument_key)



    def mark_position_changed(self):
        with self._lock:
            self._position_changed = True

    def mark_order_changed(self):
        with self._lock:
            self._order_changed = True

    def consume_position_changed(self):
        with self._lock:
            changed = self._position_changed
            self._position_changed = False
            return changed

    def consume_order_changed(self):
        with self._lock:
            changed = self._order_changed
            self._order_changed = False
            return changed


    def is_stream_stale(self, timeout_seconds: int):
        with self._lock:
            if not self._last_stream_heartbeat:
                return True
            return (time.time() - self._last_stream_heartbeat) > timeout_seconds