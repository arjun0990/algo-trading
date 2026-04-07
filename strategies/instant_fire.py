import time
from datetime import datetime
from control_server import get_command
import config
from config import INSTANT_ENGINE_CONFIG, ACTIVE_INDEX, INDEX_CONFIG
from core.utils import log, round_to_tick


class InstantFireStrategy:

 def __init__(self):
    self.trade_active = False
    self.current_atm = None
    self.active_side = None
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
    self.active_instrument = None
    self.target_order_id = None
    self.last_key_time = 0
    self.processing_instruments = set()
    self.processed_positions = set()
    self.last_entry_price = None
    self.last_entry_instrument = None
    self.auto_exit_enabled = True
    self.partial_fill_time = None
    self.partial_fill_order_id = None
    self.partial_filled_qty = 0
    self.partial_exit_in_progress = False
    self.position_detect_time = None
    self.risk_engine = None
    self.lot_size = None
    self.lots = max(1, INSTANT_ENGINE_CONFIG.get("lots", 1))
    self.quantity = 0
    self.gtt_enabled = False
    self.active_gtt_id = None
    self.base_payload_template = {
        "product": "D",
        "validity": "DAY",
        "transaction_type": "SELL",
    }
    self.target_points = INSTANT_ENGINE_CONFIG["target_points"]
    self.sl_points = INSTANT_ENGINE_CONFIG["sl_points"]
    self.target_step = 1
    self.sl_step = 1

    log(f"[INSTANT]\n======================================")
    log(f"INSTANT FIRE Entry Exit Strategy Active")
    log("━━━━━━━━━━ KEY CONTROLS ━━━━━━━━━━")

    # ---------------------------------
    # ENTRY / EXIT
    # ---------------------------------
    log("[CONTROL] → Press RIGHT ARROW → CE Trade")
    log("[CONTROL] → Press LEFT ARROW  → PE Trade")
    log("[CONTROL] → Press DOWN / Q    → Exit Everything")
    log("[CONTROL] → Press UP / E      → End Session")

    # ---------------------------------
    # MODE
    # ---------------------------------
    log("[CONTROL] → Press G → Enable GTT Exit Mode")
    log("[CONTROL] → Press N → Disable GTT Exit Mode")

    # ---------------------------------
    # AUTO EXIT
    # ---------------------------------
    log("[CONTROL] → Press X → Pause Auto Exit")
    log("[CONTROL] → Press R → Resume Auto Exit")

    # ---------------------------------
    # LOT CONTROL
    # ---------------------------------
    log("[CONTROL] → Press = → Increase Lots")
    log("[CONTROL] → Press - → Decrease Lots")

    # ---------------------------------
    # TARGET CONTROL
    # ---------------------------------
    log("[CONTROL] → Press ] → Increase Target")
    log("[CONTROL] → Press [ → Decrease Target")

    # ---------------------------------
    # SL CONTROL (GTT MODE)
    # ---------------------------------
    log("[CONTROL] → Press ' → Tighten SL (GTT)")
    log("[CONTROL] → Press ; → Loosen SL (GTT)")

    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log(f"[INSTANT] ======================================\n")

