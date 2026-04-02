import math
from core.utils import log
from config import OPTION_INTEL_CONFIG, ACTIVE_INDEX, INDEX_CONFIG


class OptionIntelligenceEngine:

    def __init__(self):
        self.config = OPTION_INTEL_CONFIG
        self.prev_chain = {}

    # =========================================================
    def compute(self, market_data, instruments):

        index_symbol = INDEX_CONFIG[ACTIVE_INDEX]["index_symbol"]
        index_ltp = market_data.get_ltp(index_symbol)

        if not index_ltp:
            return None

        strike_step = INDEX_CONFIG[ACTIVE_INDEX]["strike_step"]
        atm = round(index_ltp / strike_step) * strike_step

        strikes = self._get_strikes(atm, strike_step)

        chain = self._build_chain(strikes, instruments, market_data)
        print(f"[DEBUG] Chain size: {len(chain)}")
        if not chain:
            return None

        features = self._extract_features(chain, index_ltp)

        structure = self._analyze_structure(chain)

        gamma = self._compute_gamma(chain, index_ltp)

        regime = self._detect_regime(features, gamma)

        signal = self._generate_signal(features, structure, gamma, regime)

        self.prev_chain = chain

        return {
            "ltp": index_ltp,
            "atm": atm,
            "features": features,
            "structure": structure,
            "gamma": gamma,
            "regime": regime,
            "signal": signal
        }

    # =========================================================
    def _get_strikes(self, atm, step):
        rng = self.config["strike_range"]
        return list(range(atm - rng, atm + rng + step, step))

    # =========================================================
    def _build_chain(self, strikes, instruments, market_data):

        chain = {}
        expiry = instruments.get_nearest_expiry()

        segment = INDEX_CONFIG[ACTIVE_INDEX]['segment']

        oi_values = []

        # -------------------------------
        # FIRST PASS → collect OI
        # -------------------------------
        for strike in strikes:

            ce_token, _ = instruments.find_option(expiry, strike, "CE")
            pe_token, _ = instruments.find_option(expiry, strike, "PE")

            if not ce_token or not pe_token:
                continue

            ce_key = f"{segment}|{ce_token}"
            pe_key = f"{segment}|{pe_token}"

            if hasattr(market_data, "get_oi"):
                ce_oi = market_data.get_oi(ce_key)
                pe_oi = market_data.get_oi(pe_key)

                if ce_oi and pe_oi:
                    oi_values.append(ce_oi + pe_oi)

        if not oi_values:
            return {}

        avg_oi = sum(oi_values) / len(oi_values)
        dynamic_threshold = avg_oi * 0.6

        # -------------------------------
        # SECOND PASS → build filtered chain
        # -------------------------------
        for strike in strikes:

            ce_token, _ = instruments.find_option(expiry, strike, "CE")
            pe_token, _ = instruments.find_option(expiry, strike, "PE")

            if not ce_token or not pe_token:
                continue

            ce_key = f"{segment}|{ce_token}"
            pe_key = f"{segment}|{pe_token}"

            # LTP
            ce_ltp = market_data.get_ltp(ce_key)
            pe_ltp = market_data.get_ltp(pe_key)
            print(f"[DEBUG] LTP check | Strike: {strike} | CE: {ce_ltp} | PE: {pe_ltp}")
            if ce_ltp is None or pe_ltp is None:
                continue

            # OI
            if not hasattr(market_data, "get_oi"):
                continue

            ce_oi = market_data.get_oi(ce_key)
            pe_oi = market_data.get_oi(pe_key)
            print(f"[DEBUG] OI check | Strike: {strike} | CE_OI: {ce_oi} | PE_OI: {pe_oi}")
            if ce_oi is None or pe_oi is None:
                ce_oi=0
                pe_oi=0

            # VOLUME
            if not hasattr(market_data, "get_volume"):
                continue

            ce_vol = market_data.get_volume(ce_key)
            pe_vol = market_data.get_volume(pe_key)
            print(f"[DEBUG] VOL check | Strike: {strike} | CE_VOL: {ce_vol} | PE_VOL: {pe_vol}")
            if ce_vol is None or pe_vol is None:
                ce_vol=0
                pe_vol=0

            # -------------------------------
            # LIQUIDITY FILTERS
            # -------------------------------
            # if ce_oi < self.config["min_oi"] or pe_oi < self.config["min_oi"]:
            #     continue
            #
            # if ce_vol < self.config["min_volume"] or pe_vol < self.config["min_volume"]:
            #     continue

            # -------------------------------
            # DOMINANCE FILTER (NEW 🔥)
            # -------------------------------
            # if (ce_oi + pe_oi) < dynamic_threshold:
            #     continue
            log(f"[DEBUG] Strike {strike} | CE_OI: {ce_oi} | PE_OI: {pe_oi} | CE_VOL: {ce_vol}")
            # -------------------------------
            # BUILD CHAIN
            # -------------------------------
            chain[strike] = {
                "ce": {"ltp": ce_ltp, "oi": ce_oi, "vol": ce_vol},
                "pe": {"ltp": pe_ltp, "oi": pe_oi, "vol": pe_vol}
            }
        return chain

    # =========================================================
    def _extract_features(self, chain, index_ltp):

        total_delta = 0
        oi_shift = 0
        volume_spike = 0
        oi_acceleration = 0

        for strike, data in chain.items():

            ce = data["ce"]
            pe = data["pe"]

            dist = abs(strike - index_ltp)
            weight = 1 / (1 + dist)

            total_delta += weight * (pe["ltp"] - ce["ltp"])

            if strike in self.prev_chain:

                prev = self.prev_chain[strike]

                # OI SHIFT
                ce_oi_change = ce["oi"] - prev["ce"]["oi"]
                pe_oi_change = pe["oi"] - prev["pe"]["oi"]

                oi_shift += (pe_oi_change - ce_oi_change)

                # OI ACCELERATION 🔥
                oi_acceleration += abs(ce_oi_change) + abs(pe_oi_change)

                # VOLUME SPIKE
                prev_ce_vol = prev["ce"]["vol"]
                prev_pe_vol = prev["pe"]["vol"]

                if prev_ce_vol > 0 and ce["vol"] / prev_ce_vol > self.config["volume_spike_threshold"]:
                    volume_spike += 1

                if prev_pe_vol > 0 and pe["vol"] / prev_pe_vol > self.config["volume_spike_threshold"]:
                    volume_spike += 1

        return {
            "delta_flow": total_delta,
            "oi_shift": oi_shift,
            "volume_spike": volume_spike,
            "oi_acceleration": oi_acceleration
        }

    # =========================================================
    def _analyze_structure(self, chain):

        max_call_oi = 0
        max_put_oi = 0

        resistance = None
        support = None

        for strike, data in chain.items():

            if data["ce"]["oi"] > max_call_oi:
                max_call_oi = data["ce"]["oi"]
                resistance = strike

            if data["pe"]["oi"] > max_put_oi:
                max_put_oi = data["pe"]["oi"]
                support = strike

        return {
            "support": support,
            "resistance": resistance
        }

    # =========================================================
    def _compute_gamma(self, chain, index_ltp):

        gex = 0

        for strike, data in chain.items():

            distance = abs(strike - index_ltp)

            gamma = 1 / (1 + distance)

            gex += gamma * (data["pe"]["oi"] - data["ce"]["oi"])

        gamma_flip = "POSITIVE" if gex > 0 else "NEGATIVE"

        return {
            "gex": gex,
            "gamma_flip": gamma_flip
        }

    # =========================================================
    def _detect_regime(self, features, gamma):

        if abs(gamma["gex"]) < 100:
            return "RANGE"

        if gamma["gamma_flip"] == "POSITIVE":
            return "TREND_UP"

        return "TREND_DOWN"

    # =========================================================
    def _generate_signal(self, f, s, g, regime):

        score = 0
        w = self.config

        score += w["delta_weight"] * (1 if f["delta_flow"] > 0 else -1) * 100
        score += w["oi_weight"] * (1 if f["oi_shift"] > 0 else -1) * 100
        score += w["gamma_weight"] * (1 if g["gamma_flip"] == "POSITIVE" else -1) * 100
        score += w["volume_weight"] * f["volume_spike"] * 10

        # 🔥 NEW: OI ACCELERATION BOOST
        score += 0.05 * f["oi_acceleration"]

        # structure bias
        if s["support"] and s["resistance"]:
            if s["support"] > s["resistance"]:
                score += 10

        strength = abs(score)

        bias = "NEUTRAL"
        threshold = self.config["strength_threshold"]

        if score > threshold:
            bias = "BULLISH"
        elif score < -threshold:
            bias = "BEARISH"

        breakout = strength > self.config["breakout_score"]

        return {
            "bias": bias,
            "strength": strength,
            "breakout": breakout,
            "regime": regime
        }