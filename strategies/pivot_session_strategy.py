# strategies/pivot_session_strategy.py
from datetime import datetime
from config import PIVOT_CONFIG


class PivotSessionStrategy:
    """
    Virgin Pivot Reclaim + Immediate Bounce Strategy
    Fully aligned with new structured config
    """

    def __init__(self):
        self.session_trade_taken = False
        self.pivot_store = {}
        self.above_engine_state = {}
        self.pivot_date = None

    # =========================================================
    # PUBLIC ENTRY
    # =========================================================
    def check_signal(self, market_data, instrument_manager):

        if PIVOT_CONFIG["one_trade_per_session"] and self.session_trade_taken:
            return None

        expiry = instrument_manager.get_nearest_expiry()

        instrument_keys = []

        # -------------------------------
        # CE Selection
        # -------------------------------
        if PIVOT_CONFIG["enable_ce"]:
            ce_key, _ = instrument_manager.find_option(
                expiry,
                instrument_manager.get_atm_strike("NIFTY", market_data)
                + PIVOT_CONFIG["strike_offset"],
                "CE",
                "NIFTY"
            )
            if ce_key:
                instrument_keys.append(ce_key)

        # -------------------------------
        # PE Selection
        # -------------------------------
        if PIVOT_CONFIG["enable_pe"]:
            pe_key, _ = instrument_manager.find_option(
                expiry,
                instrument_manager.get_atm_strike("NIFTY")
                - PIVOT_CONFIG["strike_offset"],
                "PE",
                "NIFTY"
            )
            if pe_key:
                instrument_keys.append(pe_key)

        # -------------------------------
        # Loop Instruments
        # -------------------------------
        for key in instrument_keys:

            if not self._ensure_initialized(key, market_data):
                continue

            signal = None

            if PIVOT_CONFIG["enable_above_pivot_trade"]:
                signal = self._check_above_engine(key, market_data)

            if not signal and PIVOT_CONFIG["enable_below_pivot_trade"]:
                signal = self._check_below_engine(key, market_data)

            if signal:
                self.session_trade_taken = True
                return signal

        return None

    # =========================================================
    # INITIALIZATION
    # =========================================================
    def _ensure_initialized(self, key, market_data):

        today = datetime.now().date()

        # --------------------------------------------------
        # Already fully initialized for today
        # --------------------------------------------------
        if (
                key in self.pivot_store
                and self.pivot_store[key].get("pivot_date") == today
                and self.pivot_store[key].get("data_ready") is True
        ):
            return True

        try:
            print(f"INITIALIZING PIVOT STRUCTURE FOR {key}")

            # 1️⃣ Fetch pivots only once per day
            pivots = market_data.get_previous_day_fib_pivots(key)
            if not pivots:
                return False

            # # 2️⃣ Preload intraday data once
            # print(f"Preload intraday data once KEY IS {key}")
            # instrument_key = f"NSE_FO|{key}"
            # candles = market_data.get_intraday_1min_candles(instrument_key)
            # print(f"Preload intraday data once CANDLE IS {candles}")
            # if not candles:
            #     print("Waiting for first intraday candle...")
            #     return False

            # 3️⃣ Store everything cleanly
            self.pivot_store[key] = {
                "pivot_date": today,
                "pivots": pivots,
                "touched_today": {name: False for name in pivots},
                "invalidated": {name: False for name in pivots},
                "data_ready": True  # 🔥 critical flag
            }

            self.above_engine_state[key] = {
                "phase": None,
                "tracking_pivot": None,
                "pivot_value": None,
                "validation_index": None
            }

            print(f"PIVOTS READY FOR {key}")
            return True

        except Exception as e:
            print(f"PIVOT INIT FAILED for {key}: {e}")
            return False

    # def _ensure_initialized(self, key, market_data):
    #     today = datetime.now().date()
    #     # -------------------------------------------------- #
    #     # 1️⃣ Already initialized for today → skip
    #     # --------------------------------------------------
    #     if (
    #             key in self.pivot_store
    #             and self.pivot_store[key].get("pivot_date") == today
    #             and self.pivot_store[key].get("data_ready") is True
    #     ):
    #         return True
    #     try:
    #         print(f"INITIALIZING PIVOT STRUCTURE FOR {key}")
    #         # 1️⃣ Fetch pivots only once per day
    #         pivots = market_data.get_previous_day_fib_pivots(key)
    #         if not pivots:
    #             return False
    #     # --------------------------------------------------
    #     # 2️⃣ Store pivots with today's date
    #     # --------------------------------------------------
    #     #     self.pivot_store[key] = {
    #     #         "pivot_date": today,
    #     #         "pivots": pivots,
    #     #         "touched_today": {name: False for name in pivots},
    #     #         "invalidated": {name: False for name in pivots}
    #     #     }
    #
    #     #     print(f"PIVOT IS :  {pivots}")
    #         self.pivot_store[key] = {
    #             "pivot_date": today,
    #             "pivots": pivots,
    #             "touched_today": {name: False for name in pivots},
    #             "invalidated": {name: False for name in pivots},
    #             "data_ready": True  # 🔥 critical flag
    #         }
    #
    #
    #         # candles = market_data.get_intraday_1min_candles(key)
    #         # if not candles:
    #         #     print("Waiting for first intraday candle...")
    #         #     return False
    #     # --------------------------------------------------
    #     # 3️⃣ Reset engine state cleanly
    #     # --------------------------------------------------
    #         self.above_engine_state[key] = {
    #             "phase": None,
    #             "tracking_pivot": None,
    #             "pivot_value": None,
    #             "validation_index": None }
    #         print(f"PIVOTS INITIALIZED FOR {key}")
    #         print("PIVOTS:", pivots)
    #         return True
    #     except Exception as e:
    #         print(f"PIVOT INIT FAILED for {key}: {e}")
    #     return False
    # =========================================================
    # ABOVE ENGINE
    # =========================================================
    def _check_above_engine(self, key, market_data):
        print(f"INSIDE ABOVE ENGINE")
        pivots = self.pivot_store[key]["pivots"]
        touched = self.pivot_store[key]["touched_today"]
        invalidated = self.pivot_store[key]["invalidated"]
        state = self.above_engine_state[key]

        candle = market_data.get_latest_candle(key)
        prev = market_data.get_previous_candle(key)
        if not candle or not prev:
            return None
        low = candle.low
        high = candle.high
        close = candle.close
        index = candle.index

        # Update touch flags

        # ==============================
        # STATE 0 — IDLE
        # ==============================

        if state["phase"] is None:

            sorted_pivots = sorted(
                [(n, v) for n, v in pivots.items() if not invalidated[n]],
                key=lambda x: x[1]
            )

            for name, value in sorted_pivots:

                if value <= prev.close:
                    continue

                if touched[name] or invalidated[name]:
                    continue

                if low <= value and close >= value:
                    state["phase"] = "validated"
                    state["tracking_pivot"] = name
                    state["pivot_value"] = value
                    state["validation_index"] = index
                    break

            # ==============================
            # STATE 1 — VALIDATED
            # ==============================
        elif state["phase"] == "validated":

            if index > state["validation_index"]:

                if low <= state["pivot_value"]:
                    self._invalidate_pivot(key, state["tracking_pivot"])
                    self._reset_above_state(key)
                else:
                    state["phase"] = "waiting_retest"

            # ==============================
            # STATE 2 — WAITING RETEST
            # ==============================
        elif state["phase"] == "waiting_retest":

            if index > state["validation_index"] + 6:
                self._invalidate_pivot(key, state["tracking_pivot"])
                self._reset_above_state(key)
                return None

            if low <= state["pivot_value"]:

                entry = state["pivot_value"]

                if PIVOT_CONFIG["use_fixed_sl"]:
                    sl = entry - PIVOT_CONFIG["fixed_sl_points"]
                else:
                    sl = entry - PIVOT_CONFIG["fixed_sl_points"]

                touched[state["tracking_pivot"]] = True
                self._reset_above_state(key)

                return {
                    "instrument_key": key,
                    "entry_price": entry,
                    "initial_sl_reference": sl,
                    "sl_price": sl,
                    "strategy_name": "PIVOT"
                }

            # Update touched flags
        for name, value in pivots.items():
            if low <= value <= high:
                touched[name] = True

        return None

    # =========================================================
    # BELOW ENGINE
    # =========================================================
    def _check_below_engine(self, key, market_data):
        print(f"INSIDE BELOW ENGINE")
        pivots = self.pivot_store[key]["pivots"]
        invalidated = self.pivot_store[key]["invalidated"]

        candle = market_data.get_latest_candle(key)
        prev = market_data.get_previous_candle(key)

        if not candle or not prev:
            return None

        low = candle.low
        close = candle.close
        prev_close = prev.close

        sorted_pivots = sorted(
            [(n, v) for n, v in pivots.items() if v < close],
            key=lambda x: x[1],
            reverse=True
        )

        for name, value in sorted_pivots:

            if invalidated[name]:
                continue

            # Gap invalidation
            if prev_close <= value and low <= value:
                self._invalidate_pivot(key, name)
                continue

            # Proper touch
            if prev_close > value and low <= value:

                entry = value

                if PIVOT_CONFIG["use_fixed_sl"]:
                    sl = entry - PIVOT_CONFIG["fixed_sl_points"]
                else:
                    sl = entry - PIVOT_CONFIG["fixed_sl_points"]

                self.pivot_store[key]["touched_today"][name] = True

                return {
                    "instrument_key": key,
                    "entry_price": entry,
                    "initial_sl_reference": sl,
                    "sl_price": sl,
                    "strategy_name": "PIVOT"
                }

        return None

    # =========================================================
    # HELPERS
    # =========================================================
    def _invalidate_pivot(self, key, pivot_name):
        self.pivot_store[key]["invalidated"][pivot_name] = True

    def _reset_above_state(self, key):
        self.above_engine_state[key] = {
            "phase": None,
            "tracking_pivot": None,
            "pivot_value": None,
            "validation_index": None
        }

    def reset_session(self):
        self.session_trade_taken = False
        self.pivot_store.clear()
        self.above_engine_state.clear()