# ======================================================
# MAIN ENTRY
# ======================================================

 def run(self, broker, market_data, risk_engine, instruments):

     state_store = broker.data_provider.state_store
     self.risk_engine = risk_engine
     # -------------------------------------------------
     # INITIALIZATION (DO NOT BLOCK EVENT FLOW)
     # -------------------------------------------------
     if not self.initialized:
         self._initialize(instruments, market_data)

     # -------------------------------------------------
     # HANDLE MANUAL INPUT
     # -------------------------------------------------
     self._handle_keypress(broker, market_data)

     # -------------------------------------------------
     # LTP MONITOR (ONLY WHEN IDLE)
     # -------------------------------------------------
     if not self.trade_active:
         self._monitor_ltp(market_data, instruments)

     # -------------------------------------------------
     # CONSUME STREAM EVENTS (FIRST PRIORITY)
     # -------------------------------------------------
     position_changed = state_store.consume_position_changed()
     order_changed = state_store.consume_order_changed()

     # -------------------------------------------------
     # EVENT-DRIVEN GLOBAL RISK CHECK
     # -------------------------------------------------
     if position_changed or order_changed:
         self.risk_engine._last_event_time = time.time()
         self.risk_engine.check_global_pnl()

     # -------------------------------------------------
     # ORDER STREAM PROCESSING (ENTRY + PARTIAL FILL TRACK)
     # -------------------------------------------------
     if order_changed:

         orders = state_store.get_all_orders()

         for o in orders.values():

             if o.get("transaction_type").upper() != "BUY":
                 continue

             order_qty = int(o.get("quantity", 0))
             filled_qty = int(o.get("filled_quantity", 0))
             pending_qty = int(o.get("pending_quantity", 0))

             # -------------------------
             # PARTIAL FILL TRACKING
             # -------------------------
             if filled_qty > 0 and pending_qty > 0:

                 if self.partial_fill_order_id != o.get("order_id"):
                     self.partial_fill_order_id = o.get("order_id")
                     self.partial_fill_time = time.time()
                     self.partial_filled_qty = filled_qty

             # -------------------------
             # COMPLETE ORDER → CAPTURE ENTRY
             # -------------------------
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

     # -------------------------------------------------
     # PARTIAL FILL TIMEOUT HANDLING
     # -------------------------------------------------
     positions = state_store.get_all_positions()
     current_qty = positions.get(self.last_entry_instrument, 0)

     if self.partial_fill_time and int(current_qty) > 0:

         if time.time() - self.partial_fill_time > 3:

             orders = state_store.get_all_orders()
             order = orders.get(self.partial_fill_order_id)

             if order:

                 pending_qty = int(order.get("pending_quantity", 0))
                 filled_qty = int(order.get("filled_quantity", 0))

                 if pending_qty > 0:

                     log("[EXIT_ENGINE] Partial fill timeout → cancelling remaining qty")

                     broker.cancel_order(self.partial_fill_order_id)
                     time.sleep(0.05)

                     orders = state_store.get_all_orders()
                     order = orders.get(self.partial_fill_order_id)

                     if not order:
                         return

                     filled_qty = int(order.get("filled_quantity", 0))
                     instrument = order.get("instrument_token")
                     entry_price = float(order.get("average_price", 0))

                     if filled_qty > 0 and entry_price > 0 and self.auto_exit_enabled:
                         self.partial_exit_in_progress = True
                         # -------------------------------------------------
                         # EXIT ENGINE DECISION (GTT vs NORMAL)
                         # -------------------------------------------------
                         if self.gtt_enabled:

                             log("[EXIT_ENGINE] Using GTT EXIT")

                             self._place_gtt_exit_orders(
                                 broker,
                                 instrument,
                                 entry_price,
                                 filled_qty,
                             )

                         else:

                             log("[EXIT_ENGINE] Using NORMAL BRACKET")

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

     # -------------------------------------------------
     # POSITION DETECTION (ENTRY → EXIT ENGINE)
     # -------------------------------------------------
     if self.auto_exit_enabled:

         if order_changed and not self.trade_active:
             self._detect_new_position(broker)

         if position_changed and not self.trade_active:
             self._detect_new_position(broker)

     # -------------------------------------------------
     # MONITOR EXIT (POSITION CHANGE)
     # -------------------------------------------------
     if position_changed and self.trade_active:
         self._monitor_position(broker)

     # -------------------------------------------------
     # MICRO TRADE-LEVEL RISK CHECK (ULTRA FAST)
     # -------------------------------------------------
     if (
             (position_changed or order_changed)
             and self.trade_active
             and self.active_instrument
             and self.last_entry_price
             and self.risk_engine
     ):

         qty = abs(positions.get(self.active_instrument, 0))

         if qty > 0:
             self.risk_engine.check_trade_level_risk(
                 self.active_instrument,
                 self.last_entry_price,
                 qty
             )

     # -------------------------------------------------
     # TARGET COMPLETION FALLBACK (CRITICAL FIX)
     # -------------------------------------------------
     if order_changed and self.trade_active and self.target_order_id:

         orders = state_store.get_all_orders()
         target_order = orders.get(self.target_order_id)

         if target_order and target_order.get("status", "").lower() == "complete":
             self._monitor_position(broker)

     # -------------------------------------------------
     # FINAL SAFETY RESET (ONLY AFTER EVENTS)
     # -------------------------------------------------
     positions = state_store.get_all_positions()

     if self.trade_active:
         if not positions or all(int(qty) == 0 for qty in positions.values()):
             log("[ENTRY_ENGINE] Position closed → Entry engine reset")
             self.trade_active = False

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
    atm = int(round(index_ltp / strike_step)) * strike_step
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

    # -------------------------------------------------
    # SENSEX OFFSET CORRECTION (IMPORTANT)
    # -------------------------------------------------
    if ACTIVE_INDEX == "SENSEX":

        strike_step = INDEX_CONFIG[ACTIVE_INDEX]["strike_step"]

        # If offset is multiple of 50 but not valid for 100-step strikes
        if offset % 50 == 0 and offset % strike_step != 0:
            corrected_offset = offset + 50
            log(f"[ENTRY] Adjusting strike_offset for SENSEX: {offset} → {corrected_offset}")
            offset = corrected_offset

    ce_strike = atm + offset
    pe_strike = atm - offset

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

    # self.lot_size = lot_size
    # self.quantity = lot_size * INSTANT_ENGINE_CONFIG["lots"]
    self.lot_size = lot_size
    self.quantity = self.lots * self.lot_size

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

        new_atm = int(round(index_ltp / strike_step)) * strike_step

        if self.last_atm is not None and new_atm != self.last_atm:

            if self.current_atm is None:
                return

            if abs(index_ltp - self.current_atm) >= 25:

                self.current_atm = new_atm
                offset = INSTANT_ENGINE_CONFIG["strike_offset"]

                # -------------------------------------------------
                # SENSEX OFFSET CORRECTION (IMPORTANT)
                # -------------------------------------------------
                if ACTIVE_INDEX == "SENSEX":

                    strike_step = INDEX_CONFIG[ACTIVE_INDEX]["strike_step"]

                    # If offset is multiple of 50 but not valid for 100-step strikes
                    if offset % 50 == 0 and offset % strike_step != 0:
                        corrected_offset = offset + 50
                        log(f"[ENTRY] Adjusting strike_offset for SENSEX: {offset} → {corrected_offset}")
                        offset = corrected_offset

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

                    # self.quantity = lot_size * INSTANT_ENGINE_CONFIG["lots"]
                    self.quantity = self.lots * self.lot_size
                    self.current_ce_strike = new_ce_strike
                    self.current_pe_strike = new_pe_strike
                    self.last_atm = new_atm

                    log(f"[ENTRY]\n🔄 ATM Shift Detected → Strikes Updated")
                    log(f"[ENTRY]New CE Strike: {new_ce_strike}")
                    log(f"[ENTRY]New PE Strike: {new_pe_strike}")

