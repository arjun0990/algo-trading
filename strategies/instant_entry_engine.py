import msvcrt
import keyboard
import time
from datetime import datetime
from config import INSTANT_ENGINE_CONFIG, ACTIVE_INDEX, INDEX_CONFIG
from core.utils import log, round_to_tick


class ManualEntryStrategy:

 def __init__(self,exit_engine):
    self.exit_engine = exit_engine
    self.trade_active = False
    self.current_atm = None
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
    self.last_atm = None
    self.last_ltp_fetch_time = 0
    self.ltp_fetch_interval = 1
    self.last_ce_ltp = None
    self.last_pe_ltp = None
    self.cached_expiry = None
    self.option_cache = {}

    log(f"[ENTRY]\n======================================")
    log(f"[ENTRY] Manual Entry Strategy Active")
    log(f"[ENTRY] Press C → CE Trade")
    log(f"[ENTRY] Press P → PE Trade")
    log(f"[ENTRY] Press Q → Exit Everything")
    log(f"[ENTRY] ======================================\n")

# ======================================================
# MAIN ENTRY
# ======================================================

 def run(self, broker, market_data, risk_engine, instruments):

    state_store = broker.data_provider.state_store
    positions = state_store.get_all_positions()

     # If trade was active but position is now closed → reset entry engine
    if self.trade_active:

         if not positions or all(int(qty) == 0 for qty in positions.values()):
             log("[ENTRY_ENGINE] Position closed → Entry engine reset")
             self.trade_active = False

    if not self.initialized:
        self._initialize(instruments, market_data)
        return

    self._handle_keypress(broker, market_data)

    if not self.trade_active:
        self._monitor_ltp(market_data, instruments)

# ======================================================
# INITIALIZATION
# ======================================================

 def _initialize(self, instruments, market_data):

    if not self.cached_expiry:
        self.cached_expiry = instruments.get_nearest_expiry()

    if self.initialized:
        return

    expiry = self.cached_expiry
    index_symbol = INDEX_CONFIG[ACTIVE_INDEX]["index_symbol"]
    index_ltp = market_data.get_ltp(index_symbol)

    log(f"[ENTRY] DEBUG → expiry:{expiry}")
    log(f"[ENTRY] DEBUG → index_ltp:{index_ltp}")

    if not expiry or not index_ltp:
        log(f"[ENTRY] Waiting for expiry/index resolution...")
        return

    strike_step = INDEX_CONFIG[ACTIVE_INDEX]["strike_step"]
    atm = round(index_ltp / strike_step) * strike_step
    self.last_atm = atm
    if not self.option_cache:
        log(f"[ENTRY] Building option cache...")

        strike_range_start = atm - 1000
        strike_range_end = atm + 1000

        for strike in range(strike_range_start, strike_range_end, strike_step):

            ce_token, lot = instruments.find_option(expiry, strike, "CE")
            pe_token, _ = instruments.find_option(expiry, strike, "PE")

            if ce_token:
                self.option_cache[(strike, "CE")] = (ce_token, lot)

            if pe_token:
                self.option_cache[(strike, "PE")] = (pe_token, lot)

        log(f"[ENTRY] Option cache ready.")

    offset = INSTANT_ENGINE_CONFIG["strike_offset"]

    ce_strike = atm + offset
    pe_strike = atm - offset

    # ce_token, lot_size = instruments.find_option(expiry, ce_strike, "CE")
    # pe_token, _ = instruments.find_option(expiry, pe_strike, "PE")
    ce_data = self.option_cache.get((ce_strike, "CE"))
    pe_data = self.option_cache.get((pe_strike, "PE"))

    ce_token = ce_data[0] if ce_data else None
    pe_token = pe_data[0] if pe_data else None
    lot_size = ce_data[1] if ce_data else None
    log(f"[ENTRY] CE TOKEN is....{ce_token}")
    log(f"[ENTRY] PE TOKEN is....{pe_token}")
    if not ce_token or not pe_token:
        log(f"[ENTRY] Option instruments not found.")
        return

    exchange = INDEX_CONFIG[ACTIVE_INDEX]["segment"]

    self.ce_key = f"{exchange}|{ce_token}"
    self.pe_key = f"{exchange}|{pe_token}"

    self.lot_size = lot_size
    self.quantity = lot_size * INSTANT_ENGINE_CONFIG["lots"]

    self.current_ce_strike = ce_strike
    self.current_pe_strike = pe_strike

    log(f"[ENTRY] Monitoring CE Strike: {ce_strike}")
    log(f"[ENTRY] Monitoring PE Strike: {pe_strike}")

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
                offset = INSTANT_ENGINE_CONFIG["strike_offset"]

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

                    self.quantity = lot_size * INSTANT_ENGINE_CONFIG["lots"]

                    self.current_ce_strike = new_ce_strike
                    self.current_pe_strike = new_pe_strike
                    self.last_atm = new_atm

                    log(f"[ENTRY]\n🔄 ATM Shift Detected → Strikes Updated")
                    log(f"[ENTRY]New CE Strike: {new_ce_strike}")
                    log(f"[ENTRY]New PE Strike: {new_pe_strike}")

    ce_ltp = market_data.get_ltp(self.ce_key)
    pe_ltp = market_data.get_ltp(self.pe_key)

    if ce_ltp is None and pe_ltp is None:
        log(f"[ENTRY] ⚠ LTP fetch failed. Retrying...")
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

    # if keyboard.is_pressed("e"):
    if keyboard.is_pressed("up"):
        self.last_key_time = now
        self._end_session(broker)
        return

    # if keyboard.is_pressed("q"):
    if keyboard.is_pressed("down"):
        self.last_key_time = now
        self._force_exit(broker)
        return

    if self.trade_active:
        return

    if now - self.last_key_time < self.key_cooldown:
        return

    if self.order_in_progress:
        return

    # if keyboard.is_pressed("c"):
    if keyboard.is_pressed("right"):
        self.last_key_time = now
        self.order_in_progress = True
        self._place_trade("CE", broker, market_data)
        self.order_in_progress = False
        return

    # if keyboard.is_pressed("p"):
    if keyboard.is_pressed("left"):
        self.last_key_time = now
        self.order_in_progress = True
        self._place_trade("PE", broker, market_data)
        self.order_in_progress = False
        return

