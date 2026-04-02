import time
from datetime import datetime

from config import (
    GLOBAL_CONFIG,
    BOUNCE_CONFIG
)


class BounceStrategy:

    def __init__(self):
        self.state = {}
        self.debug_active = True
        self.initialized = False

    # =========================================================
    # STRIKE INITIALIZATION
    # =========================================================
    def initialize_strikes(self, market_data, instrument_manager):

        nifty_ltp = market_data.get_ltp("NSE_INDEX|Nifty 50")

        if not nifty_ltp:
            return False

        atm = round(nifty_ltp / 50) * 50
        expiry = instrument_manager.get_nearest_expiry()

        ce_enabled = BOUNCE_CONFIG["enable_ce"]
        pe_enabled = BOUNCE_CONFIG["enable_pe"]
        offset = BOUNCE_CONFIG["strike_offset"]

        self.state = {}

        if ce_enabled:
            ce_key, _ = instrument_manager.find_option(
                expiry,
                atm + offset,
                "CE",
                "NIFTY"
            )
            if ce_key:
                self.state[ce_key] = {
                    "low": None,
                    "ready": False,
                    "type": "CE",
                    "strike": atm + BOUNCE_CONFIG["strike_offset"]
                }

        if pe_enabled:
            pe_key, _ = instrument_manager.find_option(
                expiry,
                atm - offset,
                "PE",
                "NIFTY"
            )
            if pe_key:
                self.state[pe_key] = {
                    "low": None,
                    "ready": False,
                    "type": "PE",
                    "strike": atm - BOUNCE_CONFIG["strike_offset"]
                }

        if not self.state:
            return False

        print("======================================")
        print("Bounce Strategy Monitoring:")
        print("ATM:", atm)
        print("Monitoring Keys:", list(self.state.keys()))
        print("======================================")

        self.debug_active = True
        self.initialized = True
        return True

    # =========================================================
    # MAIN SIGNAL ENGINE
    # =========================================================
    def check_signal(self, market_data, instrument_manager):

        now = datetime.now()

        # Time filter
        if (
            now.hour > BOUNCE_CONFIG["no_new_trades_after_hour"] or
            (
                now.hour == BOUNCE_CONFIG["no_new_trades_after_hour"] and
                now.minute >= BOUNCE_CONFIG["no_new_trades_after_minute"]
            )
        ):
            return None

        # Initialize once per session
        if not self.initialized:
            if not self.initialize_strikes(market_data, instrument_manager):
                return None

        for key in list(self.state.keys()):

            ltp = market_data.get_ltp(key)

            if not ltp:
                continue

            s = self.state[key]

            # Debug print (only before entry)
            if self.debug_active:
                print(
                    f"{s['strike']} {s['type']} | "
                    f"LOW: {s['low']} | "
                    f"LTP: {ltp}"
                )

            # Premium filter
            if ltp < BOUNCE_CONFIG["min_premium"]:
                continue

            # Initialize low from last 10 candles
            if s["low"] is None:
                candles = market_data.get_intraday_1min_candles(key)
                # candles = market_data.get_historical_candles(
                #     key,
                #     interval="minutes/1",
                #     minutes_back=30
                # )

                if len(candles) < 10:
                    continue

                # Sort by timestamp ascending
                candles.sort(key=lambda x: x[0])

                # Take last 10 completed candles
                last_10 = candles[-10:]

                lows = [c[3] for c in last_10]

                print("LAST 10 USED:")
                for c in last_10:
                    print(c[0], "LOW:", c[3])

                s["low"] = min(lows)
                continue

            # New low update
            if ltp < s["low"]:
                s["low"] = ltp
                s["ready"] = False
                continue

            # Bounce weakening
            if s["ready"] and ltp < s["low"] + BOUNCE_CONFIG["bounce_points"]:
                s["ready"] = False
                continue

            # Bounce confirmation
            if not s["ready"] and ltp >= s["low"] + BOUNCE_CONFIG["bounce_points"]:
                s["ready"] = True
                continue

            # Entry trigger
            entry_level = (
                s["low"] +
                BOUNCE_CONFIG["bounce_points"] +
                BOUNCE_CONFIG["entry_buffe"]
            )

            if s["ready"] and ltp >= entry_level:

                self.debug_active = False
                self.reset_session()

                return {
                    "instrument_key": key,
                    "entry_price": entry_level,
                    "initial_sl_reference": s["low"],
                    "strategy_name": "BOUNCE"
                }

        return None

    # =========================================================
    # SESSION RESET
    # =========================================================
    def reset_session(self):
        self.state = {}
        self.initialized = False
        self.debug_active = True