# ======================================================
# HANDLE KEY
# ======================================================

 def _handle_keypress(self, broker, market_data):


  now = time.time()

  cmd = get_command()
  
  # debounce
  if cmd and (now - self.last_key_time < 0.3):
    return
  if cmd:
   self.last_key_time = now

# =========================
# EXIT / SESSION CONTROL
# =========================
  if cmd == "END":
   self._end_session(broker)
   return

  if cmd == "EXIT":
   print("CMD RECEIVED:", cmd)
   log("[EXIT_ENGINE] EXIT ALL TRIGGERED")
   self._force_exit(broker)
   return

# =========================
# MODE TOGGLES
# =========================
  if cmd == "GTT_ON":
   self.gtt_enabled = True
   log("[MODE] GTT EXIT ENABLED")
   return

  if cmd == "GTT_OFF":
   self.gtt_enabled = False
   log("[MODE] GTT EXIT DISABLED")
   return

  if cmd == "AUTO_PAUSE":
   self.auto_exit_enabled = False
   log("[EXIT_ENGINE] AUTO EXIT PAUSED")
   return

  if cmd == "AUTO_RESUME":
   self.auto_exit_enabled = True
   log("[EXIT_ENGINE] AUTO EXIT RESUMED")
   self._force_exit(broker)
   return

# =========================
# TRADE ACTIVE ADJUSTMENTS
# =========================
  if self.trade_active:
   if cmd == "TGT_UP":
    self.target_points += self.target_step
    log(f"[ADJUST] Target ↑ → {self.target_points}")
    self._update_exit_orders(broker, update_target=True)

   if cmd == "TGT_DOWN":
    self.target_points -= self.target_step
    log(f"[ADJUST] Target ↓ → {self.target_points}")
    self._update_exit_orders(broker, update_target=True)

   if cmd == "SL_UP":
    self.sl_points -= self.sl_step
    log(f"[ADJUST] SL ↑ → {self.sl_points}")
    self._update_exit_orders(broker, update_sl=True)

   if cmd == "SL_DOWN":
    self.sl_points += self.sl_step
    log(f"[ADJUST] SL ↓ → {self.sl_points}")
    self._update_exit_orders(broker, update_sl=True)

   return

# =========================
# ENTRY BLOCK
# =========================
  if cmd is None and (now - self.last_key_time < self.key_cooldown):
    return

  if self.order_in_progress:
   return

# LOT INCREASE
  if cmd == "LOTS_UP":
   self.lots += 1
   if self.lot_size:
    self.quantity = self.lots * self.lot_size
    log(f"[ENTRY_ENGINE] Lots Increased → {self.lots} lots ({self.quantity} qty)")
    return

# LOT DECREASE
  if cmd == "LOTS_DOWN":
   if self.lots > 1:
    self.lots -= 1
    if self.lot_size:
     self.quantity = self.lots * self.lot_size
     log(f"[ENTRY_ENGINE] Lots Decreased → {self.lots} lots ({self.quantity} qty)")
    else:
     log("[ENTRY_ENGINE] Minimum 1 lot required")
    return

