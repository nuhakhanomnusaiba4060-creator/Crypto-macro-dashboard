
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CRYPTO MARKET ZONE ENGINE
Version: 1.0.0

Inputs:
    data/market_data.json
    data/macro_data.json
    data/advanced_data.json

Output:
    data/market_zone_data.json

Spot investor only.
No futures or margin signals.
Missing data is never fabricated.
"""

import json
import math
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

MARKET_FILE = DATA_DIR / "market_data.json"
MACRO_FILE = DATA_DIR / "macro_data.json"
ADVANCED_FILE = DATA_DIR / "advanced_data.json"
OUTPUT_FILE = DATA_DIR / "market_zone_data.json"


def now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path):
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def number(value):
    if isinstance(value, dict):
        if value.get("status") not in (None, "OK"):
            return None
        value = value.get("value")

    if isinstance(value, bool):
        return None

    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def get(obj, *keys):
    current = obj
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return number(current)


def metric(metrics, key):
    item = metrics.get(key, {})
    if not isinstance(item, dict):
        return None
    if item.get("status") != "OK":
        return None
    return number(item.get("value"))


def classify(market, macro, advanced):

    # -------------------------------------------------
    # INPUT DATA
    # -------------------------------------------------

 # Current market_data.json schema
 btc = market.get("technical", {}).get("BTC", {})

 # Backward compatibility
 if not btc:
    btc = market.get("btc_technical", {})

indicators = btc.get("indicators", {})

    price = get(btc, "price_usdt")
    ma20 = get(indicators, "ma20")
    ma50 = get(indicators, "ma50")
    ma200 = get(indicators, "ma200")
    rsi = get(indicators, "rsi14")
    macd = get(indicators, "macd")
    macd_signal = get(indicators, "macd_signal")
    volume_ratio = get(indicators, "volume_ratio_20d")

    fg = get(market, "fear_greed", "value")
    btc_dom = get(
        market, "global_market", "btc_dominance_pct"
    )

    macro_metrics = macro.get("metrics", {})

    vix = metric(macro_metrics, "vix")
    usd_broad = metric(macro_metrics, "usd_broad_index")
    yield_10y = metric(macro_metrics, "yield_10y")

    advanced_onchain = advanced.get("on_chain", {})
    mvrv = get(advanced_onchain, "mvrv_ratio")

    breadth = (
        advanced.get("spot_market_activity", {})
        .get("breadth", {})
    )

    advancing = number(
        breadth.get("advancing_pairs")
    ) if isinstance(breadth, dict) else None

    declining = number(
        breadth.get("declining_pairs")
    ) if isinstance(breadth, dict) else None

    breadth_ratio = number(
        breadth.get("advance_decline_ratio")
    ) if isinstance(breadth, dict) else None

    # -------------------------------------------------
    # DATA QUALITY GATE
    # -------------------------------------------------

    required = {
        "BTC Price": price,
        "MA20": ma20,
        "MA50": ma50,
        "MA200": ma200,
        "RSI": rsi,
        "MACD": macd,
        "MACD Signal": macd_signal,
        "Fear & Greed": fg,
        "BTC Dominance": btc_dom,
        "VIX": vix,
        "US 10Y Yield": yield_10y,
    }

    missing = [
        name for name, value in required.items()
        if value is None
    ]

    if missing:
        return {
            "current_zone": "INSUFFICIENT DATA",
            "zone_code": "INSUFFICIENT_DATA",
            "confidence": None,
            "confidence_label": "NOT_AVAILABLE",
            "market_position": "UNKNOWN",
            "spot_action": "WAIT",
            "risk_level": "UNKNOWN",
            "next_zone": "UNKNOWN",
            "reason": [
                "Market Zone নির্ধারণের জন্য প্রয়োজনীয় ডেটা অসম্পূর্ণ।"
            ],
            "missing_data": missing,
            "verified_inputs": required,
            "method": "Conservative multi-factor rule engine"
        }

    # -------------------------------------------------
    # TECHNICAL STRUCTURE
    # -------------------------------------------------

    bullish_stack = ma20 > ma50 > ma200
    bearish_stack = ma20 < ma50 < ma200

    price_above_20 = price > ma20
    price_above_50 = price > ma50
    price_above_200 = price > ma200

    macd_bullish = macd > macd_signal
    macd_bearish = macd < macd_signal

    oversold = rsi < 30
    overbought = rsi >= 70

    support = get(indicators, "support_20d")
    support_broken = (
        support is not None and price < support
    )

    # -------------------------------------------------
    # MARKET BREADTH
    # -------------------------------------------------

    breadth_bullish = (
        breadth_ratio is not None
        and breadth_ratio >= 1.20
    )

    breadth_bearish = (
        breadth_ratio is not None
        and breadth_ratio < 0.80
    )

    # -------------------------------------------------
    # MACRO RISK
    # -------------------------------------------------

    macro_risk = 0

    if vix >= 25:
        macro_risk += 2
    elif vix >= 20:
        macro_risk += 1

    if usd_broad >= 125:
        macro_risk += 1

    if yield_10y >= 5:
        macro_risk += 1

    # -------------------------------------------------
    # SCORING
    # -------------------------------------------------

    bull_score = 0
    bear_score = 0
    accumulation_score = 0
    distribution_score = 0

    if bullish_stack:
        bull_score += 3

    if bearish_stack:
        bear_score += 3

    if price_above_20:
        bull_score += 1
    else:
        bear_score += 1

    if price_above_50:
        bull_score += 1
    else:
        bear_score += 1

    if price_above_200:
        bull_score += 2
    else:
        bear_score += 2

    if macd_bullish:
        bull_score += 1
    elif macd_bearish:
        bear_score += 1

    if breadth_bullish:
        bull_score += 1

    if breadth_bearish:
        bear_score += 1

    if fg >= 60:
        bull_score += 1

    if fg <= 25:
        accumulation_score += 2
        bear_score += 1

    if oversold:
        accumulation_score += 1
        bear_score += 1

    if support_broken:
        bear_score += 2

    if overbought:
        distribution_score += 2

    if fg >= 75:
        distribution_score += 2

    if btc_dom >= 60 and bear_score > bull_score:
        bear_score += 1

    if btc_dom < 50 and bull_score > bear_score:
        bull_score += 1

    if mvrv is not None:
        if mvrv < 1:
            accumulation_score += 2
        elif mvrv > 3:
            distribution_score += 2

    # -------------------------------------------------
    # ZONE CLASSIFICATION
    # -------------------------------------------------

    zone = "INSUFFICIENT DATA"
    zone_code = "INSUFFICIENT_DATA"
    action = "WAIT"
    risk = "HIGH"
    position = "UNKNOWN"
    next_zone = "UNKNOWN"
    reasons = []

    if (
        bearish_stack
        and support_broken
        and oversold
        and fg <= 20
    ):
        zone = "Capitulation Zone"
        zone_code = "CAPITULATION"
        action = "WAIT"
        risk = "HIGH"
        position = "LATE"
        next_zone = "Accumulation Zone"
        reasons.append(
            "Bearish MA structure, support breakdown, "
            "oversold RSI এবং Extreme Fear একসঙ্গে রয়েছে।"
        )

    elif (
        bearish_stack
        and bear_score >= 6
    ):
        zone = "Bear Market Zone"
        zone_code = "BEAR_MARKET"
        action = "WAIT"
        risk = "HIGH"
        position = "LATE"
        next_zone = "Capitulation / Accumulation"
        reasons.append(
            "দাম ও MA structure দীর্ঘমেয়াদি bearish।"
        )

    elif (
        bullish_stack
        and bull_score >= 7
        and fg < 75
        and macro_risk <= 2
    ):
        zone = "Bull Market Zone"
        zone_code = "BULL_MARKET"
        action = "HOLD"
        risk = "MEDIUM"
        position = "MID"
        next_zone = "Distribution Zone"
        reasons.append(
            "BTC MA20 > MA50 > MA200 এবং bullish confirmation রয়েছে।"
        )

    elif (
        price > ma50
        and price > ma200
        and ma20 > ma50
        and bull_score >= 5
    ):
        zone = "Early Bull Zone"
        zone_code = "EARLY_BULL"
        action = "DCA"
        risk = "MEDIUM"
        position = "EARLY"
        next_zone = "Bull Market Zone"
        reasons.append(
            "দাম MA50 ও MA200-এর ওপরে এবং short-term recovery শক্তিশালী।"
        )

    elif (
        distribution_score >= 4
        and bull_score >= 3
    ):
        zone = "Distribution Zone"
        zone_code = "DISTRIBUTION"
        action = "SELL"
        risk = "HIGH"
        position = "LATE"
        next_zone = "Bear Market Zone"
        reasons.append(
            "উচ্চ sentiment / overbought condition এবং distribution risk রয়েছে।"
        )

    elif (
        bear_score >= 4
        and accumulation_score >= 3
        and fg <= 30
        and not support_broken
    ):
        zone = "Accumulation Zone"
        zone_code = "ACCUMULATION"
        action = "DCA"
        risk = "MEDIUM"
        position = "EARLY"
        next_zone = "Early Bull Zone"
        reasons.append(
            "Extreme fear, দুর্বল trend এবং support এখনো অক্ষত।"
        )

    else:
        reasons.append(
            "বর্তমান ডেটা কোনো নির্দিষ্ট Market Zone নিশ্চিত করছে না।"
        )

    # -------------------------------------------------
    # CONFIDENCE
    # -------------------------------------------------

    confidence = 45

    if bullish_stack or bearish_stack:
        confidence += 15

    if macd_bullish or macd_bearish:
        confidence += 5

    if breadth_ratio is not None:
        confidence += 5

    if mvrv is not None:
        confidence += 5

    if volume_ratio is not None:
        confidence += 5

    if zone == "INSUFFICIENT DATA":
        confidence = None
        confidence_label = "NOT_AVAILABLE"
    else:
        confidence = min(confidence, 80)

        if confidence >= 70:
            confidence_label = "MODERATE"
        elif confidence >= 55:
            confidence_label = "LOW"
        else:
            confidence_label = "VERY_LOW"

    # -------------------------------------------------
    # POSITION AND RISK OVERRIDES
    # -------------------------------------------------

    if macro_risk >= 3:
        risk = "HIGH"
        if action == "DCA":
            action = "WAIT"
            reasons.append(
                "Macro risk বেশি; নতুন DCA আপাতত স্থগিত।"
            )

    if overbought and action == "DCA":
        action = "WAIT"
        reasons.append(
            "RSI overbought; নতুন DCA ঝুঁকিপূর্ণ।"
        )

    # -------------------------------------------------
    # RETURN
    # -------------------------------------------------

    return {
        "current_zone": zone,
        "zone_code": zone_code,
        "confidence": confidence,
        "confidence_label": confidence_label,
        "market_position": position,
        "spot_action": action,
        "risk_level": risk,
        "next_zone": next_zone,
        "reason": reasons,
        "missing_data": [],
        "verified_inputs": {
            "btc_price": price,
            "ma20": ma20,
            "ma50": ma50,
            "ma200": ma200,
            "rsi14": rsi,
            "macd": macd,
            "macd_signal": macd_signal,
            "fear_greed": fg,
            "btc_dominance": btc_dom,
            "vix": vix,
            "usd_broad_index": usd_broad,
            "us_10y_yield": yield_10y,
            "mvrv_ratio": mvrv,
            "market_breadth_ratio": breadth_ratio,
            "volume_ratio_20d": volume_ratio
        },
        "data_limitations": [
            "Weekly BTC trend এখনো আলাদা করে যাচাই করা হয়নি।",
            "USD Broad Index হলো DXY নয়।",
            "MVRV Ratio পাওয়া না গেলে সেটি বাদ থাকে।",
            "ETF flow, SOPR ও Exchange Netflow অনুপলব্ধ হলে অনুমান করা হয় না।",
            "পরবর্তী Zone সম্ভাব্য পর্যায়, নিশ্চিত ভবিষ্যদ্বাণী নয়।"
        ],
        "method": "Conservative multi-factor rule engine"
    }


def main():

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    market = read_json(MARKET_FILE)
    macro = read_json(MACRO_FILE)
    advanced = read_json(ADVANCED_FILE)

    result = classify(market, macro, advanced)

    output = {
        "schema_version": 1,
        "engine": "Crypto Market Zone Engine",
        "engine_version": "1.0.0",
        "generated_at": now(),
        "status": (
            "OK"
            if result["zone_code"] != "INSUFFICIENT_DATA"
            else "DATA_WARNING"
        ),
        "market_zone": result
    }

    temporary = OUTPUT_FILE.with_suffix(".tmp")

    temporary.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
            allow_nan=False
        ) + "\n",
        encoding="utf-8"
    )

    temporary.replace(OUTPUT_FILE)

    print("Market Zone Engine completed.")
    print("Zone:", result["current_zone"])
    print("Action:", result["spot_action"])
    print("Output:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
