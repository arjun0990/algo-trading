import msvcrt
import keyboard
import time
from datetime import datetime
from config import GTT_CONFIG


class ManualGTTStrategy:

    def __init__(self):
        self.trade_active = False
        self.active_gtt_id = None
        self.active_instrument = None
        self.active_side = None
        self.last_key_time = 0
        self.initialized = False
        self.ce_key = None
        self.pe_key = None
        self.quantity = None
        self.current_strike = None
        self.current_ce_strike = None
        self.current_pe_strike = None
        self.last_ltp_fetch_time = 0
        self.ltp_fetch_interval = 1
        self.last_strike_refresh_time = 0
        self.last_ce_ltp = None
        self.last_pe_ltp = None
        self.strike_refresh_interval = GTT_CONFIG["strike_refresh_interval"] # seconds
        print("\n======================================")
        print("Manual GTT Strategy Active")
        print("Press C → CE Trade")
        print("Press P → PE Trade")
        print("Press Q → Exit Everything")
        print("======================================\n")

    # ======================================================
    # MAIN ENTRY (called from main loop)
    # ======================================================
    def run(self, broker, market_data, risk_engine, instruments):

        # ---------------------------------
        # Initialization
        # ---------------------------------
        if not self.initialized:
            self._initialize(instruments, market_data)
            return

        # ---------------------------------
        # Always listen for keypress
        # (E, Q must work anytime)
        # ---------------------------------
        self._handle_keypress(broker, market_data)

        # ---------------------------------
        # Monitoring Mode (No Active Trade)
        # ---------------------------------
        if not self.trade_active:

            # Dynamic strike refresh
            # self._refresh_strikes_if_needed(instruments, market_data)

            # Monitor live LTP
            self._monitor_ltp(market_data)

        # ---------------------------------
        # Trade Active Mode
        # ---------------------------------
        else:
            self._monitor_position_state(broker)



    # ======================================================
    # INITIALIZATION
    # ======================================================
    def _initialize(self, instruments, market_data):

        expiry = instruments.get_nearest_expiry()
        index_ltp = market_data.get_ltp("NSE_INDEX|Nifty 50")
        print("DEBUG → expiry:", expiry)
        print("DEBUG → index_ltp:", index_ltp)
        if not expiry or not index_ltp:
            print("Waiting for expiry/index resolution...")
            return

        # Calculate ATM
        atm = round(index_ltp / 50) * 50

        # Directional offset logic (offset is in POINTS)
        offset = GTT_CONFIG["strike_offset"]

        ce_strike = atm + offset
        pe_strike = atm - offset

        ce_token, lot_size = instruments.find_option(
            expiry,
            ce_strike,
            "CE"
        )

        pe_token, _ = instruments.find_option(
            expiry,
            pe_strike,
            "PE"
        )

        if not ce_token or not pe_token:
            print("Option instruments not found.")
            return

        # Store instrument keys
        self.ce_key = f"NSE_FO|{ce_token}"
        self.pe_key = f"NSE_FO|{pe_token}"

        # Quantity calculation (preserving your logic)
        self.lot_size = lot_size
        self.quantity = lot_size * GTT_CONFIG["lots"]

        # Store current monitored strikes separately
        self.current_ce_strike = ce_strike
        self.current_pe_strike = pe_strike

        print(f"Monitoring CE Strike: {ce_strike}")
        print(f"Monitoring PE Strike: {pe_strike}")

        self.initialized = True

    def _resolve_strikes(self, index_ltp):

        strike_step = 50  # NIFTY step size

        atm = round(index_ltp / strike_step) * strike_step
        offset = GTT_CONFIG["strike_offset"]

        ce_strike = atm + offset
        pe_strike = atm - offset

        return ce_strike, pe_strike

    def _refresh_strikes_if_needed(self, instruments, market_data):
        if not GTT_CONFIG.get("enable_dynamic_strike", True):
            return
        # Do not refresh during active trade
        if self.trade_active:
            return

        now = time.time()

        # Throttle check
        if now - self.last_strike_refresh_time < self.strike_refresh_interval:
            return

        self.last_strike_refresh_time = now

        index_ltp = market_data.get_ltp("NSE_INDEX|Nifty 50")
        if not index_ltp:
            return

        expiry = instruments.get_nearest_expiry()
        if not expiry:
            return

        # Calculate ATM
        atm = round(index_ltp / 50) * 50

        offset = GTT_CONFIG["strike_offset"]

        new_ce_strike = atm + offset
        new_pe_strike = atm - offset

        # If strike unchanged → do nothing
        if (
                new_ce_strike == self.current_ce_strike
                and new_pe_strike == self.current_pe_strike
        ):
            return

        print("\n🔄 Strike Shift Detected")
        print(f"CE: {self.current_ce_strike} → {new_ce_strike}")
        print(f"PE: {self.current_pe_strike} → {new_pe_strike}")

        ce_token, lot_size = instruments.find_option(
            expiry,
            new_ce_strike,
            "CE"
        )

        pe_token, _ = instruments.find_option(
            expiry,
            new_pe_strike,
            "PE"
        )

        if not ce_token or not pe_token:
            print("Strike refresh failed: Option instruments not found.")
            return

        # Update keys
        self.ce_key = f"NSE_FO|{ce_token}"
        self.pe_key = f"NSE_FO|{pe_token}"

        # Update quantity safely
        self.quantity = lot_size * GTT_CONFIG["lots"]

        # Store new strikes
        self.current_ce_strike = new_ce_strike
        self.current_pe_strike = new_pe_strike

        print("Monitoring Strikes Updated.")

    # ======================================================
    # MONITOR LTP
    # ======================================================
    def _monitor_ltp(self, market_data):

        now = time.time()

        if now - self.last_ltp_fetch_time < self.ltp_fetch_interval:
            return

        self.last_ltp_fetch_time = now

        ce_ltp = market_data.get_ltp(self.ce_key)
        pe_ltp = market_data.get_ltp(self.pe_key)

        # If both failed → skip print
        if ce_ltp is None and pe_ltp is None:
            print("⚠ LTP fetch failed. Retrying...")
            return

        # Use last known value if one side fails
        if ce_ltp is None:
            ce_ltp = self.last_ce_ltp
        else:
            self.last_ce_ltp = ce_ltp

        if pe_ltp is None:
            pe_ltp = self.last_pe_ltp
        else:
            self.last_pe_ltp = pe_ltp

        print(f"{self.current_ce_strike} CE: {ce_ltp} | "
              f"{self.current_pe_strike} PE: {pe_ltp}")

    # def _monitor_ltp(self, market_data):
    #
    #     now = time.time()
    #
    #     if now - self.last_ltp_fetch_time < self.ltp_fetch_interval:
    #         return
    #
    #     self.last_ltp_fetch_time = now
    #
    #     ce_ltp = market_data.get_ltp(self.ce_key)
    #     pe_ltp = market_data.get_ltp(self.pe_key)
    #
    #     print(f"{self.current_ce_strike} CE: {ce_ltp} | "
    #           f"{self.current_pe_strike} PE: {pe_ltp}")
    # ======================================================
    # HANDLE KEY
    # ======================================================
    def _handle_keypress(self, broker, market_data):

        now = time.time()

        # Prevent rapid repeat triggers (reduced delay for better responsiveness)
        if now - self.last_key_time < 0.15:
            return

        # ---------------------------------
        # 🔴 END SESSION (Highest Priority)
        # ---------------------------------
        if keyboard.is_pressed("e"):
            self.last_key_time = now
            self._end_session(broker)
            return

        # ---------------------------------
        # 🟡 FORCE EXIT (Works Anytime)
        # ---------------------------------
        if keyboard.is_pressed("q"):
            self.last_key_time = now
            self._force_exit(broker)
            return

        # ---------------------------------
        # Ignore C/P if trade already active
        # ---------------------------------
        if self.trade_active:
            return

        # ---------------------------------
        # 🟢 CE Trade
        # ---------------------------------
        if keyboard.is_pressed("c"):
            self.last_key_time = now
            self._place_trade("CE", broker, market_data)
            return

        # ---------------------------------
        # 🔵 PE Trade
        # ---------------------------------
        if keyboard.is_pressed("p"):
            self.last_key_time = now
            self._place_trade("PE", broker, market_data)
            return
    # ======================================================
    # HANDLE KEY
    # ======================================================
    # def _handle_keypress(self, broker, market_data):
    #
    #     now = time.time()
    #
    #     # Prevent rapid repeat triggers
    #     if now - self.last_key_time < 0.5:
    #         return
    #
    #     # 🔴 END SESSION (highest priority)
    #     if keyboard.is_pressed("e"):
    #         self.last_key_time = now
    #         self._end_session(broker)
    #         return
    #
    #     # FORCE EXIT (works anytime)
    #     if keyboard.is_pressed("q"):
    #         self.last_key_time = now
    #         self._force_exit(broker)
    #         return
    #
    #     # Ignore c/p if trade running
    #     if self.trade_active:
    #         return
    #
    #     if keyboard.is_pressed("c"):
    #         if self.trade_active:
    #             return
    #         else:
    #             self.last_key_time = now
    #             self._place_trade("CE", broker, market_data)
    #
    #     elif keyboard.is_pressed("p"):
    #         if self.trade_active:
    #             return
    #         else:
    #             self.last_key_time = now
    #             self._place_trade("PE", broker, market_data)

    # ======================================================
    # PLACE TRADE
    # ======================================================
    # def _place_trade(self, side, broker, market_data):
    #
    #     now = datetime.now()
    #     market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    #     market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    #
    #     if not (market_open <= now <= market_close):
    #         print("Market closed. Cannot place GTT.")
    #         return
    #
    #     instrument_key = self.ce_key if side == "CE" else self.pe_key
    #
    #     ltp = market_data.get_ltp(instrument_key)
    #     if not ltp:
    #         print("Failed to fetch LTP.")
    #         return
    #
    #     entry_type = GTT_CONFIG["entry_type"]
    #
    #     if entry_type == "IMMEDIATE":
    #         entry_price = ltp
    #         trigger_type = "IMMEDIATE"
    #
    #     elif entry_type == "ABOVE":
    #         entry_price = ltp + GTT_CONFIG["above_points"]
    #         trigger_type = "ABOVE"
    #
    #     elif entry_type == "BELOW":
    #         entry_price = ltp - GTT_CONFIG["below_points"]
    #         trigger_type = "BELOW"
    #
    #     else:
    #         print("Invalid entry type.")
    #         return
    #
    #     target_price = entry_price + GTT_CONFIG["target_points"]
    #     sl_price = entry_price - GTT_CONFIG["sl_points"]
    #
    #     rules = [
    #         {
    #             "strategy": "ENTRY",
    #             "trigger_type": trigger_type,
    #             "trigger_price": round(entry_price, 2)
    #         },
    #         {
    #             "strategy": "TARGET",
    #             "trigger_type": "IMMEDIATE",
    #             "trigger_price": round(target_price, 2)
    #         }
    #     ]
    #
    #     stoploss_rule = {
    #         "strategy": "STOPLOSS",
    #         "trigger_type": "IMMEDIATE",
    #         "trigger_price": round(sl_price, 2)
    #     }
    #
    #     if GTT_CONFIG["enable_trailing"]:
    #         difference = entry_price - sl_price
    #         min_trailing = 0.1 * difference
    #         trailing = GTT_CONFIG["trailing_points"]
    #
    #         if trailing < min_trailing:
    #             print(
    #                 f"Trailing too small. Minimum required: {min_trailing:.2f}"
    #             )
    #             return
    #
    #         stoploss_rule["trailing_gap"] = trailing
    #
    #     rules.append(stoploss_rule)
    #
    #     payload = {
    #         "type": "MULTIPLE",
    #         "quantity": self.quantity,
    #         "product": "D",
    #         "instrument_token": instrument_key,
    #         "transaction_type": "BUY",
    #         "rules": rules
    #     }
    #
    #     print("\nPlacing GTT...")
    #     gtt_id = broker.place_gtt_order(payload)
    #
    #     if not gtt_id:
    #         print("GTT placement failed.")
    #         return
    #
    #     self.trade_active = True
    #     self.active_gtt_id = gtt_id
    #     self.active_instrument = instrument_key
    #     self.active_side = side
    #
    #     print(f"GTT Active → {side} | ID: {gtt_id}")

    def _place_trade(self, side, broker, market_data):

        # ---------------------------------
        # Market Time Validation
        # ---------------------------------
        now = datetime.now()
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

        if not (market_open <= now <= market_close):
            print("Market closed. Cannot place GTT.")
            return

        # ---------------------------------
        # Instrument Selection
        # ---------------------------------
        instrument_key = self.ce_key if side == "CE" else self.pe_key

        ltp = market_data.get_ltp(instrument_key)
        if not ltp:
            print("Failed to fetch LTP.")
            return

        # ---------------------------------
        # Quantity Validation (GTT Max 1755)
        # ---------------------------------
        max_gtt_qty = 1755

        if self.quantity > max_gtt_qty:
            max_lots = max_gtt_qty // self.lot_size
            requested_lots = self.quantity // self.lot_size

            print("\n⚠ GTT Quantity Limit Reached")
            print(f"Requested Lots: {requested_lots}")
            print(f"Max Allowed Lots per GTT: {max_lots}")

            self.quantity = max_lots * self.lot_size
            print(f"Adjusted Quantity: {self.quantity}")

        # ---------------------------------
        # Entry Logic
        # ---------------------------------
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

        # ---------------------------------
        # Target & Stoploss Calculation
        # ---------------------------------
        target_price = round(entry_price + GTT_CONFIG["target_points"], 2)
        sl_price = round(entry_price - GTT_CONFIG["sl_points"], 2)

        # ---------------------------------
        # GTT Rules Construction
        # ---------------------------------
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

        # ---------------------------------
        # Trailing Stop Logic
        # ---------------------------------
        if GTT_CONFIG["enable_trailing"]:

            difference = entry_price - sl_price
            min_trailing = 0.1 * difference
            trailing = GTT_CONFIG["trailing_points"]

            if trailing < min_trailing:
                print(f"Trailing too small. Minimum required: {min_trailing:.2f}")
                return

            stoploss_rule["trailing_gap"] = trailing

        rules.append(stoploss_rule)

        # ---------------------------------
        # Payload Construction
        # ---------------------------------
        payload = {
            "type": "MULTIPLE",
            "quantity": self.quantity,
            "product": "D",
            "instrument_token": instrument_key,
            "transaction_type": "BUY",
            "rules": rules
        }

        # ---------------------------------
        # Place GTT
        # ---------------------------------
        print("\nPlacing GTT...")
        gtt_id = broker.place_gtt_order(payload)

        if not gtt_id:
            print("GTT placement failed.")
            return

        # ---------------------------------
        # Update Trade State
        # ---------------------------------
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

            self.trade_active = False
            self.active_gtt_id = None
            self.active_instrument = None
            self.active_side = None

    # def _monitor_position_state(self, broker):
    #
    #     positions = broker.get_positions()
    #     #
    #     active_qty = 0
    #
    #     for p in positions:
    #         print('POSITION ATTRIBUTES ARE : ', p)
    #         if p.get("instrument_key") == self.active_instrument:
    #             active_qty = int(p.get("quantity", 0))
    #     # if active_qty == 0:
    #     #     print("Trade completed. Monitoring resumed.")
    #     #     self.trade_active = False
    #     #     self.active_gtt_id = None
    #     #     self.active_instrument = None
    #     #     self.active_side = None
    # def _monitor_position_state(self, broker):
    #     positions = broker.get_positions()
    #
    #     active_position = False
    #
    #     for p in positions:
    #         if (
    #                 p.get("instrument_token") == self.active_instrument
    #                 and int(p.get("quantity", 0)) != 0
    #         ):
    #             active_position = True
    #             break
    #
    #     if not active_position:
    #         print("Trade completed. Monitoring resumed.")
    #
    #         self.trade_active = False
    #         self.active_gtt_id = None
    #         self.active_instrument = None
    #         self.active_side = None
    #
    #         return
    # ======================================================
    # FORCE EXIT
    # ======================================================
    def _force_exit(self, broker):

        print("\nForce Exit Triggered...")

        # 1️⃣ Cancel GTT first (if active)
        if self.active_gtt_id:
            print("Cancelling active GTT:", self.active_gtt_id)
            broker.cancel_gtt_order(self.active_gtt_id)
        else:
            print("No active GTT to cancel.")

        # 2️⃣ Use existing institutional flatten logic
        flattened = broker.flatten_and_verify()

        if not flattened:
            print("WARNING: Flatten verification failed.")
        else:
            print("System fully flattened.")

        # 3️⃣ Reset strategy state safely
        self.trade_active = False
        self.active_gtt_id = None
        self.active_instrument = None
        self.active_side = None

        print("Monitoring resumed.")

    def _end_session(self, broker):
        print("\n🔴 SESSION TERMINATION INITIATED...")
        # 1️⃣ Cancel active GTT (if any)
        if self.active_gtt_id:
            print("Cancelling active GTT:", self.active_gtt_id)
            broker.cancel_gtt_order(self.active_gtt_id)
        else:
            print("No active GTT to cancel.")
        # 2️⃣ Flatten everything using your institutional logic
        flattened = broker.flatten_and_verify()
        if flattened:
            print("All orders and positions cleared.")
        else:
            print("WARNING: Flatten verification failed.")
        print("Shutting down system safely...")
        raise SystemExit