# =========================
# ENTRY TRIGGERS
# =========================
  if cmd == "CE":
   self.order_in_progress = True
   self._place_trade("CE", broker, market_data)
   self.order_in_progress = False
   return

  if cmd == "PE":
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
    if self.risk_engine:
        self.risk_engine.check_global_pnl()
    instrument_key = self.ce_key if side == "CE" else self.pe_key

    ltp = market_data.get_ltp(instrument_key)

    if ltp is None:
        log(f"[ENTRY] Failed to fetch LTP.")
        return

    max_qty = INDEX_CONFIG[ACTIVE_INDEX]["max_gtt_quantity"]

    if self.quantity > max_qty:
        max_lots = max_qty // self.lot_size
        self.quantity = max_lots * self.lot_size
    log(f"[DEBUG] Using token: {config.ACCESS_TOKEN[:10]}...")
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
    if entry_price <= ltp:
        log("[ENTRY] Invalid SL-M → already above trigger")
        return
    log(f"[ENTRY] \nPlacing KEYPRESS Entry Order... LTP IS : {ltp}  and entry price is : {entry_price} ")

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
    }

    # -------------------------------
    # SL-M ORDER (BREAKOUT ENTRY)
    # -------------------------------
    # payload = {
    #     "quantity": self.quantity,
    #     "product": "D",
    #     "validity": "DAY",
    #     "price": float(round(entry_price+0.1, 2)),
    #     "instrument_token": instrument_key,
    #     "order_type": "SL",
    #     "transaction_type": "BUY",
    #     "disclosed_quantity": 0,
    #     "trigger_price": float(round(entry_price, 2)),
    #     "is_amo": False,
    #     "slice": True
    # }


    order_id = broker.place_order(payload)
    self.last_entry_price = entry_price
    self.last_entry_instrument = instrument_key

    if not order_id:
        log(f"[ENTRY] Entry placement failed.")
        return

    # self.trade_active = True
    # self.active_instrument = instrument_key
    self.active_side = side

    log(f"[ENTRY] Entry Active → {side} | Order: {order_id}")

# ======================================================
# FORCE EXIT
# ======================================================

 def _force_exit(self, broker):

    log("[EXIT_ENGINE] 🚨 KILL SWITCH ACTIVATED")
    state_store = broker.data_provider.state_store
    positions = state_store.get_all_positions()

    # -------------------------------------------------
    # 1. CANCEL ALL PENDING ORDERS (MOST IMPORTANT)
    # -------------------------------------------------
    try:
        broker.cancel_all_pending_orders()
        log("[EXIT_ENGINE] All pending orders cancelled")
    except Exception as e:
        log(f"[EXIT_ENGINE] Cancel all failed: {e}")

    # -------------------------------------------------
    # 2. CANCEL GTT (IF ANY)
    # -------------------------------------------------
    if self.active_gtt_id:
        try:
            broker.cancel_gtt_order(self.active_gtt_id)
            log(f"[GTT] Cancelled GTT → {self.active_gtt_id}")
        except Exception as e:
            log(f"[GTT] Cancel failed: {e}")

        self.active_gtt_id = None

    # -------------------------------------------------
    # 3. FLATTEN POSITIONS (IF ANY)
    # -------------------------------------------------

    if positions and any(int(qty) != 0 for qty in positions.values()):
        broker.flatten_and_verify()
        log("[EXIT_ENGINE] Positions flattened")
    else:
        log("[EXIT_ENGINE] No positions → skip flatten")

    state_store.manual_trade_active = False
    self.trade_active = False
    self.active_instrument = None
    self.active_side = None
    self.last_entry_price = None
    self.last_entry_instrument = None
    self.partial_exit_in_progress = False
    self.order_in_progress = False
    # release duplicate protection locks
    self.processing_instruments.clear()
    self.processed_positions.clear()
    log("[EXIT_ENGINE] All exits cancelled")
    log("[EXIT_ENGINE] All positions exited")
    self.target_order_id = None
    self.position_detect_time = None
    self.active_gtt_id = None
    log("[EXIT_ENGINE] AUTO EXIT RESUMED")
    self.target_points = INSTANT_ENGINE_CONFIG["target_points"]
    self.sl_points = INSTANT_ENGINE_CONFIG["sl_points"]
    # reset exit engine state
    self.partial_fill_time = None
    self.partial_fill_order_id = None
    self.partial_filled_qty = 0
    log(f"[ENTRY] Monitoring resumed.")

 # ======================================================
# END SESSION
# ======================================================

 def _end_session(self, broker):

    log(f"[ENTRY] \n🔴 SESSION TERMINATION INITIATED...")
    self._force_exit(broker)
    log(f"[ENTRY] Shutting down system safely...")

    raise SystemExit

