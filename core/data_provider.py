# core/data_provider.py
from config import STREAM_CONFIG
from core.utils import log
import time

class DataProvider:
    """
    Thin abstraction layer between strategies and data source.
    Prefers streaming data (StateStore) if available and healthy.
    Falls back to REST via broker/market_data when needed.
    """

    def __init__(self, broker, market_data, state_store, enable_streaming, stream_manager=None):
        self.stream_manager = stream_manager
        self.broker = broker
        self.market_data = market_data
        self.state_store = state_store
        self.enable_streaming = enable_streaming
        self.stream_timeout_seconds = STREAM_CONFIG["heartbeat_timeout_seconds"]

    # =========================================================
    # LTP
    # =========================================================
    def get_ltp(self, instrument_key):

        # Use stream if enabled and connected
        if self.enable_streaming and self.state_store.is_stream_connected():

            # Ensure subscription
            if self.stream_manager:
                self.stream_manager.subscribe(instrument_key)

                price = self.state_store.get_ltp(instrument_key)
                # log(f"[STREAM] STREAM VALUE:{ self.state_store.get_ltp(instrument_key)}")
                if price is not None:
                    return price

                # Give stream a moment before REST fallback
                last_update = self.state_store.get_ltp_timestamp(instrument_key)

                if last_update:
                    age = time.time() - last_update
                    if age < 2:  # wait 2 seconds
                        return None

                log(f"[DATA] LTP fallback to REST for {instrument_key}")

                return self.market_data.get_ltp(instrument_key)

    # =========================================================
    # POSITION
    # =========================================================

    def get_position_qty(self, instrument_key):

        if self.enable_streaming and self.state_store.is_stream_connected():

            qty = self.state_store.get_position(instrument_key)

            if qty is not None:
                return qty

        # Fallback to REST
        return self.broker.get_position_qty(instrument_key)

    # =========================================================
    # ALL POSITIONS (for RiskEngine later)
    # =========================================================

    def get_all_positions(self):

        if self.enable_streaming and self.state_store.is_stream_connected():

            return self.state_store.get_all_positions()

        return self.broker.get_positions()