# ======================================================
# PLACE ENTRY TRADE
# ======================================================

 def _place_trade(self, side, broker, market_data):

    now = datetime.now()
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

    if not (market_open <= now <= market_close):
        log(f"[ENTRY] Market closed. Cannot place order.")
        return

    instrument_key = self.ce_key if side == "CE" else self.pe_key

    ltp = market_data.get_ltp(instrument_key)

    if not ltp:
        log(f"[ENTRY] Failed to fetch LTP.")
        return

    max_qty = INDEX_CONFIG[ACTIVE_INDEX]["max_gtt_quantity"]

    if self.quantity > max_qty:
        max_lots = max_qty // self.lot_size
        self.quantity = max_lots * self.lot_size

    entry_price = round_to_tick(ltp + INSTANT_ENGINE_CONFIG["entry_buffer"])
    # -------------------------------------------------
    # BAD PRICE PROTECTION
    # Prevent entries if price feed glitches
    # -------------------------------------------------
    if entry_price is None or entry_price <= 1:
        log(f"[ENTRY] Invalid entry price detected. Trade blocked.")
        return

    state_store = broker.data_provider.state_store
    state_store.manual_trade_active = True

    log(f"[ENTRY] \nPlacing Entry Order...")

    payload = {
        "quantity": self.quantity,
        "product": "D",
        "validity": "DAY",
        "price": entry_price,
        "instrument_token": instrument_key,
        "order_type": "LIMIT",
        "transaction_type": "BUY",
        "disclosed_quantity": 0,
        "trigger_price": 0,
        "is_amo": False,
        "slice": True,
        "tag": "ENTRY"
    }

    order_id = broker.place_order(payload)
    self.exit_engine.last_entry_price = entry_price
    self.exit_engine.last_entry_instrument = instrument_key

    if not order_id:
        log(f"[ENTRY] Entry placement failed.")
        return

    self.trade_active = True
    self.active_instrument = instrument_key
    self.active_side = side

    log(f"[ENTRY] Entry Active → {side} | Order: {order_id}")

# ======================================================
# FORCE EXIT
# ======================================================

 def _force_exit(self, broker):

    log(f"[ENTRY] \nForce Exit Triggered...")

    broker.flatten_and_verify()

    state_store = broker.data_provider.state_store
    state_store.manual_trade_active = False

    self.trade_active = False
    self.active_instrument = None
    self.active_side = None
    self.exit_engine.last_entry_price = None
    self.exit_engine.last_entry_instrument = None
    self.exit_engine.partial_exit_in_progress = False
    self.order_in_progress = False
    self.exit_engine.processing_instruments.clear()
    self.exit_engine.processed_positions.clear()
    log(f"[ENTRY] Monitoring resumed.")

# ======================================================
# END SESSION
# ======================================================

 def _end_session(self, broker):

    log(f"[ENTRY] \n🔴 SESSION TERMINATION INITIATED...")

    broker.flatten_and_verify()

    state_store = broker.data_provider.state_store
    state_store.manual_trade_active = False

    self.trade_active = False
    self.active_instrument = None
    self.active_side = None
    self.exit_engine.last_entry_price = None
    self.exit_engine.last_entry_instrument = None
    self.exit_engine.partial_exit_in_progress = False
    self.exit_engine.processing_instruments.clear()
    self.exit_engine.processed_positions.clear()

    log(f"[ENTRY] Shutting down system safely...")

    raise SystemExit
