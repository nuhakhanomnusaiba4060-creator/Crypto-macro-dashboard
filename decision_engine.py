
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CRYPTO FINAL DECISION ENGINE
Version: 2.0.0

Inputs:
    data/market_data.json
    data/macro_data.json

Output:
    data/decision_data.json

Purpose:
    - Validate snapshot and individual metric freshness.
    - Validate BTC and ETH technical data.
    - Evaluate macro risk without treating missing data as safe.
    - Avoid unsupported SELL decisions.
    - Produce conservative Spot-market guidance.
    - Preserve dashboard-compatible output structure.

This engine is a broad-market decision aid.
It does NOT generate coin-specific BUY/SELL recommendations.
"""

import json
import math
import os
import tempfile

from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

MARKET_FILE = DATA_DIR / "market_data.json"
MACRO_FILE = DATA_DIR / "macro_data.json"
OUTPUT_FILE = DATA_DIR / "decision_data.json"

MARKET_MAX_AGE_HOURS = 36
MACRO_MAX_AGE_HOURS = 72
TECHNICAL_MAX_AGE_HOURS = 60

FUTURE_TOLERANCE_MINUTES = 5

VERSION = "2.0.0"


# ============================================================
# TIME FUNCTIONS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def parse_time(value):
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        value = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except (ValueError, TypeError, OverflowError):
        return None


def hours_old(value):
    parsed = parse_time(value)

    if parsed is None:
        return None

    age = (utc_now() - parsed).total_seconds() / 3600

    if age < -(FUTURE_TOLERANCE_MINUTES / 60):
        return None

    return max(0.0, age)


def timestamp_quality(value, max_age_hours):
    age = hours_old(value)

    if age is None:
        return {
            "status": "INVALID",
            "age_hours": None,
        }

    if age > max_age_hours:
        return {
            "status": "STALE",
            "age_hours": round(age, 2),
        }

    return {
        "status": "FRESH",
        "age_hours": round(age, 2),
    }


# ============================================================
# JSON FUNCTIONS
# ============================================================

def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            result = json.load(file)

        if not isinstance(result, dict):
            return {}

        return result

    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def atomic_write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        prefix=path.stem + "_",
        suffix=".tmp",
        dir=str(path.parent),
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )

        os.replace(temp_path, path)

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ============================================================
# SAFE VALUE FUNCTIONS
# ============================================================

def finite_number(value):
    if isinstance(value, bool):
        return None

    if isinstance(value, dict):
        if value.get("status") not in (None, "OK", "SUCCESS"):
            return None

        value = value.get("value")

    try:
        number = float(value)

        if not math.isfinite(number):
            return None

        return number

    except (ValueError, TypeError, OverflowError):
        return None


def nested_value(data, *keys):
    current = data

    for key in keys:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

    return current


def metric_value(data, *keys):
    return finite_number(nested_value(data, *keys))


def first_metric(data, paths):
    for path in paths:
        value = metric_value(data, *path)

        if value is not None:
            return value

    return None


def metric_timestamp(data, *paths):
    for path in paths:
        value = nested_value(data, *path)

        if isinstance(value, dict):
            for key in (
                "source_updated_at",
                "observed_at",
                "as_of",
                "asof",
                "timestamp",
                "updated_at",
            ):
                if value.get(key):
                    return value[key]

    return None


def valid_range(value, low, high):
    return value is not None and low <= value <= high


# ============================================================
# SNAPSHOT VALIDATION
# ============================================================

def check_snapshot(data, max_age_hours):
    if not data:
        return {
            "status": "MISSING",
            "age_hours": None,
            "reason": "Input file missing or invalid.",
        }

    timestamp = data.get("generated_at") or data.get("fetched_at")

    quality = timestamp_quality(timestamp, max_age_hours)

    if quality["status"] != "FRESH":
        return {
            **quality,
            "reason": "Snapshot timestamp is missing, invalid, future-dated or stale.",
        }

    return {
        **quality,
        "reason": "Snapshot is fresh.",
    }


# ============================================================
# TECHNICAL DATA EXTRACTION
# ============================================================

def get_asset_technical(market, symbol):
    technical = market.get("technical")

    if not isinstance(technical, dict):
        technical = {}

    asset = technical.get(symbol)

    if not isinstance(asset, dict):
        asset = {}

    # Alternative structure support
    if not asset:
        alternate = market.get(
            symbol.lower() + "_technical"
        )

        if isinstance(alternate, dict):
            asset = alternate

    return asset


def analyze_asset(market, symbol):
    asset = get_asset_technical(market, symbol)

    price = first_metric(asset, [
        ("price",),
        ("current_price",),
        ("close",),
    ])

    ma20 = first_metric(asset, [
        ("sma20",),
        ("ma20",),
        ("SMA20",),
    ])

    ma50 = first_metric(asset, [
        ("sma50",),
        ("ma50",),
        ("SMA50",),
    ])

    ma200 = first_metric(asset, [
        ("sma200",),
        ("ma200",),
        ("SMA200",),
    ])

    rsi = first_metric(asset, [
        ("rsi14",),
        ("rsi",),
        ("RSI14",),
    ])

    macd = first_metric(asset, [
        ("macd",),
        ("MACD",),
    ])

    macd_signal = first_metric(asset, [
        ("macd_signal",),
        ("signal",),
        ("MACD_signal",),
    ])

    adx = first_metric(asset, [
        ("adx14",),
        ("adx",),
    ])

    volume_ratio = first_metric(asset, [
        ("volume_ratio",),
        ("volume_sma20_ratio",),
    ])

    support = first_metric(asset, [
        ("support_20d",),
        ("support",),
    ])

    resistance = first_metric(asset, [
        ("resistance_20d",),
        ("resistance",),
    ])

    bollinger_lower = first_metric(asset, [
        ("bollinger_lower",),
        ("bb_lower",),
    ])

    # Individual technical observation timestamp
    observed_at = (
        asset.get("source_updated_at")
        or asset.get("observed_at")
        or asset.get("as_of")
        or market.get("generated_at")
    )

    technical_age = timestamp_quality(
        observed_at,
        TECHNICAL_MAX_AGE_HOURS,
    )

    checks = {
        "price": price is not None and price > 0,
        "ma20": ma20 is not None and ma20 > 0,
        "ma50": ma50 is not None and ma50 > 0,
        "ma200": ma200 is not None and ma200 > 0,
        "rsi": valid_range(rsi, 0, 100),
    }

    required_complete = all(checks.values())

    if not required_complete:
        quality = "INCOMPLETE"
    elif technical_age["status"] != "FRESH":
        quality = "STALE"
    else:
        quality = "FRESH"

    trend = "UNKNOWN"

    if required_complete and quality == "FRESH":
        if price > ma20 > ma50 > ma200:
            trend = "STRONG_BULLISH"

        elif price > ma50 and ma20 > ma50:
            trend = "BULLISH"

        elif price < ma20 < ma50 < ma200:
            trend = "STRONG_BEARISH"

        elif price < ma50 and ma20 < ma50:
            trend = "BEARISH"

        else:
            trend = "NEUTRAL"

    support_broken = (
        price is not None
        and support is not None
        and support > 0
        and price < support
        and quality == "FRESH"
    )

    # A support comparison alone is NOT enough to issue SELL.
    # The support value must be based on previous closed candles.
    # This engine therefore treats it only as a warning.

    return {
        "symbol": symbol,
        "quality": quality,
        "technical_age": technical_age,
        "trend": trend,
        "price": price,
        "ma20": ma20,
        "ma50": ma50,
        "ma200": ma200,
        "rsi14": rsi,
        "macd": macd,
        "macd_signal": macd_signal,
        "adx14": adx,
        "volume_ratio": volume_ratio,
        "support": support,
        "resistance": resistance,
        "bollinger_lower": bollinger_lower,
        "support_warning": support_broken,
        "checks": checks,
    }


# ============================================================
# MACRO ANALYSIS
# ============================================================

def get_macro_metric(macro, *names):
    metrics = macro.get("metrics")

    if not isinstance(metrics, dict):
        return None

    for name in names:
        item = metrics.get(name)

        value = finite_number(item)

        if value is not None:
            return value

    return None


def analyze_macro(macro):
    decision = macro.get("overall_macro_decision")

    if not isinstance(decision, dict):
        decision = {}

    decision_label = str(
        decision.get("decision", "UNKNOWN")
    ).upper()

    risk_level = str(
        decision.get("risk_level", "UNKNOWN")
    ).upper()

    vix = get_macro_metric(
        macro,
        "VIX",
        "vix",
    )

    yield_10y = get_macro_metric(
        macro,
        "DGS10",
        "10Y",
        "US10Y",
    )

    broad_usd = get_macro_metric(
        macro,
        "DTWEXBGS",
        "broad_usd",
        "usd_broad",
    )

    fed_funds = get_macro_metric(
        macro,
        "FEDFUNDS",
        "fed_funds",
    )

    critical_checks = {
        "vix": valid_range(vix, 0, 150),
        "10y_yield": valid_range(yield_10y, -1, 20),
        "broad_usd": broad_usd is not None and broad_usd > 0,
    }

    available_count = sum(
        1 for value in critical_checks.values() if value
    )

    if available_count == 3:
        quality = "GOOD"
    elif available_count >= 1:
        quality = "PARTIAL"
    else:
        quality = "POOR"

    risk_score = 0
    risk_flags = []

    if vix is not None:
        if vix >= 30:
            risk_score += 2
            risk_flags.append("VIX very high")
        elif vix >= 25:
            risk_score += 1
            risk_flags.append("VIX elevated")

    if yield_10y is not None and yield_10y >= 5:
        risk_score += 1
        risk_flags.append("US 10Y yield elevated")

    if decision_label in (
        "REDUCE RISK",
        "REDUCE_RISK",
        "HIGH RISK",
        "HIGH_RISK",
    ):
        risk_score = max(risk_score, 2)
        risk_flags.append("Macro engine recommends reducing risk")

    if risk_level in ("HIGH", "VERY_HIGH", "CRITICAL"):
        risk_score = max(risk_score, 2)
        risk_flags.append("Macro risk level is elevated")

    if quality == "POOR":
        risk_flags.append("Insufficient macro data")

    if decision_label not in (
        "RISK ON",
        "RISK_ON",
        "HOLD",
        "REDUCE RISK",
        "REDUCE_RISK",
        "WAIT",
        "UNKNOWN",
        "NEUTRAL",
    ):
        risk_flags.append("Unrecognized macro decision")

    return {
        "quality": quality,
        "decision": decision_label,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "risk_flags": risk_flags,
        "vix": vix,
        "yield_10y": yield_10y,
        "broad_usd": broad_usd,
        "fed_funds": fed_funds,
        "critical_checks": critical_checks,
    }


# ============================================================
# DATA QUALITY
# ============================================================

def detect_data_issues(
    market,
    macro,
    market_quality,
    macro_quality,
    btc,
    eth,
):
    issues = []

    if market_quality["status"] != "FRESH":
        issues.append(
            "Market snapshot is missing, invalid or stale."
        )

    if macro_quality["status"] != "FRESH":
        issues.append(
            "Macro snapshot is missing, invalid or stale."
        )

    if btc["quality"] != "FRESH":
        issues.append(
            "BTC technical data is incomplete or stale."
        )

    if eth["quality"] != "FRESH":
        issues.append(
            "ETH technical data is incomplete or stale."
        )

    update_mode = market.get("update_mode")

    if update_mode != "realtime":
        issues.append(
            "Market data is a scheduled snapshot, not guaranteed realtime."
        )

    if macro.get("limitations"):
        if isinstance(macro["limitations"], list):
            issues.extend(
                str(item) for item in macro["limitations"]
                if item
            )

    return list(dict.fromkeys(issues))


# ============================================================
# DECISION ENGINE
# ============================================================

def build_decision(
    market,
    macro,
    market_quality,
    macro_quality,
    btc,
    eth,
    macro_analysis,
):
    issues = detect_data_issues(
        market,
        macro,
        market_quality,
        macro_quality,
        btc,
        eth,
    )

    # Critical data gate
    data_ready = (
        market_quality["status"] == "FRESH"
        and macro_quality["status"] == "FRESH"
        and btc["quality"] == "FRESH"
    )

    reasons = []
    actions = []
    risk_items = []

    if not data_ready:
        final_decision = "WAIT"

        reasons.append(
            "Critical market, macro or BTC technical data is not verified."
        )

        actions.append(
            "নতুন Spot position নেওয়া থেকে বিরত থাকুন; আগে data quality ঠিক করুন।"
        )

        risk_items.append(
            "Incomplete or stale data can produce misleading signals."
        )

    else:
        btc_trend = btc["trend"]
        eth_trend = eth["trend"]

        macro_score = macro_analysis["risk_score"]
        macro_label = macro_analysis["decision"]

        # Strong risk conditions
        strong_macro_risk = (
            macro_score >= 3
            or macro_label in (
                "REDUCE RISK",
                "REDUCE_RISK",
            )
        )

        btc_bearish = btc_trend in (
            "BEARISH",
            "STRONG_BEARISH",
        )

        btc_bullish = btc_trend in (
            "BULLISH",
            "STRONG_BULLISH",
        )

        eth_bearish = eth_trend in (
            "BEARISH",
            "STRONG_BEARISH",
        )

        if strong_macro_risk and btc_bearish:
            final_decision = "REDUCE RISK"

            reasons.append(
                "BTC bearish structure and elevated macro risk are aligned."
            )

            actions.append(
                "নতুন Altcoin exposure বাড়াবেন না। দুর্বল ও অতিরিক্ত ঝুঁকিপূর্ণ position পর্যালোচনা করুন।"
            )

            risk_items.append(
                "Broad-market downside risk is elevated."
            )

        elif btc_bearish:
            final_decision = "WAIT"

            reasons.append(
                "BTC technical structure is bearish."
            )

            actions.append(
                "নতুন Spot BUY/DCA আপাতত বন্ধ রাখুন; বাজারের trend উন্নতির অপেক্ষা করুন।"
            )

        elif strong_macro_risk:
            final_decision = "REDUCE RISK"

            reasons.append(
                "Macro risk is elevated even though BTC is not confirmed bearish."
            )

            actions.append(
                "নতুন exposure বাড়াবেন না; portfolio concentration ও position risk পর্যালোচনা করুন।"
            )

        elif btc_bullish and not eth_bearish:
            final_decision = "HOLD"

            reasons.append(
                "BTC trend is bullish and macro risk is not elevated."
            )

            actions.append(
                "বিদ্যমান Spot position ধরে রাখুন; নতুন BUY সিদ্ধান্তের আগে coin-specific fundamentals ও valuation যাচাই করুন।"
            )

        else:
            final_decision = "WAIT"

            reasons.append(
                "Market signals are mixed or lack sufficient confirmation."
            )

            actions.append(
                "নতুন Spot position নেওয়ার আগে BTC ও ETH trend confirmation অপেক্ষা করুন।"
            )

        if btc["support_warning"]:
            risk_items.append(
                "BTC price is below the supplied support reference; verify the support calculation and closed-candle confirmation."
            )

        if btc["rsi14"] is not None and btc["rsi14"] >= 70:
            risk_items.append(
                "BTC RSI is overbought; avoid chasing extended price moves."
            )

        if eth["rsi14"] is not None and eth["rsi14"] >= 70:
            risk_items.append(
                "ETH RSI is overbought."
            )

        if eth["quality"] != "FRESH":
            risk_items.append(
                "ETH technical data is not fully verified; ETH confirmation is limited."
            )

        if macro_analysis["quality"] != "GOOD":
            risk_items.append(
                "Macro metrics are incomplete."
            )

    return {
        "decision": final_decision,
        "market_status": final_decision,
        "reasons": reasons,
        "actions": actions,
        "risk": risk_items,
        "data_ready": data_ready,
        "decision_scope": "BROAD_CRYPTO_MARKET_SPOT",
        "not_coin_specific": True,
    }


# ============================================================
# MAIN
# ============================================================

def main():
    generated_at = utc_now().isoformat()

    market = read_json(MARKET_FILE)
    macro = read_json(MACRO_FILE)

    market_quality = check_snapshot(
        market,
        MARKET_MAX_AGE_HOURS,
    )

    macro_quality = check_snapshot(
        macro,
        MACRO_MAX_AGE_HOURS,
    )

    btc = analyze_asset(market, "BTC")
    eth = analyze_asset(market, "ETH")

    macro_analysis = analyze_macro(macro)

    final_decision = build_decision(
        market,
        macro,
        market_quality,
        macro_quality,
        btc,
        eth,
        macro_analysis,
    )

    issues = detect_data_issues(
        market,
        macro,
        market_quality,
        macro_quality,
        btc,
        eth,
    )

    if macro_analysis["quality"] != "GOOD":
        issues.append(
            "Macro critical metric coverage is incomplete."
        )

    data_quality_status = (
        "GOOD"
        if final_decision["data_ready"]
        and macro_analysis["quality"] == "GOOD"
        else "PARTIAL"
    )

    output = {
        "engine": "CRYPTO FINAL DECISION ENGINE",
        "version": VERSION,
        "generated_at": generated_at,

        "data_quality": {
            "status": data_quality_status,
            "market_snapshot": market_quality,
            "macro_snapshot": macro_quality,
            "btc_technical": btc["quality"],
            "eth_technical": eth["quality"],
            "issues": list(dict.fromkeys(issues)),
        },

        "macro_analysis": macro_analysis,

        "crypto_market": {
            "global_market": market.get("global", {}),
            "fear_greed": market.get("fear_greed", {}),
            "btc": btc,
            "eth": eth,
        },

        "final_decision": final_decision,

        "limitations": [
            "This engine evaluates broad crypto-market Spot risk, not individual coin fundamentals.",
            "Scheduled snapshots are not guaranteed realtime.",
            "Macro data may be delayed by official publication schedules.",
            "A support warning alone is not a confirmed breakdown.",
            "RSI overbought alone is not a SELL signal.",
            "This engine does not provide personalized portfolio allocation.",
            "No futures or margin trading signals are generated.",
        ],
    }

    atomic_write_json(OUTPUT_FILE, output)

    print("=" * 60)
    print("CRYPTO FINAL DECISION ENGINE")
    print("Version:", VERSION)
    print("Decision:", final_decision["decision"])
    print("Data Quality:", data_quality_status)
    print("BTC Trend:", btc["trend"])
    print("ETH Trend:", eth["trend"])
    print("Macro Risk Score:", macro_analysis["risk_score"])
    print("Output:", OUTPUT_FILE)
    print("=" * 60)


if __name__ == "__main__":
    main()
