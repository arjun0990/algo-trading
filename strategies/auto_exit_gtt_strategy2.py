# strategies/auto_exit_gtt_strategy.py

import time
from config import AUTO_EXIT_GTT_CONFIG as CONFIG


class AutoExitGTTStrategy:

    def __init__(self):

        self.trade_active = False
        self.active_gtt_id = None
        self.active_instrument = None

        self.last_check_time = 0
        self.check_interval = CONFIG["position_check_interval"]


    # -------------------------------------------------
    # MAIN LOOP
    # -------------------------------------------------
    def run(self, broker, market_data, risk_engine, instruments):
        # print("AUTO_EXIT_GTT RUNNING...")
        now = time.time()

        if now - self.last_check_time < self.check_interval:
            return

        self.last_check_time = now

        if not self.trade_active:
            self._detect_new_position(broker)
        else:
            self._monitor_position(broker)

    def _check_existing_gtt(self, broker, instrument):

        gtts = broker.get_all_gtt_orders()

        if not gtts:
            return None

        for g in gtts:

            # Adjust according to actual API structure
            if (
                    g.get("instrument_token") == instrument
                    and g.get("status") in ["ACTIVE", "TRIGGER_PENDING"]
            ):
                return g.get("gtt_order_id")

        return None

    # -------------------------------------------------
    # Detect Manual Entry
    # -------------------------------------------------
    def _detect_new_position(self, broker):

        if self.trade_active:
            return

        positions = broker.get_positions()
        print("DEBUG POSITIONS LIVE:", positions)
        if not positions:
            return

        for p in positions:
            print("Checking position:", p)
            print("Quantity:", p.get("quantity"))
            qty = int(p.get("quantity", 0))

            if qty != 0:

                instrument = p["instrument_token"]
                avg_price = float(p.get("buy_price", 0))

                # ------------------------------------------------
                # NEW: Check if GTT already exists for instrument
                # ------------------------------------------------
                existing_gtt = self._check_existing_gtt(broker, instrument)

                if existing_gtt:
                    print("\n⚠ Existing GTT already active.")
                    print(f"Using GTT ID: {existing_gtt}")

                    self.trade_active = True
                    self.active_gtt_id = existing_gtt
                    self.active_instrument = instrument
                    return

                print("\n📈 Open Position Detected")
                print(f"Instrument: {instrument}")
                print(f"Avg Price: {avg_price}")
                print(f"Quantity: {qty}")

                self._place_exit_gtt(
                    broker,
                    instrument,
                    avg_price,
                    abs(qty)
                )

                return

    # -------------------------------------------------
    # Place Exit GTT (NO ENTRY LEG)
    # -------------------------------------------------
    def _place_exit_gtt(self, broker, instrument, entry_price, quantity):

        target_price = round(
            entry_price + CONFIG["target_points"], 2
        )

        sl_price = round(
            entry_price - CONFIG["sl_points"], 2
        )

        rules = [
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

        # Optional trailing
        if CONFIG["enable_trailing"]:

            difference = entry_price - sl_price
            min_trailing = 0.1 * difference
            trailing = CONFIG["trailing_points"]

            if trailing < min_trailing:
                print(f"⚠ Trailing too small. Min required: {min_trailing:.2f}")
                return

            stoploss_rule["trailing_gap"] = trailing

        rules.append(stoploss_rule)

        payload = {
            "type": "MULTIPLE",
            "quantity": quantity,
            "product": "D",
            "instrument_token": instrument,
            "transaction_type": "SELL",
            "rules": rules
        }

        print("\n🚀 Placing Exit GTT...")
        print(f"Entry: {entry_price}")
        print(f"Target: {target_price}")
        print(f"SL: {sl_price}")
        print(f"Qty: {quantity}")

        gtt_id = broker.place_gtt_order(payload)

        if not gtt_id:
            print("❌ Failed to place exit GTT.")
            return

        self.trade_active = True
        self.active_gtt_id = gtt_id
        self.active_instrument = instrument

        print(f"✅ Exit GTT Active | ID: {gtt_id}")

    def _get_last_completed_buy(self, broker, instrument_token, open_quantity):

        try:
            orders = broker.get_order_book()
        except Exception as e:
            print(f"❌ Failed to fetch order book: {e}")
            return None

        if not orders:
            return None

        valid_buys = []

        for order in orders:

            if order.get("status") != "COMPLETE":
                continue

            if order.get("transaction_type") != "BUY":
                continue

            if order.get("instrument_token") != instrument_token:
                continue

            filled_qty = order.get("filled_quantity") or order.get("quantity")

            # Extra safety — ensure it matches open position
            if filled_qty != open_quantity:
                continue

            valid_buys.append(order)

        if not valid_buys:
            return None

        # Sort by exchange timestamp (latest first)
        valid_buys.sort(
            key=lambda x: x.get("exchange_timestamp", ""),
            reverse=True
        )

        latest_buy = valid_buys[0]

        entry_price = latest_buy.get("average_price")

        if not entry_price or entry_price <= 0:
            return None

        return float(entry_price)

    # -------------------------------------------------
    # Monitor Position & Handle Manual Exit
    # -------------------------------------------------
    def _monitor_position(self, broker):

        positions = broker.get_positions()

        still_open = False

        for p in positions:
            if (
                p.get("instrument_token") == self.active_instrument
                and int(p.get("quantity", 0)) != 0
            ):
                still_open = True
                break

        if not still_open:

            print("\n⚠ Position Closed.")

            if self.active_gtt_id:
                print("Cancelling remaining GTT...")
                broker.cancel_gtt_order(self.active_gtt_id)

            print("Resetting strategy state.")

            self.trade_active = False
            self.active_gtt_id = None
            self.active_instrument = None