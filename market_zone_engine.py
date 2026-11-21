
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CRYPTO MARKET ZONE ENGINE
Version: 2.0.0

Purpose:
- Classify broad crypto market regime.
- Validate snapshot and metric freshness.
- Avoid decisions from stale or incomplete BTC data.
- Use macro and advanced data as supporting context.
- Respect the Final Decision Engine's conservative decision.
- Produce Bengali explanations and actionable Spot guidance.

Inputs:
    data/market_data.json
    data/macro_data.json
    data/advanced_data.json
    data/decision_data.json

Output:
    data/market_zone_data.json

Standard library only.
"""

from __future__ import annotations

import json
import math
import os
import tempfile

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

MARKET_FILE = DATA_DIR / "market_data.json"
MACRO_FILE = DATA_DIR / "macro_data.json"
ADVANCED_FILE = DATA_DIR / "advanced_data.json"
DECISION_FILE = DATA_DIR / "decision_data.json"
OUTPUT_FILE = DATA_DIR / "market_zone_data.json"

VERSION = "2.0.0"

MARKET_MAX_AGE_HOURS = 36
MACRO_MAX_AGE_HOURS = 72
ADVANCED_MAX_AGE_HOURS = 24
DECISION_MAX_AGE_HOURS = 48

MAX_FUTURE_SECONDS = 300

# BTC technical data is essential for classification.
REQUIRED_BTC_METRICS = [
    "price",
    "ma20",
    "ma50",
    "ma200",
    "rsi14",
]

# Optional metrics improve confidence but do not block
# classification when missing.
OPTIONAL_BTC_METRICS = [
    "macd",
    "macd_signal",
    "volume_ratio",
    "support_20d",
    "resistance_20d",
]


# ============================================================
# GENERAL HELPERS
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        text = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except (ValueError, TypeError, OverflowError):
        return None


def age_hours(value: Any) -> float | None:
    parsed = parse_time(value)

    if parsed is None:
        return None

    seconds = (utc_now() - parsed).total_seconds()

    # Reject materially future-dated timestamps.
    if seconds < -MAX_FUTURE_SECONDS:
        return None

    return max(0.0, seconds / 3600.0)


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None

    if not math.isfinite(number):
        return None

    return number


def normalize_key(value: Any) -> str:
    return "".join(
        char.lower()
        for char in str(value)
        if char.isalnum()
    )


def read_json(path: Path) -> tuple[dict, str | None]:
    if not path.exists():
        return {}, f"ফাইল পাওয়া যায়নি: {path.name}"

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return {}, f"{path.name}-এর JSON root object নয়।"

        return data, None

    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{path.name} পড়তে সমস্যা: {exc}"


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as temp_file:

            json.dump(
                data,
                temp_file,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )

            temp_file.write("\n")
            temp_path = Path(temp_file.name)

        os.replace(temp_path, path)

    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def first_value(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


# ============================================================
# SNAPSHOT VALIDATION
# ============================================================

def snapshot_timestamp(data: dict) -> Any:
    return first_value(
        data.get("generated_at"),
        data.get("fetched_at"),
        data.get("updated_at"),
        data.get("timestamp"),
    )


def validate_snapshot(
    data: dict,
    label: str,
    max_age_hours: float,
) -> dict:

    timestamp = snapshot_timestamp(data)
    age = age_hours(timestamp)

    if not data:
        return {
            "status": "MISSING",
            "age_hours": None,
            "timestamp": timestamp,
            "reason": f"{label}: ডেটা পাওয়া যায়নি।",
        }

    if age is None:
        return {
            "status": "INVALID_TIMESTAMP",
            "age_hours": None,
            "timestamp": timestamp,
            "reason": f"{label}: timestamp অনুপস্থিত বা অবৈধ।",
        }

    if age > max_age_hours:
        return {
            "status": "STALE",
            "age_hours": round(age, 2),
            "timestamp": timestamp,
            "reason": (
                f"{label}: ডেটা {age:.1f} ঘণ্টা পুরোনো; "
                f"সীমা {max_age_hours} ঘণ্টা।"
            ),
        }

    return {
        "status": "FRESH",
        "age_hours": round(age, 2),
        "timestamp": timestamp,
        "reason": None,
    }


# ============================================================
# FLEXIBLE METRIC EXTRACTION
# ============================================================

def extract_metric_object(value: Any) -> tuple[float | None, Any]:
    """
    Supports:
        123.45
        {"value": 123.45, "status": "OK"}
        {"current": 123.45}
    """

    if isinstance(value, dict):

        status = str(value.get("status", "OK")).upper()

        if status in {
            "MISSING",
            "UNAVAILABLE",
            "ERROR",
            "INVALID",
            "STALE",
            "FAILED",
        }:
            return None, first_value(
                value.get("observed_at"),
                value.get("as_of"),
                value.get("timestamp"),
                value.get("fetched_at"),
            )

        raw = first_value(
            value.get("value"),
            value.get("current"),
            value.get("latest"),
            value.get("close"),
        )

        timestamp = first_value(
            value.get("observed_at"),
            value.get("as_of"),
            value.get("timestamp"),
            value.get("fetched_at"),
            value.get("source_updated_at"),
        )

        return finite_number(raw), timestamp

    return finite_number(value), None


def recursive_find(
    data: Any,
    aliases: set[str],
    depth: int = 0,
) -> tuple[float | None, Any]:

    if depth > 12:
        return None, None

    if isinstance(data, dict):

        # Prefer exact key matches at the current level.
        for key, value in data.items():
            if normalize_key(key) in aliases:
                number, timestamp = extract_metric_object(value)

                if number is not None:
                    return number, timestamp

        # Search nested objects.
        for value in data.values():
            if isinstance(value, (dict, list)):
                number, timestamp = recursive_find(
                    value,
                    aliases,
                    depth + 1,
                )

                if number is not None:
                    return number, timestamp

    elif isinstance(data, list):

        for value in data:
            number, timestamp = recursive_find(
                value,
                aliases,
                depth + 1,
            )

            if number is not None:
                return number, timestamp

    return None, None


def get_metric(
    data: dict,
    aliases: list[str],
) -> tuple[float | None, Any]:

    normalized = {normalize_key(x) for x in aliases}

    return recursive_find(data, normalized)


def get_btc_technical(market: dict) -> dict:
    """
    Supports the expected market_data structure:
        technical.BTC
        technical.btc
        btc_technical
        assets.BTC.technical
    """

    candidates = []

    technical = market.get("technical")

    if isinstance(technical, dict):
        candidates.extend([
            technical.get("BTC"),
            technical.get("btc"),
        ])

    candidates.extend([
        market.get("btc_technical"),
        market.get("BTC"),
    ])

    assets = market.get("assets")

    if isinstance(assets, dict):
        btc = assets.get("BTC") or assets.get("btc")

        if isinstance(btc, dict):
            candidates.append(
                btc.get("technical", btc)
            )

    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate

    return {}


def extract_btc_metrics(market: dict) -> dict:
    technical = get_btc_technical(market)

    aliases = {
        "price": ["price", "close", "current_price"],
        "ma20": ["ma20", "sma20", "sma_20"],
        "ma50": ["ma50", "sma50", "sma_50"],
        "ma200": ["ma200", "sma200", "sma_200"],
        "rsi14": ["rsi14", "rsi_14", "rsi"],
        "macd": ["macd", "macd_line"],
        "macd_signal": [
            "macd_signal",
            "macd_signal_line",
            "signal_line",
        ],
        "volume_ratio": [
            "volume_ratio",
            "volume_sma_ratio",
            "relative_volume",
        ],
        "support_20d": [
            "support_20d",
            "support20d",
            "support",
        ],
        "resistance_20d": [
            "resistance_20d",
            "resistance20d",
            "resistance",
        ],
    }

    result = {}

    for name, names in aliases.items():
        value, timestamp = get_metric(technical, names)

        if value is None:
            value, timestamp = get_metric(market, names)

        result[name] = value
        result[name + "_timestamp"] = timestamp

    return result


# ============================================================
# MACRO AND ADVANCED DATA
# ============================================================

def extract_macro_context(macro: dict) -> dict:

    metrics = macro.get("metrics")

    if not isinstance(metrics, dict):
        metrics = macro

    vix, vix_time = get_metric(
        metrics,
        ["VIX", "VIXCLS"],
    )

    usd, usd_time = get_metric(
        metrics,
        ["DTWEXBGS", "USD_BROAD", "BROAD_USD"],
    )

    yield_10y, yield_time = get_metric(
        metrics,
        ["DGS10", "US10Y", "TREASURY_10Y"],
    )

    macro_decision = macro.get("overall_macro_decision")

    if isinstance(macro_decision, dict):
        macro_label = first_value(
            macro_decision.get("decision"),
            macro_decision.get("label"),
            macro_decision.get("status"),
        )
    else:
        macro_label = macro_decision

    if not isinstance(macro_label, str):
        macro_label = "UNKNOWN"

    return {
        "vix": vix,
        "vix_timestamp": vix_time,
        "usd_broad": usd,
        "usd_timestamp": usd_time,
        "yield_10y": yield_10y,
        "yield_timestamp": yield_time,
        "decision": macro_label.upper().replace("_", " "),
        "data_quality": macro.get("data_quality", "UNKNOWN"),
    }


def extract_advanced_context(advanced: dict) -> dict:

    mvrv, mvrv_time = get_metric(
        advanced,
        ["mvrv", "mvrv_ratio", "capmvrvcur"],
    )

    advance, _ = get_metric(
        advanced,
        ["advancing", "advancing_coins", "advancers"],
    )

    decline, _ = get_metric(
        advanced,
        ["declining", "declining_coins", "decliners"],
    )

    breadth_ratio = None

    if (
        advance is not None
        and decline is not None
        and advance >= 0
        and decline > 0
    ):
        breadth_ratio = advance / decline

    return {
        "mvrv": mvrv,
        "mvrv_timestamp": mvrv_time,
        "advancing": advance,
        "declining": decline,
        "breadth_ratio": breadth_ratio,
    }


def extract_fear_greed(market: dict) -> float | None:

    fear = market.get("fear_greed")

    if isinstance(fear, dict):
        raw = first_value(
            fear.get("value"),
            fear.get("current"),
            fear.get("score"),
        )
    else:
        raw = fear

    value = finite_number(raw)

    if value is None or not 0 <= value <= 100:
        return None

    return value


def extract_btc_dominance(market: dict) -> float | None:

    global_data = market.get("global")

    if not isinstance(global_data, dict):
        global_data = market

    value, _ = get_metric(
        global_data,
        ["btc_dominance", "btc_dominance_percentage"],
    )

    if value is None or not 0 <= value <= 100:
        return None

    return value


# ============================================================
# BTC TECHNICAL VALIDATION
# ============================================================

def validate_btc_metrics(metrics: dict) -> dict:

    missing = []
    invalid = []

    for key in REQUIRED_BTC_METRICS:
        value = metrics.get(key)

        if value is None:
            missing.append(key)

    price = metrics.get("price")
    rsi = metrics.get("rsi14")

    for key in ["price", "ma20", "ma50", "ma200"]:
        value = metrics.get(key)

        if value is not None and value <= 0:
            invalid.append(key)

    if rsi is not None and not 0 <= rsi <= 100:
        invalid.append("rsi14")

    valid = not missing and not invalid

    return {
        "valid": valid,
        "missing": missing,
        "invalid": invalid,
    }


def classify_btc_trend(metrics: dict) -> str:

    price = metrics.get("price")
    ma20 = metrics.get("ma20")
    ma50 = metrics.get("ma50")
    ma200 = metrics.get("ma200")

    if any(
        value is None
        for value in [price, ma20, ma50, ma200]
    ):
        return "UNKNOWN"

    if price > ma20 > ma50 > ma200:
        return "STRONG_BULLISH"

    if price > ma50 and ma20 > ma50:
        return "BULLISH"

    if price < ma20 < ma50 < ma200:
        return "STRONG_BEARISH"

    if price < ma50 and ma20 < ma50:
        return "BEARISH"

    return "MIXED"


# ============================================================
# MACRO RISK
# ============================================================

def calculate_macro_risk(context: dict) -> dict:

    score = 0
    reasons = []
    missing = []

    vix = context.get("vix")
    usd = context.get("usd_broad")
    yield_10y = context.get("yield_10y")

    if vix is not None:
        if vix >= 30:
            score += 2
            reasons.append("VIX খুব বেশি; বাজারে ঝুঁকি ও অস্থিরতা উঁচু।")
        elif vix >= 25:
            score += 1
            reasons.append("VIX elevated; বাজারে সতর্কতা প্রয়োজন।")
    else:
        missing.append("VIX")

    if usd is not None:
        # DTWEXBGS is a broad trade-weighted USD proxy,
        # not the ICE DXY index. No fixed 125 threshold is used.
        reasons.append(
            "Broad USD data পাওয়া গেছে; trend data ছাড়া "
            "এটিকে একক risk trigger ধরা হয়নি।"
        )
    else:
        missing.append("Broad USD")

    if yield_10y is not None:
        if yield_10y >= 5.0:
            score += 1
            reasons.append("US 10Y yield উচ্চ পর্যায়ে রয়েছে।")
    else:
        missing.append("US 10Y yield")

    label = (
        "HIGH"
        if score >= 2
        else "MODERATE"
        if score == 1
        else "LOW_OR_UNKNOWN"
    )

    return {
        "score": score,
        "level": label,
        "reasons": reasons,
        "missing": missing,
    }


# ============================================================
# MARKET ZONE CLASSIFICATION
# ============================================================

def classify_market(
    metrics: dict,
    fear_greed: float | None,
    dominance: float | None,
    advanced: dict,
    macro_risk: dict,
) -> dict:

    price = metrics["price"]
    ma20 = metrics["ma20"]
    ma50 = metrics["ma50"]
    ma200 = metrics["ma200"]
    rsi = metrics["rsi14"]

    macd = metrics.get("macd")
    macd_signal = metrics.get("macd_signal")
    volume_ratio = metrics.get("volume_ratio")

    bullish = 0
    bearish = 0
    reasons = []

    # Long-term and medium-term structure.
    if price > ma200:
        bullish += 2
        reasons.append("BTC মূল্য MA200-এর উপরে।")
    else:
        bearish += 2
        reasons.append("BTC মূল্য MA200-এর নিচে।")

    if ma20 > ma50:
        bullish += 1
        reasons.append("MA20, MA50-এর উপরে।")
    else:
        bearish += 1
        reasons.append("MA20, MA50-এর নিচে।")

    if ma50 > ma200:
        bullish += 2
        reasons.append("MA50, MA200-এর উপরে; দীর্ঘমেয়াদি trend ইতিবাচক।")
    else:
        bearish += 2
        reasons.append("MA50, MA200-এর নিচে; দীর্ঘমেয়াদি trend দুর্বল।")

    if price > ma20:
        bullish += 1
    else:
        bearish += 1

    # RSI momentum.
    if rsi >= 60:
        bullish += 1
        reasons.append("RSI শক্তিশালী momentum নির্দেশ করছে।")
    elif rsi <= 40:
        bearish += 1
        reasons.append("RSI দুর্বল momentum নির্দেশ করছে।")
    else:
        reasons.append("RSI মাঝামাঝি অবস্থানে রয়েছে।")

    if rsi >= 70:
        reasons.append(
            "RSI 70-এর উপরে; বাজার অতিরিক্ত উত্তপ্ত হতে পারে। "
            "এটি একা SELL signal নয়।"
        )

    if rsi <= 30:
        reasons.append(
            "RSI 30-এর নিচে; বাজার oversold। "
            "এটি একা BUY বা DCA signal নয়।"
        )

    # MACD.
    if macd is not None and macd_signal is not None:
        if macd > macd_signal:
            bullish += 1
            reasons.append("MACD signal line-এর উপরে।")
        else:
            bearish += 1
            reasons.append("MACD signal line-এর নিচে।")

    # Volume.
    if volume_ratio is not None:
        if volume_ratio >= 1.2:
            reasons.append("Volume স্বাভাবিকের চেয়ে বেশি।")
        elif volume_ratio < 0.8:
            reasons.append("Volume দুর্বল; trend confirmation কম।")

    # Fear and Greed.
    if fear_greed is not None:
        if fear_greed <= 20:
            reasons.append("Fear & Greed-এ Extreme Fear রয়েছে।")
        elif fear_greed >= 80:
            reasons.append("Fear & Greed-এ Extreme Greed রয়েছে।")

    # Market breadth.
    breadth = advanced.get("breadth_ratio")

    if breadth is not None:
        if breadth >= 1.5:
            bullish += 1
            reasons.append("Spot market breadth ইতিবাচক।")
        elif breadth <= 0.67:
            bearish += 1
            reasons.append("Spot market breadth দুর্বল।")

    # MVRV is context only, not an independent buy/sell trigger.
    mvrv = advanced.get("mvrv")

    if mvrv is not None:
        reasons.append(
            "MVRV Ratio পাওয়া গেছে; এটি MVRV Z-Score নয়।"
        )

    # Determine broad regime.
    zone = "NEUTRAL"
    zone_code = "NEUTRAL"

    if (
        price < ma200
        and ma20 < ma50 < ma200
        and bearish >= 6
    ):
        zone = "BEAR_MARKET"
        zone_code = "BEAR_MARKET"

    elif (
        price > ma200
        and ma20 > ma50 > ma200
        and bullish >= 6
    ):
        zone = "BULL_MARKET"
        zone_code = "BULL_MARKET"

    elif (
        price > ma200
        and ma20 > ma50
        and bullish > bearish
    ):
        zone = "EARLY_BULL"
        zone_code = "EARLY_BULL"

    elif (
        price < ma200
        and ma20 > ma50
        and bullish >= bearish
    ):
        zone = "POTENTIAL_RECOVERY"
        zone_code = "POTENTIAL_RECOVERY"

    elif (
        price < ma200
        and ma20 < ma50
        and bearish > bullish
    ):
        zone = "BEARISH_RECOVERY_RISK"
        zone_code = "BEARISH_RECOVERY_RISK"

    elif (
        price > ma200
        and ma20 < ma50
        and bearish >= bullish
    ):
        zone = "DISTRIBUTION_RISK"
        zone_code = "DISTRIBUTION_RISK"

    # Market position is descriptive, not a forecast.
    if zone in {"EARLY_BULL", "POTENTIAL_RECOVERY"}:
        position = "EARLY"
    elif zone == "BULL_MARKET":
        position = "MID_OR_LATE"
    elif zone in {"DISTRIBUTION_RISK", "BEARISH_RECOVERY_RISK"}:
        position = "TRANSITION"
    elif zone == "BEAR_MARKET":
        position = "BEAR"
    else:
        position = "UNCLEAR"

    # Confidence points are evidence coverage, not probability.
    confidence = 40

    if macd is not None and macd_signal is not None:
        confidence += 10

    if fear_greed is not None:
        confidence += 5

    if dominance is not None:
        confidence += 5

    if breadth is not None:
        confidence += 5

    if advanced.get("mvrv") is not None:
        confidence += 5

    confidence = min(confidence, 70)

    return {
        "zone": zone,
        "zone_code": zone_code,
        "position": position,
        "bullish_score": bullish,
        "bearish_score": bearish,
        "confidence": confidence,
        "reasons": reasons,
    }


# ============================================================
# SPOT ACTION POLICY
# ============================================================

def determine_spot_action(
    classification: dict,
    btc_trend: str,
    macro_risk: dict,
    decision_data: dict,
    market_quality_ok: bool,
) -> dict:

    final = decision_data.get("final_decision")

    if not isinstance(final, dict):
        final = {}

    decision_label = first_value(
        final.get("decision"),
        final.get("label"),
        final.get("action"),
    )

    if not isinstance(decision_label, str):
        decision_label = "UNKNOWN"

    decision_label = decision_label.upper().replace("_", " ")

    zone = classification["zone"]
    macro_level = macro_risk["level"]

    # Highest priority: data quality.
    if not market_quality_ok:
        return {
            "action": "WAIT",
            "risk": "HIGH",
            "reason": "প্রয়োজনীয় BTC ডেটা যাচাই করা যায়নি।",
            "instruction": (
                "নতুন Spot position নেওয়া থেকে বিরত থাকুন। "
                "আগে Market Data ও Technical Data ঠিক করুন।"
            ),
        }

    # Respect the Final Decision Engine.
    if decision_label in {"WAIT", "REDUCE RISK", "SELL"}:
        return {
            "action": "WAIT",
            "risk": "HIGH" if decision_label != "WAIT" else "MODERATE",
            "reason": (
                "Final Decision Engine-এর সিদ্ধান্ত "
                f"{decision_label}; তাই নতুন DCA অনুমোদন করা হচ্ছে না।"
            ),
            "instruction": (
                "নতুন Spot BUY/DCA আপাতত বন্ধ রাখুন। "
                "বিদ্যমান coin-এর ঝুঁকি ও portfolio weight পর্যালোচনা করুন।"
            ),
        }

    if macro_level == "HIGH":
        return {
            "action": "WAIT",
            "risk": "HIGH",
            "reason": "Macro risk বেশি; নতুন position নেওয়া নিরাপদ নয়।",
            "instruction": (
                "নতুন Spot BUY/DCA স্থগিত রাখুন। "
                "BTC trend ও Macro Risk পুনরায় যাচাই করুন।"
            ),
        }

    if zone == "BEAR_MARKET":
        return {
            "action": "WAIT",
            "risk": "HIGH",
            "reason": "BTC-এর দীর্ঘমেয়াদি trend bearish।",
            "instruction": (
                "নতুন Altcoin DCA করবেন না। "
                "BTC-এর MA20/50/200 structure উন্নত হওয়া পর্যন্ত অপেক্ষা করুন।"
            ),
        }

    if zone in {
        "DISTRIBUTION_RISK",
        "BEARISH_RECOVERY_RISK",
    }:
        return {
            "action": "WAIT",
            "risk": "HIGH",
            "reason": "Market structure দুর্বল বা transition পর্যায়ে।",
            "instruction": (
                "নতুন Spot position নেওয়ার আগে trend confirmation অপেক্ষা করুন। "
                "অতিরিক্ত ঝুঁকিপূর্ণ coin-এর exposure পর্যালোচনা করুন।"
            ),
        }

    if zone == "BULL_MARKET":
        return {
            "action": "HOLD",
            "risk": "MODERATE",
            "reason": "BTC-এর দীর্ঘ ও মধ্যমেয়াদি trend bullish।",
            "instruction": (
                "ভালো fundamentals-এর existing Spot coin HOLD করুন। "
                "শুধু এই Market Zone দেখে নতুন coin কিনবেন না।"
            ),
        }

    if zone in {"EARLY_BULL", "POTENTIAL_RECOVERY"}:
        if btc_trend in {"STRONG_BULLISH", "BULLISH"}:
            return {
                "action": "CAUTIOUS_DCA",
                "risk": "MODERATE",
                "reason": (
                    "BTC structure উন্নতির ইঙ্গিত দিচ্ছে, "
                    "তবে পূর্ণ Bull Market confirmation হয়নি।"
                ),
                "instruction": (
                    "শুধু উচ্চমানের fundamentals ও গ্রহণযোগ্য valuation-এর "
                    "coin বিবেচনা করুন। একবারে পুরো অর্থ বিনিয়োগ করবেন না।"
                ),
            }

    return {
        "action": "WAIT",
        "risk": "MODERATE",
        "reason": "Market direction এখনো পরিষ্কার নয়।",
        "instruction": (
            "নতুন Spot BUY আপাতত অপেক্ষায় রাখুন। "
            "BTC trend, volume এবং macro confirmation পর্যবেক্ষণ করুন।"
        ),
    }


# ============================================================
# MAIN ENGINE
# ============================================================

def build_market_zone() -> dict:

    market, market_error = read_json(MARKET_FILE)
    macro, macro_error = read_json(MACRO_FILE)
    advanced, advanced_error = read_json(ADVANCED_FILE)
    decision, decision_error = read_json(DECISION_FILE)

    market_status = validate_snapshot(
        market,
        "Market Snapshot",
        MARKET_MAX_AGE_HOURS,
    )

    macro_status = validate_snapshot(
        macro,
        "Macro Snapshot",
        MACRO_MAX_AGE_HOURS,
    )

    advanced_status = validate_snapshot(
        advanced,
        "Advanced Snapshot",
        ADVANCED_MAX_AGE_HOURS,
    )

    decision_status = validate_snapshot(
        decision,
        "Decision Snapshot",
        DECISION_MAX_AGE_HOURS,
    )

    data_errors = [
        error for error in [
            market_error,
            macro_error,
            advanced_error,
            decision_error,
        ]
        if error
    ]

    metrics = extract_btc_metrics(market)
    btc_validation = validate_btc_metrics(metrics)

    btc_trend = classify_btc_trend(metrics)

    fear_greed = extract_fear_greed(market)
    dominance = extract_btc_dominance(market)

    macro_context = extract_macro_context(macro)
    advanced_context = extract_advanced_context(advanced)

    macro_risk = calculate_macro_risk(macro_context)

    # A valid, fresh market snapshot and complete BTC essentials
    # are mandatory for classification.
    market_quality_ok = (
        market_status["status"] == "FRESH"
        and btc_validation["valid"]
    )

    missing_data = []

    if market_status["status"] != "FRESH":
        missing_data.append(market_status["reason"])

    for name in btc_validation["missing"]:
        missing_data.append(
            f"BTC Technical: {name} পাওয়া যায়নি।"
        )

    for name in btc_validation["invalid"]:
        missing_data.append(
            f"BTC Technical: {name} অবৈধ।"
        )

    if macro_status["status"] != "FRESH":
        missing_data.append(
            "Macro Snapshot fresh নয়; Macro Risk অসম্পূর্ণ।"
        )

    if advanced_status["status"] != "FRESH":
        missing_data.append(
            "Advanced Snapshot fresh নয়; On-chain/Breadth context অসম্পূর্ণ।"
        )

    if decision_status["status"] != "FRESH":
        missing_data.append(
            "Final Decision Snapshot fresh নয়; conservative policy প্রয়োগ করা হবে।"
        )

    if not market_quality_ok:

        classification = {
            "zone": "INSUFFICIENT_DATA",
            "zone_code": "INSUFFICIENT_DATA",
            "position": "UNKNOWN",
            "bullish_score": 0,
            "bearish_score": 0,
            "confidence": 0,
            "reasons": [
                "Market Zone নির্ধারণের জন্য প্রয়োজনীয় BTC data যাচাই হয়নি।"
            ],
        }

        spot = {
            "action": "WAIT",
            "risk": "HIGH",
            "reason": "প্রয়োজনীয় BTC data অনুপস্থিত, stale অথবা invalid।",
            "instruction": (
                "নতুন Spot position নেবেন না। "
                "প্রথমে data quality এবং BTC technical data ঠিক করুন।"
            ),
        }

    else:

        classification = classify_market(
            metrics,
            fear_greed,
            dominance,
            advanced_context,
            macro_risk,
        )

        spot = determine_spot_action(
            classification,
            btc_trend,
            macro_risk,
            decision,
            market_quality_ok,
        )

    # A stale macro snapshot cannot be treated as a verified
    # low-risk environment.
    if macro_status["status"] != "FRESH" and market_quality_ok:
        if spot["action"] in {"CAUTIOUS_DCA", "HOLD"}:
            spot = {
                "action": "WAIT",
                "risk": "HIGH",
                "reason": "Macro data fresh নয়; সামগ্রিক risk যাচাই অসম্পূর্ণ।",
                "instruction": (
                    "Macro Snapshot আপডেট না হওয়া পর্যন্ত "
                    "নতুন Spot BUY/DCA স্থগিত রাখুন।"
                ),
            }

    if advanced_status["status"] != "FRESH":
        data_quality = "PARTIAL"
    elif macro_status["status"] != "FRESH":
        data_quality = "PARTIAL"
    elif decision_status["status"] != "FRESH":
        data_quality = "PARTIAL"
    elif not market_quality_ok:
        data_quality = "POOR"
    else:
        data_quality = "GOOD"

    # Human-readable zone labels.
    zone_labels = {
        "INSUFFICIENT_DATA": "তথ্য অপর্যাপ্ত",
        "BEAR_MARKET": "বিয়ার মার্কেট",
        "BULL_MARKET": "বুল মার্কেট",
        "EARLY_BULL": "প্রাথমিক বুল পর্যায়",
        "POTENTIAL_RECOVERY": "সম্ভাব্য Recovery পর্যায়",
        "BEARISH_RECOVERY_RISK": "বিয়ারিশ Recovery ঝুঁকি",
        "DISTRIBUTION_RISK": "Distribution ঝুঁকি",
        "NEUTRAL": "নিরপেক্ষ / অনিশ্চিত",
    }

    position_labels = {
        "EARLY": "প্রাথমিক পর্যায়",
        "MID_OR_LATE": "মধ্যম বা শেষ পর্যায়",
        "TRANSITION": "পরিবর্তনশীল পর্যায়",
        "BEAR": "বিয়ার পর্যায়",
        "UNCLEAR": "নির্ধারণ করা যায়নি",
        "UNKNOWN": "তথ্য নেই",
    }

    action_labels = {
        "WAIT": "অপেক্ষা করুন",
        "HOLD": "HOLD",
        "CAUTIOUS_DCA": "সতর্কভাবে DCA বিবেচনা",
    }

    risk_labels = {
        "LOW": "কম",
        "MODERATE": "মাঝারি",
        "HIGH": "উচ্চ",
    }

    zone = classification["zone"]
    action = spot["action"]
    risk = spot["risk"]

    # Include the Final Decision Engine's label for auditability.
    final_decision = decision.get("final_decision")

    if isinstance(final_decision, dict):
        final_decision_label = first_value(
            final_decision.get("decision"),
            final_decision.get("label"),
            final_decision.get("action"),
        )
    else:
        final_decision_label = final_decision

    if not isinstance(final_decision_label, str):
        final_decision_label = "UNKNOWN"

    result = {
        "schema_version": 2,
        "engine": "Crypto Market Zone Engine",
        "engine_version": VERSION,
        "generated_at": iso_now(),

        "data_quality": data_quality,

        "current_zone": zone_labels.get(zone, "তথ্য নেই"),
        "zone_code": classification["zone_code"],

        "market_position": position_labels.get(
            classification["position"],
            "তথ্য নেই",
        ),

        "confidence": classification["confidence"],

        "confidence_note": (
            "এটি calibrated probability নয়; "
            "ডেটার coverage ও supporting evidence-এর score।"
        ),

        "next_zone": (
            "নির্দিষ্ট ভবিষ্যৎ Zone অনুমান করা হচ্ছে না। "
            "বর্তমান trend confirmation প্রয়োজন।"
        ),

        "spot_action": action_labels.get(action, "অপেক্ষা করুন"),
        "spot_action_code": action,

        "risk_level": risk_labels.get(risk, "তথ্য নেই"),
        "risk_code": risk,

        "reason": spot["reason"],
        "action_instruction": spot["instruction"],

        "btc_trend": btc_trend,
        "btc_trend_bn": {
            "STRONG_BULLISH": "শক্তিশালী বুলিশ",
            "BULLISH": "বুলিশ",
            "MIXED": "মিশ্র trend",
            "BEARISH": "বিয়ারিশ",
            "STRONG_BEARISH": "শক্তিশালী বিয়ারিশ",
            "UNKNOWN": "তথ্য নেই",
        }.get(btc_trend, "তথ্য নেই"),

        "macro_risk": macro_risk,

        "macro_decision": macro_context["decision"],
        "final_engine_decision": final_decision_label,

        "btc_technical": {
            "price": metrics.get("price"),
            "ma20": metrics.get("ma20"),
            "ma50": metrics.get("ma50"),
            "ma200": metrics.get("ma200"),
            "rsi14": metrics.get("rsi14"),
            "macd": metrics.get("macd"),
            "macd_signal": metrics.get("macd_signal"),
            "volume_ratio": metrics.get("volume_ratio"),
            "support_20d": metrics.get("support_20d"),
            "resistance_20d": metrics.get("resistance_20d"),
        },

        "fear_greed": fear_greed,
        "btc_dominance": dominance,

        "advanced_context": {
            "mvrv_ratio": advanced_context["mvrv"],
            "breadth_ratio": advanced_context["breadth_ratio"],
            "advancing": advanced_context["advancing"],
            "declining": advanced_context["declining"],
        },

        "bullish_score": classification["bullish_score"],
        "bearish_score": classification["bearish_score"],

        "reasons": classification["reasons"],

        "missing_data": missing_data,
        "data_errors": data_errors,

        "verified_inputs": {
            "market": market_status,
            "macro": macro_status,
            "advanced": advanced_status,
            "decision": decision_status,
            "btc_technical": btc_validation,
        },

        "limitations": [
            "Market Zone পুরো crypto market-এর broad regime; coin-specific BUY/SELL signal নয়।",
            "Market data scheduled snapshot; guaranteed realtime নয়।",
            "Macro data FRED release schedule অনুযায়ী delayed হতে পারে।",
            "DTWEXBGS হলো broad trade-weighted USD proxy; ICE DXY নয়।",
            "MVRV Ratio এবং MVRV Z-Score এক জিনিস নয়।",
            "Fear & Greed একা BUY/SELL signal নয়।",
            "Confidence score calibrated probability নয়।",
            "এই Engine কোনো coin-এর valuation বা tokenomics যাচাই করে না।",
            "CAUTIOUS_DCA মানে স্বয়ংক্রিয় BUY অনুমোদন নয়; coin-level fundamentals, valuation, liquidity এবং unlock যাচাই জরুরি।",
        ],
    }

    return result


# ============================================================
# ENTRY POINT
# ============================================================

def main() -> int:

    try:
        result = build_market_zone()

        atomic_write_json(OUTPUT_FILE, result)

        print("=" * 60)
        print("CRYPTO MARKET ZONE ENGINE")
        print("Version:", VERSION)
        print("Generated:", result["generated_at"])
        print("Data Quality:", result["data_quality"])
        print("Market Zone:", result["current_zone"])
        print("BTC Trend:", result["btc_trend_bn"])
        print("Spot Action:", result["spot_action"])
        print("Risk:", result["risk_level"])
        print("Output:", OUTPUT_FILE)
        print("=" * 60)

        # Missing market data is recorded in JSON. The engine
        # still exits successfully so the workflow can validate
        # and publish the diagnostic output.
        return 0

    except Exception as exc:
        print("FATAL ERROR:", repr(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
