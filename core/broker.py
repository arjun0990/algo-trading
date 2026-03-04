import requests
import sys
import time

from config import GLOBAL_CONFIG
from core.utils import log


class BrokerClient:

    BASE_URL = "https://api.upstox.com/v3"

    def __init__(self, access_token):

        self.headers = {
            "Content-Type": 'application/json',
            "accept": "application/json",
            "Authorization": f"Bearer {access_token}"
        }

        self.product_type = GLOBAL_CONFIG["product_type"]
        self.validity = GLOBAL_CONFIG["validity"]

    # =========================================================
    # SAFE REQUEST
    # =========================================================
    def safe_request(self, method, url, **kwargs):

        max_retries = 4
        base_delay = 0.5  # initial backoff delay (seconds)

        for attempt in range(max_retries):

            try:
                r = requests.request(
                    method,
                    url,
                    headers=self.headers,
                    timeout=10,
                    **kwargs
                )

                # -------------------------------------------------
                # 429 RATE LIMIT HANDLING
                # -------------------------------------------------
                if r.status_code == 429:
                    wait_time = base_delay * (2 ** attempt)

                    log(
                        f"[BROKER] 429 Rate Limit Hit | "
                        f"Retrying in {wait_time:.2f}s | Attempt {attempt + 1}/{max_retries}"
                    )

                    time.sleep(wait_time)
                    continue

                # -------------------------------------------------
                # NON-200 RESPONSE
                # -------------------------------------------------
                if r.status_code != 200:
                    log(
                        f"[BROKER] HTTP Error {r.status_code} | URL: {url}"
                    )
                    return {"status": "error", "code": r.status_code}

                # -------------------------------------------------
                # SAFE JSON PARSE
                # -------------------------------------------------
                try:
                    data = r.json()
                except Exception as e:
                    log(f"[BROKER] JSON Parse Failed: {str(e)}")
                    return {"status": "error", "code": "json_error"}

                return data

            except Exception as e:

                wait_time = base_delay * (2 ** attempt)

                log(
                    f"[BROKER] Request Exception: {str(e)} | "
                    f"Retrying in {wait_time:.2f}s | Attempt {attempt + 1}/{max_retries}"
                )

                time.sleep(wait_time)

        # -------------------------------------------------
        # MAX RETRIES EXCEEDED
        # -------------------------------------------------
        log("[BROKER] Max Retries Exceeded")
        return {"status": "error", "code": "max_retries_exceeded"}

    # def safe_request(self, method, url, **kwargs):
    #
    #     try:
    #         r = requests.request(method, url, headers=self.headers, timeout=10, **kwargs)
    #
    #         # print("STATUS CODE:", r.status_code)
    #         # print("RAW RESPONSE:", r.text)
    #
    #         if r.status_code != 200:
    #             return {"status": "error", "code": r.status_code}
    #
    #         # 🔥 IMPORTANT: parse only once
    #         try:
    #             data = r.json()
    #         except Exception as e:
    #             print("JSON PARSE FAILED:", str(e))
    #             return {"status": "error", "code": "json_error"}
    #
    #         return data
    #
    #     except Exception as e:
    #         print("REQUEST FAILED:", str(e))
    #         return {"status": "error", "code": "request_exception"}
    # =========================================================
    # ORDER FUNCTIONS
    # =========================================================
    def place_order(self, payload):

        # Always enforce config alignment
        payload["product"] = self.product_type
        payload["validity"] = self.validity

        # Ensure instrument_token is string
        if not isinstance(payload.get("instrument_token"), str):
            payload["instrument_token"] = str(payload["instrument_token"])

        print("DEBUG ORDER PAYLOAD:", payload)

        return self.safe_request(
            "POST",
            f"{self.BASE_URL}/order/place",
            json=payload
        )

    def cancel_order(self, order_id):

        if not order_id:
            return None

        return self.safe_request(
            "DELETE",
            f"{self.BASE_URL}/order/cancel",
            params={"order_id": order_id}
        )

    def get_order_book(self):

        response = self.safe_request(
            "GET",
            f"https://api.upstox.com/v2/order/retrieve-all"
        )

        if not response:
            return []

        if response.get("status") != "success":
            return []

        return response.get("data", [])

    def get_order_status(self, order_id):

        if not order_id:
            return None

        data = self.safe_request(
            "GET",
            f"{self.BASE_URL}/order/details",
            params={"order_id": order_id}
        )

        if data and data.get("status") == "success":
            return data["data"].get("status")

        return None

    # =========================================================
    # POSITION FUNCTIONS
    # =========================================================
    def get_positions(self):

        data = self.safe_request(
            "GET",
            f"https://api.upstox.com/v2/portfolio/short-term-positions"
        )

        if data and data.get("status") == "success":
            return data["data"]

        return []

    def get_position_qty(self, instrument_key):

        positions = self.get_positions()

        for p in positions:
            if p.get("instrument_token") == instrument_key:
                return int(p.get("quantity", 0))

        return 0

    # =========================================================
    # CANCEL ALL
    # =========================================================
    def cancel_all_pending_orders(self):

        url = "https://api.upstox.com/v2/order/multi/cancel"

        data = self.safe_request(
            "DELETE",
            url
        )

        if not data:
            print("Cancel pending orders: No response")
            return False

            # If no pending orders exist, API may return 400
        if data.get("status") == "error" and data.get("code") == 400:
            print("No pending regular orders to cancel.")
            return True

        if data.get("status") != "success":
            print("Cancel pending orders failed:", data)
            return False

        print("All pending regular orders cancelled successfully")
        return True

    # =========================================================
    # EXIT ALL POSITIONS
    # =========================================================
    def exit_all_positions(self):

        url = "https://api.upstox.com/v2/order/positions/exit"

        data = self.safe_request(
            "POST",
            url,
            json={}
        )

        if not data:
            print("Position exit failed - No response")
            return False

            # 👇 This is the important change
        if data.get("status") == "error" and data.get("code") == 400:
            print("No open positions to exit.")
            return True

        if data.get("status") != "success":
            print("Position exit failed:", data)
            return False

        print("All positions exited successfully")
        return True

    # =========================================================
    # SAFE FLATTEN
    # =========================================================
    def flatten_and_verify(self, max_wait_seconds=5):

        try:
            self.cancel_all_pending_orders()
            self.exit_all_positions()
        except:
            return False

        checks = 0
        max_checks = int(max_wait_seconds / 0.5)

        while checks < max_checks:

            positions = self.get_positions()

            active = [
                p for p in positions
                if int(p.get("quantity", 0)) != 0
            ]

            if not active:
                log("All positions flattened successfully")
                return True

            time.sleep(0.5)
            checks += 1

        log("CRITICAL: Unable to flatten all positions")
        return False

    def place_gtt_order(self, payload):
        url = f"{self.BASE_URL}/order/gtt/place"

        data = self.safe_request(
            "POST",
            url,
            json=payload
        )

        if data.get("status") != "success":
            log(f"[BROKER] GTT Placement Failed | Response: {data}")
            return None

        gtt_ids = data.get("data", {}).get("gtt_order_ids", [])
        if not gtt_ids:
            print("❌ No GTT ID returned.")
            return None

        print("✅ GTT Placed:", gtt_ids[0])
        return gtt_ids[0]

    def modify_gtt_order(self, payload):
        url = f"{self.BASE_URL}/order/gtt/modify"

        data = self.safe_request(
            "PUT",
            url,
            json=payload
        )

        if data.get("status") != "success":
            print("❌ GTT Modify Failed:", data)
            return False

        print("✅ GTT Modified")
        return True

    def cancel_gtt_order(self, gtt_order_id):
        url = f"{self.BASE_URL}/order/gtt/cancel"

        payload = {
            "gtt_order_id": gtt_order_id
        }

        data = self.safe_request(
            "DELETE",
            url,
            json=payload
        )
        print("Cancel GTT Response:", data)
        if data.get("status") != "success":
            print("❌ GTT Cancel Failed:", data)
            return False

        print("✅ GTT Cancelled:", gtt_order_id)
        return True

    def get_all_gtt_orders(self):

        data = self.safe_request(
            "GET",
            f"{self.BASE_URL}/order/gtt"
        )

        if data and data.get("status") == "success":
            return data.get("data", [])

        return []