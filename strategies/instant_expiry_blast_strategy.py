import time
import keyboard
from collections import deque

from config import (
    INSTANT_EXPIRY_BLAST_CONFIG as CONFIG,
    ACTIVE_INDEX,
    INDEX_CONFIG,
    INSTANT_ENGINE_CONFIG
)

from core.utils import log, round_to_tick


class InstantExpiryBlastStrategy:

    def __init__(self):

        # -------------------------------------------------
        # SESSION CONTROL
        # -------------------------------------------------
        self.trade_taken = False

        # -------------------------------------------------
        # MARKET STRUCTURE
        # -------------------------------------------------
        self.resistance = None
        self.support = None

        self.sweep_low = None
        self.sweep_high = None

        # -------------------------------------------------
        # OPTION TRACKING
        # -------------------------------------------------
        self.option_list = []
        self.option_buffers = {}
        self.volume_buffers = {}

        # -------------------------------------------------
        # ENTRY TRACKING
        # -------------------------------------------------
        self.instrument = None
        self.entry_price = None

        # -------------------------------------------------
        # LOOP CONTROL
        # -------------------------------------------------
        self.last_scan_time = 0
        self.scan_interval = 0.3

        print("\n======================================")
        print("Instant Expiry Blast Strategy Active")
        print("Detecting Institutional Spike Patterns")
        print("======================================\n")


    # =====================================================
    # MAIN STRATEGY LOOP
    # =====================================================

    def run(self, broker, market_data, risk_engine, instruments):

        # -------------------------------------------------
        # GLOBAL PNL GUARD
        # -------------------------------------------------
        if risk_engine:
            risk_engine.check_global_pnl()

        # -------------------------------------------------
        # KILL SWITCH
        # -------------------------------------------------
        if keyboard.is_pressed("up"):
            log("[BLAST] Kill switch activated")
            broker.flatten_and_verify()
            raise SystemExit

        # -------------------------------------------------
        # FORCE EXIT
        # -------------------------------------------------
        if keyboard.is_pressed("down"):
            log("[BLAST] Force exit triggered")
            broker.flatten_and_verify()
            self.trade_taken = True
            return

        # -------------------------------------------------
        # SINGLE TRADE PER SESSION
        # -------------------------------------------------
        if self.trade_taken:
            return

        now = time.time()

        if now - self.last_scan_time < self.scan_interval:
            return

        self.last_scan_time = now

        # -------------------------------------------------
        # BUILD OPTION LIST
        # -------------------------------------------------
        if not self.option_list:
            self._initialize_strikes(market_data, instruments)

        # -------------------------------------------------
        # UPDATE LIQUIDITY LEVELS
        # -------------------------------------------------
        self._update_liquidity_levels(market_data)

        # -------------------------------------------------
        # COMPRESSION DETECTION
        # -------------------------------------------------
        if not self._detect_compression(market_data):
            return

        # -------------------------------------------------
        # SWEEP DETECTION
        # -------------------------------------------------
        if not self._detect_liquidity_sweep(market_data):
            return

        accelerating_count = 0
        slope_signal_count = 0

        best_instrument = None
        best_strength = 0
        best_price = None

        for instrument in self.option_list:

            ltp = market_data.get_ltp(instrument)

            if not ltp:
                continue

            # -------------------------------------------------
            # MIN PREMIUM FILTER
            # -------------------------------------------------
            if ltp < CONFIG["min_option_premium"]:
                continue

            self._update_price_buffer(instrument, ltp)

            acceleration_strength = self._detect_premium_acceleration(instrument)

            if acceleration_strength:

                accelerating_count += 1

                if acceleration_strength > best_strength:
                    best_strength = acceleration_strength
                    best_instrument = instrument
                    best_price = ltp

            if self._detect_option_slope(instrument):
                slope_signal_count += 1

        # -------------------------------------------------
        # CLUSTER ACCELERATION ENTRY
        # -------------------------------------------------

        if accelerating_count >= CONFIG["cluster_option_threshold"]:

            log("[BLAST] Cluster acceleration detected")

            self._execute_trade(broker, market_data, best_instrument, best_price)

            return

        # -------------------------------------------------
        # HFT SLOPE IMBALANCE ENTRY
        # -------------------------------------------------

        if slope_signal_count >= CONFIG["slope_cluster_threshold"]:

            log("[BLAST] Option chain slope imbalance detected")

            self._execute_trade(broker, market_data, best_instrument, best_price)

            return


    # =====================================================
    # STRIKE INITIALIZATION
    # =====================================================

    def _initialize_strikes(self, market_data, instruments):

        expiry = instruments.get_nearest_expiry()

        index_symbol = INDEX_CONFIG[ACTIVE_INDEX]["index_symbol"]

        index_ltp = market_data.get_ltp(index_symbol)

        if not index_ltp:
            return

        strike_step = INDEX_CONFIG[ACTIVE_INDEX]["strike_step"]

        atm = round(index_ltp / strike_step) * strike_step

        strikes = []

        if CONFIG["use_fixed_offsets"]:

            for offset in CONFIG["strike_offsets"]:
                strikes.append(atm + offset)

        else:

            scan_range = CONFIG["strike_scan_range"]

            for offset in range(0, scan_range + strike_step, strike_step):
                strikes.append(atm + offset)

        exchange = INDEX_CONFIG[ACTIVE_INDEX]["exchange"]

        for strike in strikes:

            ce_token, lot = instruments.find_option(expiry, strike, "CE")
            pe_token, lot = instruments.find_option(expiry, strike, "PE")

            if ce_token:
                self.option_list.append(f"{exchange}|{ce_token}")

            if pe_token:
                self.option_list.append(f"{exchange}|{pe_token}")

        log(f"[BLAST] Monitoring {len(self.option_list)} options")


    # =====================================================
    # LIQUIDITY LEVELS
    # =====================================================

    def _update_liquidity_levels(self, market_data):

        index_symbol = INDEX_CONFIG[ACTIVE_INDEX]["index_symbol"]

        candles = market_data.market_data.get_last_n_minutes(
            index_symbol,
            CONFIG["liquidity_lookback_minutes"]
        )

        if not candles:
            return

        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]

        self.resistance = max(highs)
        self.support = min(lows)


    # =====================================================
    # COMPRESSION
    # =====================================================

    def _detect_compression(self, market_data):

        index_symbol = INDEX_CONFIG[ACTIVE_INDEX]["index_symbol"]

        candles = market_data.market_data.get_last_n_minutes(index_symbol, 10)

        if not candles or len(candles) < 5:
            return False

        ranges = [c[2] - c[3] for c in candles]

        avg_range = sum(ranges[:-2]) / len(ranges[:-2])

        last_range = ranges[-1]

        if last_range < avg_range * CONFIG["compression_factor"]:
            return True

        return False


    # =====================================================
    # LIQUIDITY SWEEP
    # =====================================================

    def _detect_liquidity_sweep(self, market_data):

        index_symbol = INDEX_CONFIG[ACTIVE_INDEX]["index_symbol"]

        candles = market_data.market_data.get_last_n_minutes(index_symbol, 3)

        if not candles or len(candles) < 2:
            return False

        c = candles[-1]

        open_p = c[1]
        high = c[2]
        low = c[3]
        close = c[4]

        body = abs(close - open_p)
        lower_wick = min(open_p, close) - low

        if lower_wick > body * 1.5:
            self.sweep_low = low
            return True

        return False


    # =====================================================
    # PRICE BUFFER
    # =====================================================

    def _update_price_buffer(self, instrument, price):

        if instrument not in self.option_buffers:
            self.option_buffers[instrument] = deque(maxlen=100)

        self.option_buffers[instrument].append(price)


    # =====================================================
    # PREMIUM ACCELERATION
    # =====================================================

    def _detect_premium_acceleration(self, instrument):

        buffer = self.option_buffers.get(instrument)

        if not buffer or len(buffer) < 5:
            return 0

        old_price = buffer[0]
        new_price = buffer[-1]

        pct_move = (new_price - old_price) / old_price

        if pct_move > CONFIG["premium_acceleration_pct"]:
            return pct_move

        return 0


    # =====================================================
    # OPTION SLOPE IMBALANCE
    # =====================================================

    def _detect_option_slope(self, instrument):

        buffer = self.option_buffers.get(instrument)

        if not buffer or len(buffer) < 4:
            return False

        p1 = buffer[-4]
        p2 = buffer[-3]
        p3 = buffer[-2]
        p4 = buffer[-1]

        if p1 < p2 < p3 < p4:
            return True

        return False


    # =====================================================
    # EXECUTE TRADE
    # =====================================================

    def _execute_trade(self, broker, market_data, instrument, ltp):

        if not instrument:
            return

        qty = INDEX_CONFIG[ACTIVE_INDEX]["lot_size"] * INSTANT_ENGINE_CONFIG["lots"]

        entry = round_to_tick(ltp)

        payload = {
            "quantity": qty,
            "product": "D",
            "validity": "DAY",
            "price": entry,
            "instrument_token": instrument,
            "order_type": "LIMIT",
            "transaction_type": "BUY",
            "slice": True,
            "tag": "BLAST_ENTRY"
        }

        order = broker.place_order(payload)

        if not order:
            log("[BLAST] Entry failed")
            return

        self.entry_price = entry
        self.instrument = instrument
        self.trade_taken = True

        log(f"[BLAST] Entry placed | {instrument} @ {entry}")

        self._monitor_exit(broker, market_data)


    # =====================================================
    # EXIT MONITOR
    # =====================================================

    def _monitor_exit(self, broker, market_data):

        fixed_target = self.entry_price + CONFIG["fixed_spike_points"]
        percent_target = self.entry_price * (1 + CONFIG["percent_spike_target"])

        start_time = time.time()

        while True:

            ltp = market_data.get_ltp(self.instrument)

            if not ltp:
                time.sleep(0.1)
                continue

            if ltp >= fixed_target or ltp >= percent_target:

                qty = INDEX_CONFIG[ACTIVE_INDEX]["lot_size"] * INSTANT_ENGINE_CONFIG["lots"]

                payload = {
                    "quantity": qty,
                    "product": "D",
                    "validity": "DAY",
                    "instrument_token": self.instrument,
                    "order_type": "MARKET",
                    "transaction_type": "SELL",
                    "slice": True,
                    "tag": "BLAST_EXIT"
                }

                broker.place_order(payload)

                log("[BLAST] Target exit executed")

                return

            if self.sweep_low and ltp <= self.sweep_low:

                broker.flatten_and_verify()

                log("[BLAST] Stop loss hit")

                return

            if time.time() - start_time > 60:

                broker.flatten_and_verify()

                log("[BLAST] Timeout exit")

                return

            time.sleep(0.1)