import msvcrt
import keyboard
import time
from datetime import datetime
from config import GTT_CONFIG, ACTIVE_INDEX, INDEX_CONFIG


class ManualGTTStrategy:

    def __init__(self):
        self.trade_active = False
        self.current_atm = None
        self.active_gtt_id = None
        self.active_instrument = None
        self.active_side = None
        self.last_key_time = 0
        self.key_cooldown = 0.8
        self.order_in_progress = False
        self.initialized = False
        self.ce_key = None
        self.pe_key = None
        self.quantity = None
        self.current_ce_strike = None
        self.current_pe_strike = None
        self.last_atm = None  # 🔥 NEW → track ATM bucket
        self.last_ltp_fetch_time = 0
        self.ltp_fetch_interval = 1
        self.last_ce_ltp = None
        self.last_pe_ltp = None
        self.cached_expiry = None
        self.option_cache = {}
        # ---------------------------------
        # Pre-built Payload Templates
        # ---------------------------------
        self.base_payload_template = {
            "type": "MULTIPLE",
            "product": "D",
            "transaction_type": "BUY"
        }
        print("\n======================================")
        print("Manual GTT Strategy Active")
        print("Press C → CE Trade")
        print("Press P → PE Trade")
        print("Press Q → Exit Everything")
        print("======================================\n")

    # ======================================================
    # MAIN ENTRY
    # ======================================================
    def run(self, broker, market_data, risk_engine, instruments):

        if not self.initialized:
            self._initialize(instruments, market_data)
            return

        self._handle_keypress(broker, market_data)

        if not self.trade_active:
            self._monitor_ltp(market_data, instruments)
        else:
            self._monitor_position_state(broker)

    # ======================================================
    # INITIALIZATIO
    # ======================================================
    def _initialize(self, instruments, market_data):

        if not self.cached_expiry:
            self.cached_expiry = instruments.get_nearest_expiry()

        expiry = self.cached_expiry
        index_symbol = INDEX_CONFIG[ACTIVE_INDEX]["index_symbol"]
        index_ltp = market_data.get_ltp(index_symbol)

        print("DEBUG → expiry:", expiry)
        print("DEBUG → index_ltp:", index_ltp)

        if not expiry or not index_ltp:
            print("Waiting for expiry/index resolution...")
            return

        strike_step = INDEX_CONFIG[ACTIVE_INDEX]["strike_step"]
        atm = round(index_ltp / strike_step) * strike_step
        self.last_atm = atm  # 🔥 store initial ATM
        # ---------------------------------
        # Pre-build option lookup cache
        # ---------------------------------
        print("Building option cache...")

        strike_range_start = atm - 1000
        strike_range_end = atm + 1000

        for strike in range(strike_range_start, strike_range_end, strike_step):

            ce_token, lot = instruments.find_option(expiry, strike, "CE")
            pe_token, _ = instruments.find_option(expiry, strike, "PE")

            if ce_token:
                self.option_cache[(strike, "CE")] = (ce_token, lot)

            if pe_token:
                self.option_cache[(strike, "PE")] = (pe_token, lot)

        print("Option cache ready.")
        offset = GTT_CONFIG["strike_offset"]

        ce_strike = atm + offset
        pe_strike = atm - offset

        ce_token, lot_size = instruments.find_option(expiry, ce_strike, "CE")
        pe_token, _ = instruments.find_option(expiry, pe_strike, "PE")

        if not ce_token or not pe_token:
            print("Option instruments not found.")
            return

        exchange = INDEX_CONFIG[ACTIVE_INDEX]["segment"]

        self.ce_key = f"{exchange}|{ce_token}"
        self.pe_key = f"{exchange}|{pe_token}"

        self.lot_size = lot_size
        self.quantity = lot_size * GTT_CONFIG["lots"]

        self.current_ce_strike = ce_strike
        self.current_pe_strike = pe_strike

        print(f"Monitoring CE Strike: {ce_strike}")
        print(f"Monitoring PE Strike: {pe_strike}")

        self.initialized = True

    # ======================================================
    # EVENT-DRIVEN LTP + STRIKE REFRESH
    # ======================================================
    def _monitor_ltp(self, market_data, instruments):
        if self.trade_active:
            return
        now = time.time()

        if now - self.last_ltp_fetch_time < self.ltp_fetch_interval:
            return

        self.last_ltp_fetch_time = now

        # --------------------------------------------------
        # 🔥 EVENT-DRIVEN ATM SHIFT DETECTION
        # --------------------------------------------------
        index_symbol = INDEX_CONFIG[ACTIVE_INDEX]["index_symbol"]
        index_ltp = market_data.get_ltp(index_symbol)

        if index_ltp:

            strike_step = INDEX_CONFIG[ACTIVE_INDEX]["strike_step"]

            new_atm = round(index_ltp / strike_step) * strike_step

            if self.last_atm is not None and new_atm != self.last_atm:
                if self.current_atm is None:
                    return

                if abs(index_ltp - self.current_atm) >= 25:
                    self.current_atm = new_atm
                    offset = GTT_CONFIG["strike_offset"]
                    new_ce_strike = new_atm + offset
                    new_pe_strike = new_atm - offset

                    expiry = self.cached_expiry
                    if not expiry:
                        return

                    ce_data = self.option_cache.get((new_ce_strike, "CE"))
                    pe_data = self.option_cache.get((new_pe_strike, "PE"))

                    if not ce_data or not pe_data:
                        return

                    ce_token, lot_size = ce_data
                    pe_token, _ = pe_data

                    if ce_token and pe_token:

                     self.ce_key = f"{INDEX_CONFIG[ACTIVE_INDEX]['segment']}|{ce_token}"
                     self.pe_key = f"{INDEX_CONFIG[ACTIVE_INDEX]['segment']}|{pe_token}"

                     self.quantity = lot_size * GTT_CONFIG["lots"]

                     self.current_ce_strike = new_ce_strike
                     self.current_pe_strike = new_pe_strike
                     self.last_atm = new_atm

                     print("\n🔄 ATM Shift Detected → Strikes Updated")
                     print(f"New CE Strike: {new_ce_strike}")
                     print(f"New PE Strike: {new_pe_strike}")

        # --------------------------------------------------
        # CE / PE LTP
        # --------------------------------------------------
        ce_ltp = market_data.get_ltp(self.ce_key)
        pe_ltp = market_data.get_ltp(self.pe_key)

        if ce_ltp is None and pe_ltp is None:
            print("⚠ LTP fetch failed. Retrying...")
            return

        if ce_ltp is None:
            ce_ltp = self.last_ce_ltp
        else:
            self.last_ce_ltp = ce_ltp

        if pe_ltp is None:
            pe_ltp = self.last_pe_ltp
        else:
            self.last_pe_ltp = pe_ltp

    # ======================================================
    # HANDLE KEY
    # ======================================================
    def _handle_keypress(self, broker, market_data):

        now = time.time()

        if now - self.last_key_time < 0.15:
            return

        if keyboard.is_pressed("e"):
            self.last_key_time = now
            self._end_session(broker)
            return

        if keyboard.is_pressed("q"):
            self.last_key_time = now
            self._force_exit(broker)
            return


        if self.trade_active:
            return

        if now - self.last_key_time < self.key_cooldown:
            return

        if self.order_in_progress:
            return

        if keyboard.is_pressed("c"):
            self.last_key_time = now
            self.order_in_progress = True
            self._place_trade("CE", broker, market_data)
            self.order_in_progress = False
            return

        if keyboard.is_pressed("p"):
            self.last_key_time = now
            self.order_in_progress = True
            self._place_trade("PE", broker, market_data)
            self.order_in_progress = False
            return

    # ======================================================
    # PLACE TRADE (UNCHANGED LOGIC)
    # ======================================================
    def _place_trade(self, side, broker, market_data):

        now = datetime.now()
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

        if not (market_open <= now <= market_close):
            print("Market closed. Cannot place GTT.")
            return

        instrument_key = self.ce_key if side == "CE" else self.pe_key

        ltp = market_data.get_ltp(instrument_key)
        if not ltp:
            print("Failed to fetch LTP.")
            return

        max_gtt_qty = INDEX_CONFIG[ACTIVE_INDEX]["max_gtt_quantity"]

        if self.quantity > max_gtt_qty:
            max_lots = max_gtt_qty // self.lot_size
            self.quantity = max_lots * self.lot_size

        entry_type = GTT_CONFIG["entry_type"]

        if entry_type == "IMMEDIATE":
            entry_price = ltp
            trigger_type = "IMMEDIATE"
        elif entry_type == "ABOVE":
            entry_price = ltp + GTT_CONFIG["above_points"]
            trigger_type = "ABOVE"
        elif entry_type == "BELOW":
            entry_price = ltp - GTT_CONFIG["below_points"]
            trigger_type = "BELOW"
        else:
            print("Invalid entry type.")
            return

        entry_price = round(entry_price, 2)
        target_price = round(entry_price + GTT_CONFIG["target_points"], 2)
        sl_price = round(entry_price - GTT_CONFIG["sl_points"], 2)

        rules = [
            {
                "strategy": "ENTRY",
                "trigger_type": trigger_type,
                "trigger_price": entry_price
            },
            {
                "strategy": "TARGET",
                "trigger_type": "IMMEDIATE",
                "trigger_price": target_price
            }
        ]

        stoploss_rule = {
            "strategy": "STOPLOSS",
            "trigger_type": "IMMEDIATE",
            "trigger_price": sl_price
        }

        if GTT_CONFIG["enable_trailing"]:
            difference = entry_price - sl_price
            min_trailing = 0.1 * difference
            trailing = GTT_CONFIG["trailing_points"]

            if trailing < min_trailing:
                print(f"Trailing too small. Minimum required: {min_trailing:.2f}")
                return

            stoploss_rule["trailing_gap"] = trailing

        rules.append(stoploss_rule)

        payload = dict(self.base_payload_template)

        payload["quantity"] = self.quantity
        payload["instrument_token"] = instrument_key
        payload["rules"] = rules
        state_store = broker.data_provider.state_store  # ← ADD THIS
        state_store.manual_trade_active = True
        print("\nPlacing GTT...")
        gtt_id = broker.place_gtt_order(payload)

        if not gtt_id:
            print("GTT placement failed.")
            return

        self.trade_active = True
        self.active_gtt_id = gtt_id
        self.active_instrument = instrument_key
        self.active_side = side

        print(f"GTT Active → {side} | ID: {gtt_id}")

    # ======================================================
    # MONITOR POSITION
    # ======================================================
    def _monitor_position_state(self, broker):

        positions = broker.get_positions()

        active_position = False

        for p in positions:
            if (
                p.get("instrument_token") == self.active_instrument
                and int(p.get("quantity", 0)) != 0
            ):
                active_position = True
                break

        if not active_position:
            print("Manual GTT trade completed. Monitoring resumed.")
            state_store = broker.data_provider.state_store
            state_store.manual_trade_active = False
            self.trade_active = False
            self.active_gtt_id = None
            self.active_instrument = None
            self.active_side = None

    # ======================================================
    # FORCE EXIT
    # ======================================================
    def _force_exit(self, broker):

        print("\nForce Exit Triggered...")

        if self.active_gtt_id:
            broker.cancel_gtt_order(self.active_gtt_id)

        broker.flatten_and_verify()
        state_store = broker.data_provider.state_store
        state_store.manual_trade_active = False
        self.trade_active = False
        self.active_gtt_id = None
        self.active_instrument = None
        self.active_side = None

        print("Monitoring resumed.")

    def _end_session(self, broker):

        print("\n🔴 SESSION TERMINATION INITIATED...")

        if self.active_gtt_id:
            broker.cancel_gtt_order(self.active_gtt_id)

        broker.flatten_and_verify()
        state_store = broker.data_provider.state_store
        state_store.manual_trade_active = False
        self.trade_active = False
        self.active_gtt_id = None
        self.active_instrument = None
        self.active_side = None
        print("Shutting down system safely...")
        raise SystemExit