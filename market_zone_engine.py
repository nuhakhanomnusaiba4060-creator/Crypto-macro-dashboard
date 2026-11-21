
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CRYPTO MARKET ZONE ENGINE
Version: 2.0.0

Purpose:
- Identify broad crypto market phase and zone.
- Validate snapshot freshness before classification.
- Evaluate BTC technical structure, macro risk and spot breadth.
- Avoid false accumulation/distribution signals.
- Align with Final Decision Engine conservatively.
- Never generate coin-specific BUY/SELL advice.

Inputs:
    data/market_data.json
    data/macro_data.json
    data/advanced_data.json
    data/decision_data.json

Output:
    data/market_zone_data.json

Standard-library only.
"""

import json
import math
import os
import tempfile

from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional


# ============================================================
# CONFIGURATION
# ============================================================

VERSION = "2.0.0"

DATA_DIR = Path("data")

MARKET_FILE = DATA_DIR / "market_data.json"
MACRO_FILE = DATA_DIR / "macro_data.json"
ADVANCED_FILE = DATA_DIR / "advanced_data.json"
DECISION_FILE = DATA_DIR / "decision_data.json"

OUTPUT_FILE = DATA_DIR / "market_zone_data.json"

MARKET_MAX_AGE_HOURS = 36
MACRO_MAX_AGE_HOURS = 72
ADVANCED_MAX_AGE_HOURS = 24
DECISION_MAX_AGE_HOURS = 36

FUTURE_TIME_TOLERANCE_MINUTES = 5


# ============================================================
# TIME UTILITIES
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def parse_time(value):
    if not value:
        return None

    try:
        if isinstance(value, (int, float)):
            if not math.isfinite(float(value)):
                return None

            # Unix timestamp
            return datetime.fromtimestamp(
                float(value),
                tz=timezone.utc
            )

        if not isinstance(value, str):
            return None

        text = value.strip()

        if not text:
            return None

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        result = datetime.fromisoformat(text)

        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)

        return result.astimezone(timezone.utc)

    except (ValueError, TypeError, OverflowError, OSError):
        return None


def age_hours(value):
    parsed = parse_time(value)

    if parsed is None:
        return None

    age = (utc_now() - parsed).total_seconds() / 3600

    if age < -(FUTURE_TIME_TOLERANCE_MINUTES / 60):
        return None

    return max(0.0, age)


def snapshot_time(data):
    if not isinstance(data, dict):
        return None

    for key in (
        "generated_at",
        "fetched_at",
        "updated_at",
        "timestamp",
        "last_updated"
    ):
        if data.get(key):
            return data.get(key)

    return None


def snapshot_status(data, max_age_hours):
    if not isinstance(data, dict) or not data:
        return {
            "status": "MISSING",
            "age_hours": None,
            "timestamp": None
        }

    timestamp = snapshot_time(data)
    age = age_hours(timestamp)

    if timestamp is None or age is None:
        return {
            "status": "INVALID_TIMESTAMP",
            "age_hours": None,
            "timestamp": timestamp
        }

    if age > max_age_hours:
        return {
            "status": "STALE",
            "age_hours": round(age, 2),
            "timestamp": timestamp
        }

    return {
        "status": "FRESH",
        "age_hours": round(age, 2),
        "timestamp": timestamp
    }


# ============================================================
# JSON UTILITIES
# ============================================================

def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return {}

        return data

    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def atomic_write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False
        ) as temp_file:

            json.dump(
                data,
                temp_file,
                ensure_ascii=False,
                indent=2,
                allow_nan=False
            )

            temp_file.write("\n")
            temp_path = temp_file.name

        os.replace(temp_path, path)

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# ============================================================
# SAFE DATA ACCESS
# ============================================================

def safe_dict(value):
    return value if isinstance(value, dict) else {}


def safe_list(value):
    return value if isinstance(value, list) else []


def get_path(data, *keys):
    current = data

    for key in keys:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

    return current


def first_value(*values):
    for value in values:
        if value is not None:
            return value

    return None


def number(value):
    if isinstance(value, dict):
        value = value.get("value")

    if value is None or isinstance(value, bool):
        return None

    try:
        result = float(value)

        if not math.isfinite(result):
            return None

        return result

    except (ValueError, TypeError, OverflowError):
        return None


def metric(data, *paths):
    for path in paths:
        value = get_path(data, *path)

        if isinstance(value, dict):
            status = str(value.get("status", "")).upper()

            if status in (
                "UNAVAILABLE",
                "ERROR",
                "STALE",
                "INVALID",
                "MISSING"
            ):
                continue

            value = value.get("value")

        result = number(value)

        if result is not None:
            return result

    return None


def metric_object(data, *paths):
    for path in paths:
        value = get_path(data, *path)

        if isinstance(value, dict):
            return value

    return {}


def valid_range(value, minimum, maximum):
    return (
        value is not None
        and minimum <= value <= maximum
    )


# ============================================================
# INPUT EXTRACTION
# ============================================================

def extract_btc(market):
    technical = safe_dict(market.get("technical"))
    btc = safe_dict(technical.get("BTC"))

    if not btc:
        btc = safe_dict(market.get("btc_technical"))

    if not btc:
        btc = safe_dict(market.get("BTC"))

    price = metric(
        {"btc": btc},
        ("btc", "price"),
        ("btc", "current_price"),
        ("btc", "close")
    )

    ma20 = metric(
        {"btc": btc},
        ("btc", "sma20"),
        ("btc", "ma20"),
        ("btc", "MA20")
    )

    ma50 = metric(
        {"btc": btc},
        ("btc", "sma50"),
        ("btc", "ma50"),
        ("btc", "MA50")
    )

    ma200 = metric(
        {"btc": btc},
        ("btc", "sma200"),
        ("btc", "ma200"),
        ("btc", "MA200")
    )

    rsi = metric(
        {"btc": btc},
        ("btc", "rsi14"),
        ("btc", "rsi"),
        ("btc", "RSI")
    )

    macd = metric(
        {"btc": btc},
        ("btc", "macd"),
        ("btc", "MACD")
    )

    macd_signal = metric(
        {"btc": btc},
        ("btc", "macd_signal"),
        ("btc", "signal"),
        ("btc", "MACD_signal")
    )

    volume_ratio = metric(
        {"btc": btc},
        ("btc", "volume_ratio"),
        ("btc", "volume_sma20_ratio"),
        ("btc", "relative_volume")
    )

    support = metric(
        {"btc": btc},
        ("btc", "support_20d"),
        ("btc", "support")
    )

    resistance = metric(
        {"btc": btc},
        ("btc", "resistance_20d"),
        ("btc", "resistance")
    )

    return {
        "price": price,
        "ma20": ma20,
        "ma50": ma50,
        "ma200": ma200,
        "rsi": rsi,
        "macd": macd,
        "macd_signal": macd_signal,
        "volume_ratio": volume_ratio,
        "support": support,
        "resistance": resistance
    }


def extract_fear_greed(market):
    value = metric(
        market,
        ("fear_greed", "value"),
        ("fear_greed", "current_value"),
        ("fear_greed", "index"),
        ("sentiment", "fear_greed"),
        ("fear_greed_index",)
    )

    if not valid_range(value, 0, 100):
        return None

    return value


def extract_btc_dominance(market):
    value = metric(
        market,
        ("global", "market_cap_percentage", "btc"),
        ("global", "btc_dominance"),
        ("global_market", "btc_dominance"),
        ("global_market", "market_cap_percentage", "btc"),
        ("btc_dominance",)
    )

    if value is not None and not valid_range(value, 0, 100):
        return None

    return value


def extract_macro(macro):
    metrics = safe_dict(macro.get("metrics"))

    vix = metric(
        {"metrics": metrics},
        ("metrics", "VIX"),
        ("metrics", "vix"),
        ("metrics", "VIXCLS")
    )

    usd = metric(
        {"metrics": metrics},
        ("metrics", "DTWEXBGS"),
        ("metrics", "usd_broad"),
        ("metrics", "broad_usd"),
        ("metrics", "USD_BROAD")
    )

    yield_10y = metric(
        {"metrics": metrics},
        ("metrics", "DGS10"),
        ("metrics", "10Y"),
        ("metrics", "10y_yield"),
        ("metrics", "yield_10y")
    )

    macro_decision = first_value(
        macro.get("overall_macro_decision"),
        macro.get("decision"),
        macro.get("overall_decision")
    )

    if isinstance(macro_decision, dict):
        macro_decision = first_value(
            macro_decision.get("decision"),
            macro_decision.get("label"),
            macro_decision.get("status")
        )

    quality = safe_dict(macro.get("data_quality"))

    return {
        "vix": vix,
        "usd_broad": usd,
        "yield_10y": yield_10y,
        "decision": str(macro_decision or "UNKNOWN").upper(),
        "quality": quality
    }


def extract_breadth(advanced):
    breadth = safe_dict(advanced.get("spot_breadth"))

    if not breadth:
        breadth = safe_dict(
            get_path(advanced, "market_breadth")
        )

    if not breadth:
        breadth = safe_dict(
            get_path(advanced, "breadth")
        )

    advancing = metric(
        {"b": breadth},
        ("b", "advancing"),
        ("b", "advancing_count"),
        ("b", "advance")
    )

    declining = metric(
        {"b": breadth},
        ("b", "declining"),
        ("b", "declining_count"),
        ("b", "decline")
    )

    ratio = metric(
        {"b": breadth},
        ("b", "advance_decline_ratio"),
        ("b", "ad_ratio"),
        ("b", "ratio")
    )

    if ratio is None and advancing is not None and declining is not None:
        if declining > 0:
            ratio = advancing / declining

    coverage = metric(
        {"b": breadth},
        ("b", "coverage_percent"),
        ("b", "coverage"),
        ("b", "coverage_pct")
    )

    if coverage is not None and not valid_range(coverage, 0, 100):
        coverage = None

    if ratio is not None and not valid_range(ratio, 0, 100):
        ratio = None

    return {
        "advancing": advancing,
        "declining": declining,
        "ratio": ratio,
        "coverage_percent": coverage
    }


def extract_decision(decision):
    final = safe_dict(decision.get("final_decision"))

    label = first_value(
        final.get("decision"),
        final.get("action"),
        final.get("label"),
        decision.get("decision")
    )

    if isinstance(label, dict):
        label = first_value(
            label.get("decision"),
            label.get("action"),
            label.get("label")
        )

    return str(label or "UNKNOWN").upper().replace("_", " ")


# ============================================================
# TECHNICAL ANALYSIS
# ============================================================

def analyze_btc(btc):
    price = btc["price"]
    ma20 = btc["ma20"]
    ma50 = btc["ma50"]
    ma200 = btc["ma200"]
    rsi = btc["rsi"]

    missing = []

    for key in ("price", "ma20", "ma50", "ma200", "rsi"):
        if btc.get(key) is None:
            missing.append(key)

    if not valid_range(rsi, 0, 100):
        if "rsi" not in missing:
            missing.append("rsi_invalid")

    if missing:
        return {
            "quality": "INCOMPLETE",
            "missing": missing,
            "trend": "UNKNOWN",
            "bullish_points": 0,
            "bearish_points": 0,
            "support_broken": False,
            "overbought": False,
            "oversold": False
        }

    bullish = 0
    bearish = 0

    # Moving-average structure
    if price > ma20:
        bullish += 1
    else:
        bearish += 1

    if price > ma50:
        bullish += 1
    else:
        bearish += 1

    if price > ma200:
        bullish += 2
    else:
        bearish += 2

    if ma20 > ma50:
        bullish += 1
    else:
        bearish += 1

    if ma50 > ma200:
        bullish += 2
    else:
        bearish += 2

    # RSI
    if rsi >= 55:
        bullish += 1
    elif rsi <= 45:
        bearish += 1

    # MACD is optional
    macd = btc.get("macd")
    signal = btc.get("macd_signal")

    if macd is not None and signal is not None:
        if macd > signal:
            bullish += 1
        elif macd < signal:
            bearish += 1

    # Volume confirmation is optional
    volume_ratio = btc.get("volume_ratio")

    if volume_ratio is not None and volume_ratio >= 1.2:
        if price > ma20:
            bullish += 1
        elif price < ma20:
            bearish += 1

    if bullish >= bearish + 3 and price > ma200:
        trend = "BULLISH"

    elif bearish >= bullish + 3 and price < ma200:
        trend = "BEARISH"

    elif bullish > bearish:
        trend = "WEAK_BULLISH"

    elif bearish > bullish:
        trend = "WEAK_BEARISH"

    else:
        trend = "NEUTRAL"

    support = btc.get("support")

    # This is a warning only.
    # A single price comparison is not sufficient for a confirmed breakdown.
    support_broken = (
        support is not None
        and support > 0
        and price < support
    )

    return {
        "quality": "GOOD",
        "missing": [],
        "trend": trend,
        "bullish_points": bullish,
        "bearish_points": bearish,
        "support_broken": support_broken,
        "overbought": rsi >= 70,
        "oversold": rsi <= 30,
        "rsi": rsi,
        "price_above_ma200": price > ma200,
        "ma20_below_ma50": ma20 < ma50,
        "ma50_below_ma200": ma50 < ma200
    }


# ============================================================
# MACRO RISK
# ============================================================

def analyze_macro_risk(macro):
    risk_points = 0
    warnings = []

    vix = macro.get("vix")
    usd = macro.get("usd_broad")
    yield_10y = macro.get("yield_10y")

    if vix is not None:
        if vix >= 30:
            risk_points += 2
            warnings.append("VIX অত্যন্ত বেশি")

        elif vix >= 25:
            risk_points += 1
            warnings.append("VIX উচ্চ ঝুঁকি নির্দেশ করছে")

    if usd is not None:
        # Broad trade-weighted USD proxy, NOT ICE DXY.
        if usd >= 125:
            risk_points += 1
            warnings.append("Broad USD Index উচ্চ পর্যায়ে")

    if yield_10y is not None:
        if yield_10y >= 5:
            risk_points += 1
            warnings.append("US 10Y Yield উচ্চ পর্যায়ে")

    decision = macro.get("decision", "UNKNOWN")

    if "REDUCE RISK" in decision or "RISK OFF" in decision:
        risk_points += 2
        warnings.append("Macro engine ঝুঁকি কমানোর সংকেত দিয়েছে")

    elif "HIGH RISK" in decision:
        risk_points += 2
        warnings.append("Macro engine উচ্চ ঝুঁকি শনাক্ত করেছে")

    elif "CAUTION" in decision:
        risk_points += 1
        warnings.append("Macro engine সতর্কতা দিয়েছে")

    risk_points = min(risk_points, 6)

    if risk_points >= 4:
        level = "HIGH"

    elif risk_points >= 2:
        level = "MEDIUM"

    else:
        level = "LOW"

    return {
        "risk_points": risk_points,
        "risk_level": level,
        "warnings": warnings,
        "vix": vix,
        "usd_broad": usd,
        "yield_10y": yield_10y,
        "macro_decision": decision
    }


# ============================================================
# DATA QUALITY
# ============================================================

def build_data_quality(
    market_status,
    macro_status,
    advanced_status,
    decision_status,
    btc_analysis,
    macro
):
    issues = []

    if market_status["status"] != "FRESH":
        issues.append("Market snapshot fresh নয়")

    if btc_analysis["quality"] != "GOOD":
        issues.append("BTC technical data অসম্পূর্ণ")

    if macro_status["status"] != "FRESH":
        issues.append("Macro snapshot fresh নয়")

    if advanced_status["status"] != "FRESH":
        issues.append("Advanced snapshot fresh নয়")

    if decision_status["status"] not in ("FRESH", "MISSING"):
        issues.append("Final decision snapshot stale বা invalid")

    if macro.get("vix") is None:
        issues.append("VIX unavailable")

    if macro.get("yield_10y") is None:
        issues.append("US 10Y Yield unavailable")

    # Core classification gate:
    # Market snapshot + BTC technicals + Macro snapshot must be fresh.
    core_ready = (
        market_status["status"] == "FRESH"
        and macro_status["status"] == "FRESH"
        and btc_analysis["quality"] == "GOOD"
    )

    if not core_ready:
        quality = "POOR"

    elif issues:
        quality = "PARTIAL"

    else:
        quality = "GOOD"

    return {
        "status": quality,
        "core_ready": core_ready,
        "issues": issues,
        "snapshots": {
            "market": market_status,
            "macro": macro_status,
            "advanced": advanced_status,
            "decision": decision_status
        }
    }


# ============================================================
# MARKET ZONE CLASSIFICATION
# ============================================================

def classify_market(
    btc,
    btc_analysis,
    macro_risk,
    fear_greed,
    dominance,
    breadth
):
    if btc_analysis["quality"] != "GOOD":
        return {
            "zone": "INSUFFICIENT_DATA",
            "zone_code": "INSUFFICIENT_DATA",
            "position": "UNKNOWN",
            "action": "WAIT",
            "reason": "BTC technical data অসম্পূর্ণ। নির্ভরযোগ্য Market Zone নির্ধারণ সম্ভব নয়।",
            "confidence": "LOW",
            "confidence_score": 0
        }

    trend = btc_analysis["trend"]
    rsi = btc.get("rsi")
    price = btc.get("price")
    ma200 = btc.get("ma200")

    bullish = btc_analysis["bullish_points"]
    bearish = btc_analysis["bearish_points"]

    macro_points = macro_risk["risk_points"]

    reasons = []

    if trend == "BULLISH":
        reasons.append("BTC-এর প্রধান technical structure bullish")

    elif trend == "BEARISH":
        reasons.append("BTC-এর প্রধান technical structure bearish")

    elif trend == "WEAK_BULLISH":
        reasons.append("BTC-এর technical structure দুর্বল bullish")

    elif trend == "WEAK_BEARISH":
        reasons.append("BTC-এর technical structure দুর্বল bearish")

    else:
        reasons.append("BTC-এর trend এখনো পরিষ্কার নয়")

    if macro_points >= 4:
        reasons.append("Macro risk উচ্চ")

    elif macro_points >= 2:
        reasons.append("Macro risk মাঝারি")

    else:
        reasons.append("উপলব্ধ Macro indicators-এ ঝুঁকি তুলনামূলক কম")

    if breadth.get("ratio") is not None:
        if breadth["ratio"] >= 1.5:
            reasons.append("Spot market breadth ইতিবাচক")

        elif breadth["ratio"] <= 0.67:
            reasons.append("Spot market breadth দুর্বল")

    if fear_greed is not None:
        if fear_greed <= 25:
            reasons.append("Market sentiment Extreme Fear")

        elif fear_greed >= 75:
            reasons.append("Market sentiment Extreme Greed")

    if btc_analysis["support_broken"]:
        reasons.append("BTC price reported support-এর নিচে রয়েছে; breakdown confirmation প্রয়োজন")

    # --------------------------------------------------------
    # Confidence: heuristic score, NOT probability.
    # --------------------------------------------------------

    confidence_score = 40

    if btc_analysis["quality"] == "GOOD":
        confidence_score += 10

    if breadth.get("ratio") is not None:
        confidence_score += 5

    if fear_greed is not None:
        confidence_score += 5

    if macro_risk.get("vix") is not None:
        confidence_score += 5

    if macro_risk.get("yield_10y") is not None:
        confidence_score += 5

    confidence_score = min(confidence_score, 70)

    if confidence_score >= 60:
        confidence = "MODERATE"

    elif confidence_score >= 50:
        confidence = "LOW"

    else:
        confidence = "VERY_LOW"

    # --------------------------------------------------------
    # Zone rules
    # --------------------------------------------------------

    zone = "SIDEWAYS"
    zone_code = "SIDEWAYS"
    action = "WAIT"
    position = "NEUTRAL"

    # Severe bearish structure
    if (
        trend == "BEARISH"
        and price < ma200
        and macro_points >= 3
    ):
        zone = "BEAR_MARKET"
        zone_code = "BEAR_MARKET"
        action = "WAIT"
        position = "DEFENSIVE"

    # Early bull: reclaiming longer-term structure
    elif (
        price > ma200
        and price > btc["ma50"]
        and btc["ma20"] > btc["ma50"]
        and trend in ("BULLISH", "WEAK_BULLISH")
        and macro_points <= 2
    ):
        zone = "EARLY_BULL"
        zone_code = "EARLY_BULL"
        action = "HOLD"
        position = "RECOVERY"

    # Established bull market
    elif (
        price > ma200
        and btc["ma50"] > ma200
        and trend == "BULLISH"
    ):
        zone = "BULL_MARKET"
        zone_code = "BULL_MARKET"
        action = "HOLD"
        position = "BULLISH"

    # Accumulation requires multiple independent confirmations
    elif (
        price < ma200
        and rsi <= 35
        and fear_greed is not None
        and fear_greed <= 25
        and not btc_analysis["support_broken"]
        and macro_points <= 2
        and trend in ("BEARISH", "WEAK_BEARISH", "NEUTRAL")
    ):
        zone = "POTENTIAL_ACCUMULATION"
        zone_code = "ACCUMULATION"
        action = "WAIT"
        position = "POSSIBLE_BOTTOMING"

        reasons.append(
            "Extreme Fear ও oversold অবস্থার কারণে accumulation watch; "
            "এটি নিশ্চিত bottom নয়"
        )

    # Distribution watch, not automatic sell
    elif (
        price > ma200
        and rsi >= 70
        and fear_greed is not None
        and fear_greed >= 75
        and trend in ("BULLISH", "WEAK_BULLISH")
    ):
        zone = "DISTRIBUTION_RISK"
        zone_code = "DISTRIBUTION"
        action = "REDUCE RISK"
        position = "OVEREXTENDED"

        reasons.append(
            "Overbought ও Extreme Greed দেখা যাচ্ছে; "
            "এটি সতর্কতা, নিশ্চিত distribution বা Sell signal নয়"
        )

    # Short-term bearish structure
    elif (
        price < btc["ma20"]
        and price < btc["ma50"]
        and trend in ("BEARISH", "WEAK_BEARISH")
    ):
        zone = "SHORT_TERM_BEARISH"
        zone_code = "SHORT_TERM_BEARISH"
        action = "WAIT"
        position = "DEFENSIVE"

    # High macro risk overrides aggressive actions
    if macro_points >= 4:
        if action in ("HOLD", "DCA"):
            action = "WAIT"

        reasons.append(
            "উচ্চ Macro risk-এর কারণে aggressive Spot exposure এড়িয়ে চলা উচিত"
        )

    # Confirmed data does not mean confirmed support breakdown.
    if btc_analysis["support_broken"]:
        if action == "HOLD":
            action = "WAIT"

    return {
        "zone": zone,
        "zone_code": zone_code,
        "position": position,
        "action": action,
        "reason": " | ".join(reasons),
        "confidence": confidence,
        "confidence_score": confidence_score
    }


# ============================================================
# CONSERVATIVE DECISION ALIGNMENT
# ============================================================

def align_with_final_decision(zone_result, decision_label):
    zone_action = zone_result["action"]

    decision_label = (
        str(decision_label or "UNKNOWN")
        .upper()
        .replace("_", " ")
    )

    # Final Decision Engine can restrict the zone action.
    if "REDUCE RISK" in decision_label or "RISK OFF" in decision_label:
        if zone_action in ("HOLD", "DCA"):
            zone_result["action"] = "WAIT"

        zone_result["reason"] += (
            " | Final Decision Engine ঝুঁকি কমানোর নির্দেশ দিয়েছে"
        )

    elif decision_label == "WAIT":
        if zone_action in ("HOLD", "DCA"):
            zone_result["action"] = "WAIT"

        zone_result["reason"] += (
            " | Final Decision Engine-এর WAIT সিদ্ধান্ত অনুসরণ করা হয়েছে"
        )

    elif decision_label == "UNKNOWN":
        if zone_action in ("HOLD", "DCA"):
            zone_result["action"] = "WAIT"

        zone_result["reason"] += (
            " | Final Decision Engine-এর সিদ্ধান্ত পাওয়া যায়নি; "
            "সতর্কতার জন্য WAIT"
        )

    # This engine never upgrades WAIT into BUY or DCA.
    # It also never issues an automatic SELL.

    return zone_result


# ============================================================
# OUTPUT BUILDER
# ============================================================

def build_output():
    market = read_json(MARKET_FILE)
    macro = read_json(MACRO_FILE)
    advanced = read_json(ADVANCED_FILE)
    decision = read_json(DECISION_FILE)

    market_status = snapshot_status(
        market,
        MARKET_MAX_AGE_HOURS
    )

    macro_status = snapshot_status(
        macro,
        MACRO_MAX_AGE_HOURS
    )

    advanced_status = snapshot_status(
        advanced,
        ADVANCED_MAX_AGE_HOURS
    )

    decision_status = snapshot_status(
        decision,
        DECISION_MAX_AGE_HOURS
    )

    btc = extract_btc(market)
    btc_analysis = analyze_btc(btc)

    macro_data = extract_macro(macro)
    macro_risk = analyze_macro_risk(macro_data)

    fear_greed = extract_fear_greed(market)
    dominance = extract_btc_dominance(market)
    breadth = extract_breadth(advanced)

    quality = build_data_quality(
        market_status,
        macro_status,
        advanced_status,
        decision_status,
        btc_analysis,
        macro_data
    )

    decision_label = extract_decision(decision)

    # --------------------------------------------------------
    # Data quality gate
    # --------------------------------------------------------

    if not quality["core_ready"]:
        result = {
            "zone": "INSUFFICIENT_DATA",
            "zone_code": "INSUFFICIENT_DATA",
            "position": "UNKNOWN",
            "action": "WAIT",
            "reason": (
                "Market বা Macro snapshot stale/invalid অথবা "
                "BTC technical data অসম্পূর্ণ। নতুন নির্ভরযোগ্য ডেটা "
                "না পাওয়া পর্যন্ত Market Zone নির্ধারণ করা হচ্ছে না।"
            ),
            "confidence": "VERY_LOW",
            "confidence_score": 0
        }

    else:
        result = classify_market(
            btc,
            btc_analysis,
            macro_risk,
            fear_greed,
            dominance,
            breadth
        )

        result = align_with_final_decision(
            result,
            decision_label
        )

    # --------------------------------------------------------
    # Final payload
    # --------------------------------------------------------

    now = utc_now().isoformat()

    output = {
        "schema_version": 2,
        "engine": "Crypto Market Zone Engine",
        "engine_version": VERSION,
        "generated_at": now,

        "data_quality": quality,

        "current_zone": result["zone"],
        "zone_code": result["zone_code"],
        "confidence": result["confidence"],
        "confidence_score": result["confidence_score"],

        "market_position": result["position"],
        "spot_action": result["action"],
        "risk_level": macro_risk["risk_level"],

        "next_zone": (
            "পরবর্তী পরিবর্তন নির্ধারণের জন্য নতুন "
            "BTC technical ও Macro confirmation প্রয়োজন"
        ),

        "reason": result["reason"],

        "missing_data": quality["issues"],

        "verified_inputs": {
            "btc": {
                "price": btc.get("price"),
                "ma20": btc.get("ma20"),
                "ma50": btc.get("ma50"),
                "ma200": btc.get("ma200"),
                "rsi": btc.get("rsi"),
                "macd": btc.get("macd"),
                "macd_signal": btc.get("macd_signal"),
                "volume_ratio": btc.get("volume_ratio"),
                "support": btc.get("support"),
                "resistance": btc.get("resistance"),
                "trend": btc_analysis.get("trend"),
                "technical_quality": btc_analysis.get("quality"),
                "support_broken_warning": btc_analysis.get(
                    "support_broken"
                )
            },

            "sentiment": {
                "fear_greed": fear_greed,
                "btc_dominance": dominance
            },

            "macro": {
                "vix": macro_data.get("vix"),
                "usd_broad": macro_data.get("usd_broad"),
                "yield_10y": macro_data.get("yield_10y"),
                "decision": macro_data.get("decision"),
                "risk_points": macro_risk["risk_points"],
                "risk_level": macro_risk["risk_level"],
                "warnings": macro_risk["warnings"]
            },

            "spot_breadth": breadth,

            "final_decision_engine": {
                "decision": decision_label,
                "snapshot_status": decision_status["status"]
            }
        },

        "limitations": [
            "Market Zone পুরো Crypto Market-এর regime analysis; "
            "কোনো নির্দিষ্ট coin-এর BUY/SELL recommendation নয়।",

            "Dashboard scheduled snapshot ব্যবহার করে; "
            "এটি exchange-এর real-time tick feed নয়।",

            "Confidence score heuristic; এটি statistical probability নয়।",

            "BTC support-এর নিচে price থাকা একা confirmed breakdown নয়; "
            "closed-candle confirmation প্রয়োজন।",

            "Accumulation zone মানেই market bottom নিশ্চিত নয়।",

            "Distribution risk মানেই automatic SELL নয়।",

            "Broad USD metric থাকলে সেটি DTWEXBGS proxy হতে পারে; "
            "এটি ICE DXY নয়।",

            "Weekly trend confirmation এই engine-এ নেই।",

            "Spot breadth-এর coverage অসম্পূর্ণ হলে সেটিকে "
            "পুরো বাজারের নিশ্চিত প্রতিনিধিত্ব হিসেবে ধরা যাবে না।"
        ]
    }

    return output


# ============================================================
# MAIN
# ============================================================

def main():
    try:
        output = build_output()

        atomic_write_json(
            OUTPUT_FILE,
            output
        )

        print("========================================")
        print("CRYPTO MARKET ZONE ENGINE")
        print("Version:", VERSION)
        print("========================================")
        print("Zone:", output.get("current_zone"))
        print("Action:", output.get("spot_action"))
        print("Risk:", output.get("risk_level"))
        print("Data Quality:", output.get("data_quality", {}).get("status"))
        print("Output:", OUTPUT_FILE)
        print("========================================")

        # A valid WAIT/INSUFFICIENT_DATA result is still a successful run.
        return 0

    except Exception as error:
        print("MARKET ZONE ENGINE ERROR:", str(error))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