# -------------------------------------------------
# Detect New Position (STREAM DRIVEN)
# -------------------------------------------------
 # MODIFICATION 2 : AFTER DETECTING BIG QUANTITIES OR SPLIT QUANTITIES[CONSIDERING MULTIPLE BUY ORDERS]
 def _detect_new_position(self, broker):

     # ---------------------------------
     # HARD GUARDS (NO DUPLICATES)
     # ---------------------------------
     if self.trade_active or self.partial_exit_in_progress:
         return

     from datetime import datetime, timedelta

     state_store = broker.data_provider.state_store

     # mark detection time (used for stale filtering)
     self.position_detect_time = datetime.now()

     orders = state_store.get_all_orders()
     if not orders:
         return

     # ---------------------------------
     # STEP 1: FIND LATEST BUY INSTRUMENT
     # ---------------------------------
     latest_order = None

     for o in orders.values():

         if o.get("transaction_type", "").upper() != "BUY":
             continue

         if o.get("status", "").lower() != "complete":
             continue

         if not latest_order or int(o.get("order_id") or 0) > int(latest_order.get("order_id") or 0):
             latest_order = o

     if not latest_order:
         return

     instrument = latest_order.get("instrument_token")
     if not instrument:
         return

     # ---------------------------------
     # ACTIVE TRADE SAFETY
     # ---------------------------------
     if instrument == self.active_instrument and self.trade_active:
         return

     # ---------------------------------
     # DUPLICATE PROTECTION
     # ---------------------------------
     if instrument in self.processing_instruments:
         return

     if instrument in self.processed_positions:
         return

     # ---------------------------------
     # STEP 2: GET POSITION (GROUND TRUTH)
     # ---------------------------------
     positions = state_store.get_all_positions()
     position_qty = abs(int(positions.get(instrument, 0)))

     if position_qty == 0:
         return

     # ---------------------------------
     # STEP 3: AGGREGATE FILLED BUY ORDERS
     # ---------------------------------
     total_filled = 0
     weighted_price_sum = 0.0

     for o in orders.values():

         if o.get("transaction_type", "").upper() != "BUY":
             continue

         if o.get("instrument_token") != instrument:
             continue

         if o.get("status", "").lower() != "complete":
             continue

         # ---------------------------------
         # STALE ORDER FILTER (IMPORTANT)
         # ---------------------------------
         order_ts = o.get("exchange_timestamp")

         if order_ts:
             try:
                 order_time = datetime.strptime(order_ts, "%Y-%m-%d %H:%M:%S")
                 if order_time < (self.position_detect_time - timedelta(seconds=120)):
                     continue
             except (ValueError, TypeError):
                 continue

         filled_qty = int(o.get("filled_quantity", 0))
         avg_price = float(o.get("average_price", 0))

         if filled_qty <= 0 or avg_price <= 0:
             continue

         total_filled += filled_qty
         weighted_price_sum += (filled_qty * avg_price)

     # ---------------------------------
     # STEP 4: STRICT FULL-FILL MATCH
     # ---------------------------------
     if total_filled != position_qty:
         return  # still partial → do nothing

     # ---------------------------------
     # STEP 5: TRUE ENTRY PRICE
     # ---------------------------------
     entry_price = weighted_price_sum / total_filled if total_filled > 0 else 0

     if entry_price <= 0:
         return

     quantity = position_qty

     log(f"[EXIT_ENGINE] ⚡ AGGREGATED ENTRY DETECTED | Price: {entry_price} | Qty: {quantity}")

     # ---------------------------------
     # LOCK (PREVENT RACE)
     # ---------------------------------
     self.processing_instruments.add(instrument)

     # ---------------------------------
     # STEP 6: PLACE EXIT
     # ---------------------------------
     if self.gtt_enabled:

         log("[EXIT_ENGINE] ⚡ Using GTT EXIT")

         success = self._place_gtt_exit_orders(
             broker,
             instrument,
             entry_price,
             quantity
         )

     else:

         log("[EXIT_ENGINE] ⚡ Using NORMAL BRACKET")

         success = self._place_bracket_orders(
             broker,
             instrument,
             entry_price,
             quantity,
             "D"
         )

     # ---------------------------------
     # STEP 7: FINAL STATE UPDATE
     # ---------------------------------
     if success:
         self.trade_active = True
         self.active_instrument = instrument
         self.last_entry_price = entry_price
         self.last_entry_instrument = instrument
         self.processed_positions.add(instrument)

     # ---------------------------------
     # RELEASE LOCK
     # ---------------------------------
     self.processing_instruments.discard(instrument)


 # WORKING OLD : BEFORE ANY MODIFICATIONS 27/03/2026 evening working
 # def _detect_new_position(self, broker):
 #
 #     if self.trade_active or self.partial_exit_in_progress:
 #         return
 #
 #     state_store = broker.data_provider.state_store
 #     positions = state_store.get_all_positions()
 #
 #     if not positions:
 #         return
 #
 #     from datetime import datetime
 #     self.position_detect_time = datetime.now()
 #
 #     for instrument, qty in positions.items():
 #
 #         # Prevent duplicate trigger while trade active
 #         if instrument == self.active_instrument and self.trade_active:
 #             continue
 #
 #         if instrument in self.processing_instruments:
 #             continue
 #
 #         if instrument in self.processed_positions:
 #             continue
 #
 #         qty = int(qty)
 #
 #         if qty == 0:
 #             continue
 #
 #         log(f"[EXIT_ENGINE] Open Position | Instrument: {instrument} | Qty: {qty}")
 #
 #         # =========================================================
 #         # UNIFIED ENTRY PRICE DETECTION (ENGINE + MANUAL)
 #         # =========================================================
 #
 #         entry_price = None
 #         orders = state_store.get_all_orders()
 #
 #         valid_buys = []
 #
 #         for o in orders.values():
 #
 #             if o.get("instrument_token") != instrument:
 #                 continue
 #
 #             if o.get("transaction_type").upper() != "BUY":
 #                 continue
 #
 #             if o.get("status", "").lower() != "complete":
 #                 continue
 #
 #             valid_buys.append(o)
 #
 #         if not valid_buys:
 #             continue
 #
 #         # 🔥 SORT BY ORDER_ID FIRST (MOST RELIABLE)
 #         valid_buys.sort(
 #             key=lambda x: (
 #                 int(x.get("order_id") or 0),
 #                 x.get("exchange_timestamp") or "",
 #                 x.get("order_timestamp") or ""
 #             ),
 #             reverse=True
 #         )
 #
 #         latest_buy = None
 #         position_qty = abs(qty)
 #
 #         for o in valid_buys:
 #
 #             order_qty = int(o.get("quantity", 0))
 #             filled_qty = int(o.get("filled_quantity", 0))
 #             pending_qty = int(o.get("pending_quantity", 0))
 #
 #             # 🔴 STRICT MATCH CONDITIONS
 #             if pending_qty != 0:
 #                 continue
 #
 #             if filled_qty != order_qty:
 #                 continue
 #
 #             if filled_qty != position_qty:
 #                 continue
 #
 #             ts = o.get("exchange_timestamp")
 #
 #             if ts and self.position_detect_time:
 #                 from datetime import datetime, timedelta
 #
 #                 order_time = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
 #
 #                 if order_time < (self.position_detect_time - timedelta(seconds=60)):
 #                     continue
 #
 #             latest_buy = o
 #             break
 #
 #         if not latest_buy:
 #             continue
 #
 #         entry_price = float(latest_buy.get("average_price", 0))
 #
 #         if entry_price <= 0:
 #             continue
 #
 #         log(f"[EXIT_ENGINE] Entry Matched | Price: {entry_price}")
 #
 #         # 🔒 prevent duplicate exit placements
 #         if instrument in self.processed_positions:
 #             continue
 #
 #         if instrument in self.processing_instruments:
 #             continue
 #
 #         self.processing_instruments.add(instrument)
 #
 #         if self.gtt_enabled:
 #
 #             log("[EXIT_ENGINE] Using GTT EXIT")
 #
 #             self._place_gtt_exit_orders(
 #                 broker,
 #                 instrument,
 #                 entry_price,
 #                 abs(qty)
 #             )
 #
 #             success = True
 #
 #         else:
 #
 #             success = self._place_bracket_orders(
 #                 broker,
 #                 instrument,
 #                 entry_price,
 #                 abs(qty),
 #                 "D"
 #             )
 #
 #         if success:
 #             self.trade_active = True
 #             self.active_instrument = instrument
 #             self.processed_positions.add(instrument)
 #
 #         return



 # def _place_bracket_orders(self, broker, instrument, entry_price, quantity, product):
 #     state_store = broker.data_provider.state_store
 #     current_positions = state_store.get_all_positions()
 #
 #     if self.gtt_enabled:
 #         log("GTT ENABLED. skipping placing normal bracket orders")
 #         return False
 #
 #     qty1 = int(current_positions.get(instrument, 0))
 #
 #     time.sleep(0.05)
 #
 #     current_positions = state_store.get_all_positions()
 #     qty2 = int(current_positions.get(instrument, 0))
 #
 #     if qty1 != qty2:
 #         return False
 #
 #     if qty2 != quantity:
 #         return False
 #     if abs(qty2) > quantity:
 #         log("[EXIT_ENGINE] Position mismatch detected → flattening")
 #         broker.flatten_and_verify()
 #         return False
 #
 #     target_price = round_to_tick(entry_price + INSTANT_ENGINE_CONFIG["target_points"])
 #
 #     log(
 #         f"[EXIT_ENGINE] Placing Bracket | "
 #         f"Entry: {entry_price} | Target: {target_price} | "
 #         f"Qty: {quantity}"
 #     )
 #
 #     # TARGET LIMIT
 #
 #     payload = {
 #         "quantity": quantity,
 #         "product": product,
 #         "validity": "DAY",
 #         "price": target_price,
 #         "instrument_token": instrument,
 #         "order_type": "LIMIT",
 #         "transaction_type": "SELL",
 #         "disclosed_quantity": 0,
 #         "trigger_price": 0,
 #         "is_amo": False,
 #         "slice": True,
 #     }
 #
 #     target_id = broker.place_order(payload)
 #
 #     if not target_id:
 #         log("[EXIT_ENGINE] Target order failed. Retrying...")
 #         target_id = broker.place_order({
 #             "quantity": quantity,
 #             "product": product,
 #             "validity": "DAY",
 #             "price": target_price,
 #             "instrument_token": instrument,
 #             "order_type": "LIMIT",
 #             "transaction_type": "SELL",
 #             "disclosed_quantity": 0,
 #             "trigger_price": 0,
 #             "is_amo": False,
 #             "slice": True,
 #         })
 #
 #     if not target_id:
 #         log("[EXIT_ENGINE] ERROR: Target order failed")
 #
 #         self.processing_instruments.discard(instrument)
 #
 #         return False
 #
 #     if target_id and target_id.get("status") == "success":
 #         self.target_order_id = target_id["data"]["order_ids"][0]
 #     else:
 #         self.target_order_id = None
 #
 #
 #     log(f"[EXIT_ENGINE] Target placed | ID: {target_id}")
 #     self.partial_fill_time = None
 #     self.partial_fill_order_id = None
 #     self.partial_filled_qty = 0
 #     self.processing_instruments.discard(instrument)
 #
 #     return True

 def _place_bracket_orders(self, broker, instrument, entry_price, quantity, product):

     # ---------------------------------
     # GTT MODE CHECK
     # ---------------------------------
     if self.gtt_enabled:
         log("[EXIT_ENGINE] GTT enabled → skipping normal bracket")
         return False

     # ---------------------------------
     # MINIMAL SAFETY CHECK (NON-BLOCKING)
     # ---------------------------------
     state_store = broker.data_provider.state_store
     current_qty = int(state_store.get_position(instrument) or 0)

     # Ensure position exists (no delay)
     if abs(current_qty) < quantity:
         log("[EXIT_ENGINE] Qty not ready → skip (ultra-fast mode)")
         return False

     # ---------------------------------
     # TARGET CALCULATION (FAST)
     # ---------------------------------
     target_price = round_to_tick(entry_price + INSTANT_ENGINE_CONFIG["target_points"])

     log(
         f"[EXIT_ENGINE] ⚡ FAST BRACKET | "
         f"Entry: {entry_price} | Target: {target_price} | Qty: {quantity}"
     )

     # ---------------------------------
     # PLACE TARGET ORDER (NO RETRY BLOCKING)
     # ---------------------------------
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
     }

     target_id = broker.place_order(payload)

     # ---------------------------------
     # HANDLE FAILURE (NON-BLOCKING)
     # ---------------------------------
     if not target_id or target_id.get("status") != "success":
         log("[EXIT_ENGINE] ❌ Target placement failed (no retry to save latency)")
         self.processing_instruments.discard(instrument)
         return False

     # ---------------------------------
     # STORE TARGET ID
     # ---------------------------------
     self.target_order_id = target_id["data"]["order_ids"][0]

     log(f"[EXIT_ENGINE] ⚡ Target placed | ID: {self.target_order_id}")

     # ---------------------------------
     # CLEAN PARTIAL STATE
     # ---------------------------------
     self.partial_fill_time = None
     self.partial_fill_order_id = None
     self.partial_filled_qty = 0

     self.processing_instruments.discard(instrument)

     return True

 def _place_gtt_exit_orders(self, broker, instrument, entry_price, quantity):

         # Prevent duplicate GTT
         if self.active_gtt_id:
             log("[GTT] Already active → skipping")
             return False

         if not self.gtt_enabled:
             log("GTT NOT ENABLED..skipping placing gtt exit orders.")
             return False
         # -------------------------------------------------
         # CALCULATE TARGET & SL (BUY ONLY SYSTEM)
         # -------------------------------------------------
         target_price = round(entry_price + INSTANT_ENGINE_CONFIG["target_points"], 2)
         sl_price = round(entry_price - INSTANT_ENGINE_CONFIG["sl_points"], 2)

         # -------------------------------------------------
         # BUILD RULES (NO ENTRY RULE)
         # -------------------------------------------------
         rules = [
             {
                 "strategy": "TARGET",
                 "trigger_type": "IMMEDIATE",
                 "trigger_price": target_price
             },
             {
                 "strategy": "STOPLOSS",
                 "trigger_type": "IMMEDIATE",
                 "trigger_price": sl_price
             }
         ]

         # -------------------------------------------------
         # BUILD PAYLOAD
         # -------------------------------------------------
         # payload = dict(self.base_payload_template)
         payload: dict = dict(self.base_payload_template)
         payload["quantity"] = quantity
         payload["instrument_token"] = instrument
         payload["rules"] = rules

         log(f"[GTT] Placing EXIT GTT | Qty: {quantity} | Entry: {entry_price}")

         gtt_id = broker.place_gtt_order(payload)

         if not gtt_id:
             log("[GTT] Placement failed")
             return False

         self.active_gtt_id = gtt_id

         log(f"[GTT] EXIT GTT ACTIVE → ID: {gtt_id}")
         return True


 def _update_exit_orders(self, broker, update_target=False, update_sl=False):

     # -----------------------------------
     # SAFETY CHECK
     # -----------------------------------
     if not self.trade_active or not self.active_instrument:
         return

     entry = self.last_entry_price

     state_store = broker.data_provider.state_store
     qty = state_store.get_position(self.active_instrument)

     if not entry or not qty:
         return

     # -----------------------------------
     # CALCULATE PRICES
     # -----------------------------------
     target_price = round(entry + self.target_points, 2)
     sl_price = round(entry - self.sl_points, 2)

     # -----------------------------------
     # ROUTING
     # -----------------------------------
     if self.active_gtt_id :

         self._modify_gtt_orders(
             broker,
             target_price,
             sl_price,
             update_target,
             update_sl
         )

     else:

         if update_target:
             self._modify_normal_target(broker, target_price)

 def _modify_normal_target(self, broker, target_price):
     orders = broker.data_provider.state_store.get_all_orders()
     order = orders.get(self.target_order_id)
     if self.gtt_enabled:
         log("GTT ENABLED..skipping modifying normal order target")
         return
     if not order or order.get("status") != "open":
         return
     if not self.target_order_id:
         return
     state_store = broker.data_provider.state_store
     orders = state_store.get_all_orders()

     order = orders.get(self.target_order_id)

     if not order:
         log("[UPDATE] Target order not found → skipping")
         return

     if order.get("status", "").lower() != "open":
         log("[UPDATE] Target order not open → skipping")
         return

     # Prevent invalid target
     if target_price <= self.last_entry_price:
         log("[WARNING] Invalid target → skipping")
         return

     try:
         broker.modify_order(
             order_id=self.target_order_id,
             price=target_price
         )

         log(f"[UPDATE] Target modified → {target_price}")

     except Exception as e:
         log(f"[ERROR] Target modify failed: {e}")

 def _modify_gtt_orders(self, broker, target_price, sl_price, update_target, update_sl):

     if not self.active_gtt_id:
         return

     if not self.gtt_enabled:
         log("GTT NOT ENABLED..skipping modifying gtt orders.")
         return

     rules = []

     # -----------------------------------
     # TARGET
     # -----------------------------------
     if update_target:

         if target_price <= self.last_entry_price:
             log("[WARNING] Invalid target → skipping")
         else:
             rules.append({
                 "strategy": "TARGET",
                 "trigger_type": "IMMEDIATE",
                 "trigger_price": target_price
             })

     # -----------------------------------
     # SL
     # -----------------------------------
     if update_sl:

         if sl_price >= self.last_entry_price:
             log("[WARNING] Invalid SL → skipping")
         else:
             rules.append({
                 "strategy": "STOPLOSS",
                 "trigger_type": "IMMEDIATE",
                 "trigger_price": sl_price
             })

     if not rules:
         return

     try:
         broker.modify_gtt_order(
             gtt_order_id=self.active_gtt_id,
             rules=rules
         )

         log(f"[GTT UPDATE] {rules}")

     except Exception as e:
         log(f"[GTT ERROR] Modify failed: {e}")

 # -------------------------------------------------
 # Monitor Position
 # -------------------------------------------------

 def _monitor_position(self, broker):

     state_store = broker.data_provider.state_store
     positions = state_store.get_all_positions()

     qty = positions.get(self.active_instrument, 0)
     still_open = int(qty) != 0


     # -------------------------------------------------
     # POSITION CLOSED → HANDLE EXIT
     # -------------------------------------------------
     if not still_open:

         orders = state_store.get_all_orders()

         target_filled = False

         # -------------------------------------------------
         # CHECK TARGET STATUS (IF EXISTS)
         # -------------------------------------------------
         if self.target_order_id:
             order = orders.get(self.target_order_id)

             if order and order.get("status", "").lower() == "complete":
                 target_filled = True

         # -------------------------------------------------
         # LOG EXIT TYPE
         # -------------------------------------------------
         if target_filled:
             log("[EXIT_ENGINE] Position Closed (Target Hit) → Resetting Engine")
         else:
             log("[EXIT_ENGINE] Manual/External Exit Detected → Resetting Engine")

         # -------------------------------------------------
         # COMMON RESET (CRITICAL)
         # -------------------------------------------------
         self.trade_active = False
         self.active_instrument = None
         self.active_side = None
         self.last_entry_price = None
         self.last_entry_instrument = None
         self.target_order_id = None
         self.active_gtt_id = None
         self.partial_exit_in_progress = False
         self.order_in_progress = False

         # duplicate protection reset
         self.processing_instruments.clear()
         self.processed_positions.clear()

         # timing / tracking reset
         self.position_detect_time = None
         self.partial_fill_time = None
         self.partial_fill_order_id = None
         self.partial_filled_qty = 0
         self.target_points = INSTANT_ENGINE_CONFIG["target_points"]
         self.sl_points = INSTANT_ENGINE_CONFIG["sl_points"]
         log("[EXIT_ENGINE] Engine Reset Complete")

