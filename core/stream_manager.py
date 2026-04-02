# core/stream_manager.py

import threading
import time
from core.utils import log
import upstox_client

class StreamManager:

    def __init__(self, state_store, access_token):

        self.state_store = state_store
        self.access_token = access_token

        self._running = False

        self._market_thread = None
        self._order_thread = None

        self._market_streamer = None
        self._subscribed = set()
        self._subscription_lock = threading.Lock()
        self._market_connected = False

    # =========================================================
    # START STREAMS
    # =========================================================

    def start(self):

        if self._running:
            return

        log("[STREAM] Starting Stream Manager")

        self._running = True
        self.state_store.set_stream_status(True)

        self._market_thread = threading.Thread(
            target=self._run_market_stream,
            daemon=True
        )

        self._order_thread = threading.Thread(
            target=self._run_order_stream,
            daemon=True
        )

        self._market_thread.start()
        self._order_thread.start()

    # =========================================================
    # STOP STREAMS
    # =========================================================

    def stop(self):

        log("[STREAM] Stopping Stream Manager")

        self._running = False
        self.state_store.set_stream_status(False)

    # =========================================================
    # MARKET STREAM THREAD
    # =========================================================

    # =========================================================
    # MARKET STREAM THREAD (SDK Based)
    # =========================================================

    def _run_market_stream(self):

        log("[STREAM] Market Stream Thread Started")

        try:

            configuration = upstox_client.Configuration()
            configuration.access_token = self.access_token

            api_client = upstox_client.ApiClient(configuration)

            # Start empty subscription — we will subscribe dynamically
            self._market_streamer = upstox_client.MarketDataStreamerV3(api_client)
            streamer = self._market_streamer

            # ---------------------------------------------
            # EVENTS
            # ---------------------------------------------

            def on_open():
                log("[STREAM] Market Stream Connected")
                self.state_store.set_stream_status(True)
                self._market_connected = True

            def on_message(message):

                try:
                    self.state_store.update_heartbeat()
                    feeds = message.get("feeds", {})

                    for instrument_key, feed_data in feeds.items():

                        ltpc = feed_data.get("ltpc")

                        if not ltpc:
                            continue

                        ltp = ltpc.get("ltp")

                        if ltp is not None:
                            self.state_store.update_ltp(instrument_key, float(ltp))

                except Exception as e:
                    log(f"[STREAM][MARKET] Message Parse Error: {e}")

            def on_error(err):
                log(f"[STREAM][MARKET] Error: {err}")

            def on_close():
                log("[STREAM] Market Stream Closed")
                self.state_store.set_stream_status(False)
                self._market_connected = False

            streamer.on("open", on_open)
            streamer.on("message", on_message)
            streamer.on("error", on_error)
            streamer.on("close", on_close)

            # Enable auto reconnect (enterprise stability)
            streamer.auto_reconnect(True, 5, 10)

            streamer.connect()

            # Keep thread alive
            while self._running:
                time.sleep(1)

            streamer.disconnect()

        except Exception as e:
            log(f"[STREAM][MARKET] Fatal Error: {e}")

        log("[STREAM] Market Stream Thread Stopped")

    # =========================================================
    # SUBSCRIBE TO MARKET DATA
    # =========================================================

    def subscribe(self, instrument_key, mode="ltpc"):

        if not self._market_streamer:
            return

        if not self._market_connected:
            # Do not attempt subscription before connection
            return

        with self._subscription_lock:

            if instrument_key in self._subscribed:
                return

            try:
                self._market_streamer.subscribe([instrument_key], mode)
                self._subscribed.add(instrument_key)
                log(f"[STREAM] Subscribed: {instrument_key}")
            except Exception as e:
                log(f"[STREAM] Subscription Error: {e}")


    # =========================================================
    # ORDER / PORTFOLIO STREAM THREAD (SDK Based)
    # =========================================================

    def _run_order_stream(self):

        log("[STREAM] Order Stream Thread Started")

        try:
            import upstox_client

            configuration = upstox_client.Configuration()
            configuration.access_token = self.access_token

            api_client = upstox_client.ApiClient(configuration)

            streamer = upstox_client.PortfolioDataStreamer(
                api_client,
                order_update=True,
                position_update=True,
                holding_update=False,
                gtt_update=True
            )

            # ---------------------------------------------
            # EVENTS
            # ---------------------------------------------

            def on_open():
                log("[STREAM] Portfolio Stream Connected")

            import json

            def on_message(message):

                try:
                    # -------------------------------------------------
                    # Decode JSON if message arrives as string
                    # -------------------------------------------------
                    if isinstance(message, str):
                        message = json.loads(message)

                    log(f"[PORTFOLIO RAW] {message}")

                    # -------------------------------------------------
                    # Update stream heartbeat
                    # -------------------------------------------------
                    self.state_store.update_heartbeat()

                    update_type = message.get("update_type")

                    # -------------------------------------------------
                    # ORDER UPDATE
                    # -------------------------------------------------
                    if update_type == "order":

                        order_id = message.get("order_id")

                        if order_id:
                            self.state_store.update_order(order_id, message)
                            self.state_store.mark_order_changed()

                    # -------------------------------------------------
                    # POSITION UPDATE
                    # -------------------------------------------------
                    elif update_type == "position":

                        instrument = message.get("instrument_token")
                        qty = int(message.get("quantity", 0))

                        if instrument:
                            self.state_store.update_position(instrument, qty)
                            self.state_store.mark_position_changed()

                    # -------------------------------------------------
                    # GTT UPDATE
                    # -------------------------------------------------
                    elif update_type == "gtt":

                        gtt_id = message.get("gtt_order_id")

                        if gtt_id:
                            self.state_store.update_order(gtt_id, message)

                except Exception as e:
                    log(f"[STREAM][PORTFOLIO] Message Parse Error: {e}")


            def on_error(err):
                log(f"[STREAM][PORTFOLIO] Error: {err}")

            def on_close():
                log("[STREAM] Portfolio Stream Closed")

            streamer.on("open", on_open)
            streamer.on("message", on_message)
            streamer.on("error", on_error)
            streamer.on("close", on_close)

            streamer.auto_reconnect(True, 5, 10)
            streamer.connect()

            while self._running:
                time.sleep(1)

            streamer.disconnect()

        except Exception as e:
            log(f"[STREAM][PORTFOLIO] Fatal Error: {e}")

        log("[STREAM] Order Stream Thread Stopped")