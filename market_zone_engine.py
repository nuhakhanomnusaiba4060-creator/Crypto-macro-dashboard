
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Conservative BTC market-zone classifier for spot investors."""

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
    item = metrics.get(key)

    if not isinstance(item, dict):
        return None

    if item.get("status") != "OK":
        return None

    return number(item.get("value"))


def classify(market, macro, advanced):

    # BTC market data
    btc = market.get("technical", {}).get("BTC", {})

    # Backward compatibility
    if not isinstance(btc, dict) or not btc:
        btc = market.get("btc_technical", {})

    if not isinstance(btc, dict):
        btc = {}

    indicators = btc.get("indicators", {})

    if not isinstance(indicators, dict):
        indicators = {}

    price = get(btc, "price_usdt")
    ma20 = get(indicators, "ma20")
    ma50 = get(indicators, "ma50")
    ma200 = get(indicators, "ma200")
    rsi = get(indicators, "rsi14")
    macd = get(indicators, "macd")
    macd_signal = get(indicators, "macd_signal")
    volume_ratio = get(indicators, "volume_ratio_20d")
    support = get(indicators, "support_20d")
    resistance = get(indicators, "resistance_20d")

    fear_greed = get(market, "fear_greed", "value")

    btc_dominance = get(
        market,
        "global_market",
        "btc_dominance_pct"
    )

    # Macro data
    macro_metrics = macro.get("metrics", {})

    if not isinstance(macro_metrics, dict):
        macro_metrics = {}

    vix = metric(macro_metrics, "vix")
    usd_broad = metric(macro_metrics, "usd_broad_index")
    yield_10y = metric(macro_metrics, "yield_10y")

    # On-chain data
    on_chain = advanced.get("on_chain", {})

    if not isinstance(on_chain, dict):
        on_chain = {}

    mvrv = get(on_chain, "mvrv_ratio")

    # Spot market breadth
    activity = advanced.get("spot_market_activity", {})

    if not isinstance(activity, dict):
        activity = {}

    breadth = activity.get("breadth", {})

    if (
        not isinstance(breadth, dict)
        or breadth.get("status") not in (None, "OK")
    ):
        breadth = {}

    breadth_ratio = number(
        breadth.get("advance_decline_ratio")
    )

    # Required data validation
    required = {
        "BTC Price": price,
        "MA20": ma20,
        "MA50": ma50,
        "MA200": ma200,
        "RSI14": rsi,
        "MACD": macd,
        "MACD Signal": macd_signal,
        "Fear & Greed": fear_greed,
        "BTC Dominance": btc_dominance,
        "VIX": vix,
        "US 10Y Yield": yield_10y,
    }

    missing = [
        label
        for label, value in required.items()
        if value is None
    ]

    verified = {
        "btc_price": price,
        "ma20": ma20,
        "ma50": ma50,
        "ma200": ma200,
        "rsi14": rsi,
        "macd": macd,
        "macd_signal": macd_signal,
        "fear_greed": fear_greed,
        "btc_dominance": btc_dominance,
        "vix": vix,
        "usd_broad_index": usd_broad,
        "us_10y_yield": yield_10y,
        "mvrv_ratio": mvrv,
        "market_breadth_ratio": breadth_ratio,
        "volume_ratio_20d": volume_ratio,
        "support_20d": support,
        "resistance_20d": resistance,
    }

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
                "প্রয়োজনীয় verified ইনপুট পাওয়া যায়নি।"
            ],
            "missing_data": missing,
            "verified_inputs": verified,
            "data_limitations": [
                "প্রয়োজনীয় ইনপুট অনুপস্থিত থাকায় "
                "Market Zone নির্ধারণ করা হয়নি।"
            ],
            "method": "Conservative multi-factor rule engine",
        }

    # Technical structure
    bullish_stack = ma20 > ma50 > ma200
    bearish_stack = ma20 < ma50 < ma200

    price_above_20 = price > ma20
    price_above_50 = price > ma50
    price_above_200 = price > ma200

    macd_bullish = macd > macd_signal
    macd_bearish = macd < macd_signal

    oversold = rsi < 30
    overbought = rsi >= 70

    support_broken = (
        support is not None and price < support
    )

    # Market breadth
    breadth_bullish = (
        breadth_ratio is not None
        and breadth_ratio >= 1.20
    )

    breadth_bearish = (
        breadth_ratio is not None
        and breadth_ratio < 0.80
    )

    # Macro risk
    macro_risk = 0

    if vix >= 25:
        macro_risk += 2
    elif vix >= 20:
        macro_risk += 1

    if usd_broad is not None and usd_broad >= 125:
        macro_risk += 1

    if yield_10y >= 5:
        macro_risk += 1

    # Scoring
    bull_score = 0
    bear_score = 0
    accumulation_score = 0
    distribution_score = 0

    if bullish_stack:
        bull_score += 3

    if bearish_stack:
        bear_score += 3

    bull_score += (
        int(price_above_20)
        + int(price_above_50)
        + 2 * int(price_above_200)
    )

    bear_score += (
        int(not price_above_20)
        + int(not price_above_50)
        + 2 * int(not price_above_200)
    )

    if macd_bullish:
        bull_score += 1
    elif macd_bearish:
        bear_score += 1

    if breadth_bullish:
        bull_score += 1
    elif breadth_bearish:
        bear_score += 1

    if fear_greed >= 60:
        bull_score += 1

    if fear_greed <= 25:
        accumulation_score += 2
        bear_score += 1

    if oversold:
        accumulation_score += 1
        bear_score += 1

    if support_broken:
        bear_score += 2

    if overbought:
        distribution_score += 2

    if fear_greed >= 75:
        distribution_score += 2

    if btc_dominance >= 60 and bear_score > bull_score:
        bear_score += 1

    if btc_dominance < 50 and bull_score > bear_score:
        bull_score += 1

    if mvrv is not None:
        if mvrv < 1:
            accumulation_score += 2
        elif mvrv > 3:
            distribution_score += 2

    # Zone classification
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
        and fear_greed <= 20
    ):
        zone = "Capitulation Zone"
        zone_code = "CAPITULATION"
        position = "LATE"
        next_zone = "Accumulation Zone"

        reasons.append(
            "MA structure bearish, গুরুত্বপূর্ণ support ভাঙা, "
            "RSI oversold এবং Extreme Fear একসঙ্গে রয়েছে।"
        )

    elif bearish_stack and bear_score >= 6:
        zone = "Bear Market Zone"
        zone_code = "BEAR_MARKET"
        position = "LATE"
        next_zone = "Capitulation / Accumulation Zone"

        reasons.append(
            "MA20 < MA50 < MA200; "
            "দীর্ঘমেয়াদি bearish structure নিশ্চিত হচ্ছে।"
        )

    elif (
        bullish_stack
        and bull_score >= 7
        and fear_greed < 75
    ):
        zone = "Bull Market Zone"
        zone_code = "BULL_MARKET"

        action = "HOLD"
        risk = "MEDIUM"
        position = "MID"
        next_zone = "Distribution Zone"

        reasons.append(
            "MA20 > MA50 > MA200 এবং "
            "একাধিক bullish confirmation রয়েছে।"
        )

    elif (
        price_above_50
        and price_above_200
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
            "দাম MA50 ও MA200-এর ওপরে; "
            "short-term trend recovery নিশ্চিত করছে।"
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
            "Overbought ও অতিরিক্ত bullish sentiment "
            "distribution risk বাড়াচ্ছে।"
        )

    elif (
        fear_greed <= 25
        and oversold
        and not support_broken
        and accumulation_score >= 3
    ):
        zone = "Accumulation Zone"
        zone_code = "ACCUMULATION"

        action = "DCA"
        risk = "MEDIUM"
        position = "EARLY"
        next_zone = "Early Bull Zone"

        reasons.append(
            "Extreme Fear ও oversold condition আছে; "
            "পর্যবেক্ষিত support এখনো অক্ষত।"
        )

    elif (
        ma20 < ma50
        and price < ma20
        and price < ma50
        and bear_score >= 4
    ):
        zone = "Bear Market Zone"
        zone_code = "BEAR_MARKET"

        action = "WAIT"
        risk = "HIGH"
        position = "MID"
        next_zone = "Capitulation / Accumulation Zone"

        reasons.append(
            "দাম MA20 ও MA50-এর নিচে এবং "
            "short-term trend bearish; "
            "পূর্ণ death-cross structure এখনো নেই।"
        )

    else:
        reasons.append(
            "বর্তমান verified signals কোনো "
            "নির্দিষ্ট Market Zone নিশ্চিত করছে না।"
        )

    # Confidence
    confidence = 40

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

    if zone_code == "INSUFFICIENT_DATA":
        confidence = None
        confidence_label = "NOT_AVAILABLE"

    else:
        confidence = min(confidence, 75)

        if confidence >= 65:
            confidence_label = "MODERATE"
        elif confidence >= 50:
            confidence_label = "LOW"
        else:
            confidence_label = "VERY_LOW"

    # Macro risk override
    if macro_risk >= 3:
        risk = "HIGH"

        if action == "DCA":
            action = "WAIT"

            reasons.append(
                "VIX / US Treasury yield-এ macro stress বেশি; "
                "নতুন DCA আপাতত স্থগিত।"
            )

    if overbought and action == "DCA":
        action = "WAIT"

        reasons.append(
            "RSI overbought; নতুন DCA ঝুঁকিপূর্ণ।"
        )

    if support_broken and action in ("DCA", "HOLD"):
        action = "WAIT"
        risk = "HIGH"

        reasons.append(
            "20-day support ভেঙেছে; "
            "নতুন spot entry আপাতত এড়িয়ে চলুন।"
        )

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
        "verified_inputs": verified,
        "macro_risk_score": macro_risk,
        "data_limitations": [
            "BTC weekly trend আলাদা timeframe data দিয়ে এখনো যাচাই করা হয়নি।",
            "USD Broad Index হলো DXY নয়।",
            "MVRV Ratio পাওয়া গেছে; এটি MVRV Z-Score নয়।",
            "ETF flow, SOPR, Exchange Netflow ও whale data "
            "অনুপলব্ধ থাকলে সেগুলো score-এ ব্যবহার করা হয় না।",
            "পরবর্তী Zone conditional outlook; নিশ্চিত ভবিষ্যদ্বাণী নয়।",
        ],
        "method": "Conservative multi-factor rule engine",
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
        "engine_version": "1.1.0",
        "generated_at": now(),
        "status": (
            "OK"
            if result["zone_code"] != "INSUFFICIENT_DATA"
            else "DATA_WARNING"
        ),
        "market_zone": result,
    }

    temporary = OUTPUT_FILE.with_suffix(".tmp")

    temporary.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )

    temporary.replace(OUTPUT_FILE)

    print("Market Zone Engine completed.")
    print("Zone:", result["current_zone"])
    print("Action:", result["spot_action"])
    print("Missing data:", result["missing_data"])
    print("Output:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
