
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CRYPTO MARKET ZONE ENGINE
Version: 3.0.0

Purpose:
- Classify broad crypto market regime.
- Read the actual project JSON schemas.
- Validate snapshot and individual metric freshness.
- Reject missing, invalid, stale and future-dated metrics.
- Respect Macro and Final Decision Engine restrictions.
- Never authorize DCA from incomplete or unsafe data.
- Produce Bengali explanations and Spot guidance.

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

VERSION = "3.0.0"

MARKET_MAX_AGE_HOURS = 36
MACRO_MAX_AGE_HOURS = 72
ADVANCED_MAX_AGE_HOURS = 24
DECISION_MAX_AGE_HOURS = 48

# Individual metric freshness.
BTC_METRIC_MAX_AGE_HOURS = 36
MACRO_METRIC_MAX_AGE_HOURS = 72
ADVANCED_METRIC_MAX_AGE_HOURS = 24

MAX_FUTURE_SECONDS = 300

REQUIRED_BTC_METRICS = [
    "price",
    "ma20",
    "ma50",
    "ma200",
    "rsi14",
]

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
        text = value.strip()

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

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


def first_value(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def read_path(data: Any, *path: str) -> Any:
    current = data

    for key in path:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

    return current


def read_json(path: Path) -> tuple[dict, str | None]:
    if not path.exists():
        return {}, f"{path.name} ফাইল পাওয়া যায়নি।"

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return {}, f"{path.name}-এর JSON root object নয়।"

        return data, None

    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{path.name} পড়তে সমস্যা হয়েছে: {exc}"


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
            "reason": f"{label}: সময়ের তথ্য অনুপস্থিত অথবা অবৈধ।",
        }

    if age > max_age_hours:
        return {
            "status": "STALE",
            "age_hours": round(age, 2),
            "timestamp": timestamp,
            "reason": (
                f"{label}: ডেটা {age:.1f} ঘণ্টা পুরোনো। "
                f"অনুমোদিত সীমা {max_age_hours} ঘণ্টা।"
            ),
        }

    return {
        "status": "FRESH",
        "age_hours": round(age, 2),
        "timestamp": timestamp,
        "reason": None,
    }


# ============================================================
# METRIC EXTRACTION AND VALIDATION
# ============================================================

BAD_STATUSES = {
    "MISSING",
    "UNAVAILABLE",
    "ERROR",
    "INVALID",
    "STALE",
    "FAILED",
    "NO_DATA",
    "NOT_AVAILABLE",
}


def extract_metric(value: Any) -> dict:
    """
    Supports numeric values and metric objects.

    Metric object examples:
        {
            "value": 123.45,
            "status": "OK",
            "source_updated_at": "...",
            "fetched_at": "..."
        }

    Returns:
        value, status, timestamp, age_hours, valid
    """

    if isinstance(value, dict):

        status = str(value.get("status", "OK")).upper()

        timestamp = first_value(
            value.get("source_updated_at"),
            value.get("fetched_at"),
            value.get("observed_at"),
            value.get("as_of"),
            value.get("timestamp"),
        )

        raw = first_value(
            value.get("value"),
            value.get("current"),
            value.get("latest"),
            value.get("close"),
        )

        number = finite_number(raw)
        age = age_hours(timestamp)

        if status in BAD_STATUSES:
            number = None

        valid = number is not None and status not in BAD_STATUSES

        return {
            "value": number,
            "status": status,
            "timestamp": timestamp,
            "age_hours": round(age, 2) if age is not None else None,
            "valid": valid,
        }

    number = finite_number(value)

    return {
        "value": number,
        "status": "OK" if number is not None else "MISSING",
        "timestamp": None,
        "age_hours": None,
        "valid": number is not None,
    }


def validate_metric_freshness(
    metric: dict,
    max_age_hours: float,
    snapshot_time: Any = None,
) -> dict:
    """
    If an individual source timestamp is absent, the snapshot
    timestamp is used as a fallback.

    A fresh snapshot does not automatically make an old
    source timestamp fresh.
    """

    timestamp = first_value(
        metric.get("timestamp"),
        snapshot_time,
    )

    age = age_hours(timestamp)

    if not metric.get("valid"):
        return {
            "valid": False,
            "status": metric.get("status", "MISSING"),
            "timestamp": timestamp,
            "age_hours": round(age, 2) if age is not None else None,
            "reason": "মান অনুপস্থিত, অবৈধ অথবা provider unavailable।",
        }

    if age is None:
        return {
            "valid": False,
            "status": "INVALID_TIMESTAMP",
            "timestamp": timestamp,
            "age_hours": None,
            "reason": "Metric-এর সময়ের তথ্য যাচাই করা যায়নি।",
        }

    if age > max_age_hours:
        return {
            "valid": False,
            "status": "STALE",
            "timestamp": timestamp,
            "age_hours": round(age, 2),
            "reason": f"Metric {age:.1f} ঘণ্টা পুরোনো।",
        }

    return {
        "valid": True,
        "status": "FRESH",
        "timestamp": timestamp,
        "age_hours": round(age, 2),
        "reason": None,
    }


def metric_value(
    data: Any,
    *path: str,
) -> dict:
    return extract_metric(read_path(data, *path))


def checked_metric(
    data: Any,
    path: tuple[str, ...],
    max_age_hours: float,
    snapshot_time: Any,
) -> tuple[float | None, dict]:

    metric = metric_value(data, *path)

    freshness = validate_metric_freshness(
        metric,
        max_age_hours,
        snapshot_time,
    )

    value = metric["value"] if freshness["valid"] else None

    return value, freshness


# ============================================================
# BTC TECHNICAL DATA
# ============================================================

def extract_btc_metrics(market: dict) -> tuple[dict, dict]:
    """
    Actual data_engine.py structure:

        technical.BTC.price_usdt.value
        technical.BTC.indicators.ma20.value
        technical.BTC.indicators.ma50.value
        technical.BTC.indicators.ma200.value
        technical.BTC.indicators.rsi14.value

    Individual metric timestamps are checked separately.
    """

    btc = read_path(market, "technical", "BTC")

    if not isinstance(btc, dict):
        btc = read_path(market, "technical", "btc")

    if not isinstance(btc, dict):
        btc = {}

    indicators = btc.get("indicators")

    if not isinstance(indicators, dict):
        indicators = {}

    snapshot_time = snapshot_timestamp(market)

    metric_paths = {
        "price": ("technical", "BTC", "price_usdt"),
        "ma20": ("technical", "BTC", "indicators", "ma20"),
        "ma50": ("technical", "BTC", "indicators", "ma50"),
        "ma200": ("technical", "BTC", "indicators", "ma200"),
        "rsi14": ("technical", "BTC", "indicators", "rsi14"),
        "macd": ("technical", "BTC", "indicators", "macd"),
        "macd_signal": (
            "technical", "BTC", "indicators", "macd_signal"
        ),
        "volume_ratio": (
            "technical", "BTC", "indicators", "volume_ratio_20d"
        ),
        "support_20d": (
            "technical", "BTC", "indicators", "support_20d"
        ),
        "resistance_20d": (
            "technical", "BTC", "indicators", "resistance_20d"
        ),
    }

    result = {}
    checks = {}

    for name, path in metric_paths.items():

        value, check = checked_metric(
            market,
            path,
            BTC_METRIC_MAX_AGE_HOURS,
            snapshot_time,
        )

        # Do not silently fall back to a similarly named
        # unrelated metric elsewhere in the JSON.
        result[name] = value
        checks[name] = check

    # The actual market schema uses technical.BTC, but this
    # fallback supports a lowercase BTC key without recursive
    # searching through unrelated objects.
    if not btc:
        lowercase_paths = {
            "price": ("technical", "btc", "price_usdt"),
            "ma20": ("technical", "btc", "indicators", "ma20"),
            "ma50": ("technical", "btc", "indicators", "ma50"),
            "ma200": ("technical", "btc", "indicators", "ma200"),
            "rsi14": ("technical", "btc", "indicators", "rsi14"),
            "macd": ("technical", "btc", "indicators", "macd"),
            "macd_signal": (
                "technical", "btc", "indicators", "macd_signal"
            ),
            "volume_ratio": (
                "technical", "btc", "indicators", "volume_ratio_20d"
            ),
            "support_20d": (
                "technical", "btc", "indicators", "support_20d"
            ),
            "resistance_20d": (
                "technical", "btc", "indicators", "resistance_20d"
            ),
        }

        for name, path in lowercase_paths.items():
            value, check = checked_metric(
                market,
                path,
                BTC_METRIC_MAX_AGE_HOURS,
                snapshot_time,
            )
            result[name] = value
            checks[name] = check

    return result, checks


def validate_btc_metrics(metrics: dict) -> dict:

    missing = []
    invalid = []
    stale = []

    for key in REQUIRED_BTC_METRICS:

        value = metrics.get(key)
        check = metrics.get("_checks", {}).get(key, {})

        if value is None:

            if check.get("status") == "STALE":
                stale.append(key)
            elif check.get("status") in {
                "INVALID",
                "INVALID_TIMESTAMP",
            }:
                invalid.append(key)
            else:
                missing.append(key)

    for key in ["price", "ma20", "ma50", "ma200"]:

        value = metrics.get(key)

        if value is not None and value <= 0:
            invalid.append(key)

    rsi = metrics.get("rsi14")

    if rsi is not None and not 0 <= rsi <= 100:
        invalid.append("rsi14")

    valid = not missing and not invalid and not stale

    return {
        "valid": valid,
        "missing": sorted(set(missing)),
        "invalid": sorted(set(invalid)),
        "stale": sorted(set(stale)),
    }


# ============================================================
# FEAR & GREED AND BTC DOMINANCE
# ============================================================

def extract_fear_greed(market: dict) -> tuple[float | None, dict]:

    snapshot_time = snapshot_timestamp(market)

    metric = extract_metric(market.get("fear_greed"))

    check = validate_metric_freshness(
        metric,
        MARKET_MAX_AGE_HOURS,
        snapshot_time,
    )

    value = metric["value"] if check["valid"] else None

    if value is not None and not 0 <= value <= 100:
        value = None
        check["valid"] = False
        check["status"] = "INVALID"
        check["reason"] = "Fear & Greed মান ০ থেকে ১০০-এর মধ্যে নয়।"

    return value, check


def extract_btc_dominance(market: dict) -> tuple[float | None, dict]:

    snapshot_time = snapshot_timestamp(market)

    metric = extract_metric(
        read_path(market, "global_market", "btc_dominance_pct")
    )

    check = validate_metric_freshness(
        metric,
        MARKET_MAX_AGE_HOURS,
        snapshot_time,
    )

    value = metric["value"] if check["valid"] else None

    if value is not None and not 0 <= value <= 100:
        value = None
        check["valid"] = False
        check["status"] = "INVALID"
        check["reason"] = "BTC Dominance-এর মান গ্রহণযোগ্য নয়।"

    return value, check


# ============================================================
# MACRO DATA
# ============================================================

def extract_macro_context(macro: dict) -> tuple[dict, dict]:

    snapshot_time = snapshot_timestamp(macro)

    metric_paths = {
        "vix": ("metrics", "vix"),
        "usd_broad": ("metrics", "usd_broad_index"),
        "yield_10y": ("metrics", "yield_10y"),
    }

    values = {}
    checks = {}

    for name, path in metric_paths.items():

        value, check = checked_metric(
            macro,
            path,
            MACRO_METRIC_MAX_AGE_HOURS,
            snapshot_time,
        )

        values[name] = value
        checks[name] = check

    overall = macro.get("overall_macro_decision")

    if not isinstance(overall, dict):
        overall = {}

    # Actual macro_engine.py schema uses uppercase keys.
    macro_label = first_value(
        overall.get("DECISION"),
        overall.get("decision"),
        overall.get("label"),
        overall.get("status"),
    )

    if not isinstance(macro_label, str):
        macro_label = "UNKNOWN"

    macro_data = {
        "vix": values["vix"],
        "usd_broad": values["usd_broad"],
        "yield_10y": values["yield_10y"],
        "decision": macro_label.strip(),
        "data_quality": read_path(macro, "summary", "data_quality")
        or "UNKNOWN",
        "overall_data": overall.get("DATA", {}),
        "overall_analysis": overall.get("ANALYSIS", ""),
        "overall_action": overall.get("ACTION", ""),
        "overall_risk": overall.get("RISK", ""),
    }

    return macro_data, checks


def calculate_macro_risk(
    context: dict,
    checks: dict,
) -> dict:

    score = 0
    reasons = []
    missing = []

    vix = context.get("vix")
    usd = context.get("usd_broad")
    yield_10y = context.get("yield_10y")

    if vix is not None:

        if vix >= 30:
            score += 2
            reasons.append(
                "VIX ৩০ বা তার বেশি। বাজারে অস্থিরতা ও ঝুঁকি বেশি।"
            )

        elif vix >= 25:
            score += 1
            reasons.append(
                "VIX ২৫ বা তার বেশি। বাজারে সতর্কতা প্রয়োজন।"
            )

        else:
            reasons.append(
                "VIX ২৫-এর নিচে। এই সূচক থেকে উচ্চ অস্থিরতার সংকেত পাওয়া যায়নি।"
            )

    else:
        missing.append("VIX")

    if usd is not None:
        reasons.append(
            "Broad USD সূচকের তথ্য পাওয়া গেছে। "
            "শুধু বর্তমান মান দিয়ে ডলারের শক্তি বাড়ছে না কমছে তা নিশ্চিত করা যায় না।"
        )
    else:
        missing.append("Broad USD")

    if yield_10y is not None:

        if yield_10y >= 5.0:
            score += 1
            reasons.append(
                "যুক্তরাষ্ট্রের ১০ বছর মেয়াদি বন্ডের সুদ ৫%-এর সমান বা বেশি।"
            )
        else:
            reasons.append(
                "যুক্তরাষ্ট্রের ১০ বছর মেয়াদি বন্ডের সুদ ৫%-এর নিচে।"
            )

    else:
        missing.append("US 10Y yield")

    if score >= 2:
        label = "HIGH"
    elif score == 1:
        label = "MODERATE"
    else:
        label = "LOW_OR_UNKNOWN"

    return {
        "score": score,
        "level": label,
        "reasons": reasons,
        "missing": missing,
        "metric_checks": checks,
    }


# ============================================================
# ADVANCED DATA
# ============================================================

def extract_advanced_context(advanced: dict) -> tuple[dict, dict]:

    snapshot_time = snapshot_timestamp(advanced)

    mvrv, mvrv_check = checked_metric(
        advanced,
        ("on_chain", "mvrv_ratio"),
        ADVANCED_METRIC_MAX_AGE_HOURS,
        snapshot_time,
    )

    breadth, breadth_check = checked_metric(
        advanced,
        (
            "spot_market_activity",
            "breadth",
            "advance_decline_ratio",
        ),
        ADVANCED_METRIC_MAX_AGE_HOURS,
        snapshot_time,
    )

    advancing, advancing_check = checked_metric(
        advanced,
        (
            "spot_market_activity",
            "breadth",
            "advancing_pairs",
        ),
        ADVANCED_METRIC_MAX_AGE_HOURS,
        snapshot_time,
    )

    declining, declining_check = checked_metric(
        advanced,
        (
            "spot_market_activity",
            "breadth",
            "declining_pairs",
        ),
        ADVANCED_METRIC_MAX_AGE_HOURS,
        snapshot_time,
    )

    # Do not calculate a replacement ratio if the provider's
    # actual ratio is unavailable. Keep source values separate.
    if breadth is not None and breadth < 0:
        breadth = None
        breadth_check["valid"] = False
        breadth_check["status"] = "INVALID"

    return {
        "mvrv": mvrv,
        "breadth_ratio": breadth,
        "advancing": advancing,
        "declining": declining,
    }, {
        "mvrv": mvrv_check,
        "breadth_ratio": breadth_check,
        "advancing": advancing_check,
        "declining": declining_check,
    }


# ============================================================
# BTC TREND
# ============================================================

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
# MARKET ZONE CLASSIFICATION
# ============================================================

def classify_market(
    metrics: dict,
    fear_greed: float | None,
    dominance: float | None,
    advanced: dict,
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

    # Long-term structure.
    if price > ma200:
        bullish += 2
        reasons.append("BTC-এর বর্তমান মূল্য MA200-এর উপরে।")
    else:
        bearish += 2
        reasons.append("BTC-এর বর্তমান মূল্য MA200-এর নিচে।")

    # Medium-term structure.
    if ma20 > ma50:
        bullish += 1
        reasons.append("MA20, MA50-এর উপরে রয়েছে।")
    else:
        bearish += 1
        reasons.append("MA20, MA50-এর নিচে রয়েছে।")

    # Long-term moving average structure.
    if ma50 > ma200:
        bullish += 2
        reasons.append("MA50, MA200-এর উপরে; দীর্ঘমেয়াদি প্রবণতা ইতিবাচক।")
    else:
        bearish += 2
        reasons.append("MA50, MA200-এর নিচে; দীর্ঘমেয়াদি প্রবণতা দুর্বল।")

    if price > ma20:
        bullish += 1
        reasons.append("BTC মূল্য MA20-এর উপরে।")
    else:
        bearish += 1
        reasons.append("BTC মূল্য MA20-এর নিচে।")

    # RSI momentum.
    if rsi >= 60:
        bullish += 1
        reasons.append("RSI ৬০ বা বেশি; ঊর্ধ্বমুখী গতি শক্তিশালী।")

    elif rsi <= 40:
        bearish += 1
        reasons.append("RSI ৪০ বা কম; বাজারের গতি দুর্বল।")

    else:
        reasons.append("RSI মাঝামাঝি অবস্থানে রয়েছে।")

    if rsi >= 70:
        reasons.append(
            "RSI ৭০-এর উপরে। বাজার অতিরিক্ত উত্তপ্ত হতে পারে; "
            "তবে শুধু RSI দিয়ে SELL সিদ্ধান্ত নেওয়া যাবে না।"
        )

    if rsi <= 30:
        reasons.append(
            "RSI ৩০-এর নিচে। বাজার অতিরিক্ত বিক্রিত অবস্থায় থাকতে পারে; "
            "তবে শুধু RSI দিয়ে BUY বা DCA করা যাবে না।"
        )

    # MACD.
    if macd is not None and macd_signal is not None:

        if macd > macd_signal:
            bullish += 1
            reasons.append("MACD, Signal Line-এর উপরে রয়েছে।")
        else:
            bearish += 1
            reasons.append("MACD, Signal Line-এর নিচে রয়েছে।")

    # Volume.
    if volume_ratio is not None:

        if volume_ratio >= 1.2:
            reasons.append(
                "BTC-এর লেনদেনের পরিমাণ স্বাভাবিক গড়ের চেয়ে বেশি।"
            )

        elif volume_ratio < 0.8:
            reasons.append(
                "BTC-এর লেনদেনের পরিমাণ স্বাভাবিক গড়ের চেয়ে কম।"
            )

    # Fear & Greed.
    if fear_greed is not None:

        if fear_greed <= 20:
            reasons.append(
                "Fear & Greed সূচকে চরম ভয় রয়েছে। "
                "এটি একা BUY সংকেত নয়।"
            )

        elif fear_greed >= 80:
            reasons.append(
                "Fear & Greed সূচকে চরম লোভ রয়েছে। "
                "এটি একা SELL সংকেত নয়।"
            )

    # Spot breadth.
    breadth = advanced.get("breadth_ratio")

    if breadth is not None:

        if breadth >= 1.5:
            bullish += 1
            reasons.append(
                "Binance Spot মার্কেটে বাড়তে থাকা কয়েনের সংখ্যা "
                "কমতে থাকা কয়েনের তুলনায় বেশি।"
            )

        elif breadth <= 0.67:
            bearish += 1
            reasons.append(
                "Binance Spot মার্কেটে কমতে থাকা কয়েনের সংখ্যা বেশি।"
            )

    # MVRV context only.
    if advanced.get("mvrv") is not None:
        reasons.append(
            "BTC MVRV Ratio পাওয়া গেছে। এটি MVRV Z-Score নয় "
            "এবং একা BUY/SELL সিদ্ধান্ত নির্ধারণ করে না।"
        )

    # Zone classification.
    zone = "NEUTRAL"

    if (
        price < ma200
        and ma20 < ma50 < ma200
        and bearish >= 6
    ):
        zone = "BEAR_MARKET"

    elif (
        price > ma200
        and ma20 > ma50 > ma200
        and bullish >= 6
    ):
        zone = "BULL_MARKET"

    elif (
        price > ma200
        and ma20 > ma50
        and bullish > bearish
    ):
        zone = "EARLY_BULL"

    elif (
        price < ma200
        and ma20 > ma50
        and bullish >= bearish
    ):
        zone = "POTENTIAL_RECOVERY"

    elif (
        price < ma200
        and ma20 < ma50
        and bearish > bullish
    ):
        zone = "BEARISH_RECOVERY_RISK"

    elif (
        price > ma200
        and ma20 < ma50
        and bearish >= bullish
    ):
        zone = "DISTRIBUTION_RISK"

    if zone in {"EARLY_BULL", "POTENTIAL_RECOVERY"}:
        position = "EARLY"

    elif zone == "BULL_MARKET":
        position = "MID_OR_LATE"

    elif zone in {
        "DISTRIBUTION_RISK",
        "BEARISH_RECOVERY_RISK",
    }:
        position = "TRANSITION"

    elif zone == "BEAR_MARKET":
        position = "BEAR"

    else:
        position = "UNCLEAR"

    # Evidence coverage score, not a probability.
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
        "zone_code": zone,
        "position": position,
        "bullish_score": bullish,
        "bearish_score": bearish,
        "confidence": confidence,
        "reasons": reasons,
    }


# ============================================================
# DECISION ENGINE VALIDATION
# ============================================================

def extract_final_decision(decision_data: dict) -> str:

    final = decision_data.get("final_decision")

    if isinstance(final, dict):
        label = first_value(
            final.get("decision"),
            final.get("label"),
            final.get("action"),
        )
    else:
        label = final

    if not isinstance(label, str):
        return "UNKNOWN"

    return label.strip()


def is_macro_decision_restrictive(label: str) -> bool:

    normalized = label.upper()

    restrictive_terms = [
        "WAIT",
        "INSUFFICIENT",
        "REDUCE RISK",
        "REDUCE_RISK",
        "UNKNOWN",
        "UNAVAILABLE",
        "HIGH RISK",
    ]

    return any(term in normalized for term in restrictive_terms)


def is_final_decision_restrictive(label: str) -> bool:

    normalized = label.upper()

    restrictive_terms = [
        "WAIT",
        "REDUCE RISK",
        "REDUCE_RISK",
        "SELL",
        "UNKNOWN",
        "INSUFFICIENT",
        "UNAVAILABLE",
    ]

    return any(term in normalized for term in restrictive_terms)


# ============================================================
# SPOT ACTION POLICY
# ============================================================

def determine_spot_action(
    classification: dict,
    btc_trend: str,
    macro_risk: dict,
    macro_decision: str,
    final_decision: str,
    market_quality_ok: bool,
    macro_quality_ok: bool,
    advanced_quality_ok: bool,
    decision_quality_ok: bool,
) -> dict:

    zone = classification["zone"]
    macro_level = macro_risk["level"]

    # 1. Essential BTC data must be valid.
    if not market_quality_ok:
        return {
            "action": "WAIT",
            "risk": "HIGH",
            "reason": "প্রয়োজনীয় BTC তথ্য যাচাই করা যায়নি।",
            "instruction": (
                "নতুন Spot BUY বা DCA করবেন না। "
                "প্রথমে BTC মূল্য, MA20, MA50, MA200 এবং RSI-এর "
                "তথ্য ঠিক আছে কি না যাচাই করুন।"
            ),
        }

    # 2. Macro snapshot and decision must be verified.
    if not macro_quality_ok:
        return {
            "action": "WAIT",
            "risk": "HIGH",
            "reason": "Macro তথ্য পুরোনো অথবা অসম্পূর্ণ।",
            "instruction": (
                "Macro তথ্য যাচাই না হওয়া পর্যন্ত নতুন Spot BUY/DCA স্থগিত রাখুন।"
            ),
        }

    # 3. Respect macro engine's explicit WAIT / insufficient data.
    if is_macro_decision_restrictive(macro_decision):
        return {
            "action": "WAIT",
            "risk": "HIGH",
            "reason": (
                "Macro Engine-এর সিদ্ধান্ত: "
                f"{macro_decision}। তাই নতুন BUY/DCA অনুমোদিত নয়।"
            ),
            "instruction": (
                "নতুন Spot BUY/DCA করবেন না। "
                "Macro Engine-এর প্রয়োজনীয় তথ্য সম্পূর্ণ ও যাচাই হওয়া পর্যন্ত অপেক্ষা করুন।"
            ),
        }

    # 4. Respect the Final Decision Engine.
    if not decision_quality_ok:
        return {
            "action": "WAIT",
            "risk": "HIGH",
            "reason": "Final Decision Engine-এর তথ্য যাচাই করা যায়নি।",
            "instruction": (
                "Final Decision Engine-এর নতুন ও যাচাইকৃত ফলাফল না পাওয়া পর্যন্ত "
                "নতুন Spot BUY/DCA স্থগিত রাখুন।"
            ),
        }

    if is_final_decision_restrictive(final_decision):
        return {
            "action": "WAIT",
            "risk": "HIGH",
            "reason": (
                "Final Decision Engine-এর সিদ্ধান্ত "
                f"{final_decision}; তাই নতুন BUY/DCA অনুমোদিত নয়।"
            ),
            "instruction": (
                "নতুন Spot BUY/DCA করবেন না। "
                "বিদ্যমান কয়েনের ঝুঁকি ও Portfolio Weight পর্যালোচনা করুন।"
            ),
        }

    # 5. Incomplete advanced context cannot authorize DCA.
    if not advanced_quality_ok:
        return {
            "action": "WAIT",
            "risk": "HIGH",
            "reason": "Advanced Market তথ্য অসম্পূর্ণ বা পুরোনো।",
            "instruction": (
                "Advanced তথ্য যাচাই না হওয়া পর্যন্ত নতুন Spot BUY/DCA স্থগিত রাখুন।"
            ),
        }

    # 6. High macro risk.
    if macro_level == "HIGH":
        return {
            "action": "WAIT",
            "risk": "HIGH",
            "reason": "Macro Risk বেশি; বাজারে বড় ধরনের অস্থিরতার ঝুঁকি রয়েছে।",
            "instruction": (
                "নতুন Spot BUY/DCA স্থগিত রাখুন। "
                "BTC trend এবং Macro Risk পুনরায় যাচাই করুন।"
            ),
        }

    # 7. Bear market.
    if zone == "BEAR_MARKET":
        return {
            "action": "WAIT",
            "risk": "HIGH",
            "reason": "BTC-এর দীর্ঘমেয়াদি প্রবণতা bearish।",
            "instruction": (
                "নতুন Altcoin DCA করবেন না। "
                "BTC-এর MA20/MA50/MA200 কাঠামো উন্নত হওয়া পর্যন্ত অপেক্ষা করুন।"
            ),
        }

    # 8. Weak transition structures.
    if zone in {
        "DISTRIBUTION_RISK",
        "BEARISH_RECOVERY_RISK",
    }:
        return {
            "action": "WAIT",
            "risk": "HIGH",
            "reason": "বাজারের কাঠামো দুর্বল অথবা ঝুঁকিপূর্ণ পরিবর্তনের পর্যায়ে।",
            "instruction": (
                "নতুন Spot position নেওয়ার আগে trend confirmation অপেক্ষা করুন। "
                "অতিরিক্ত ঝুঁকিপূর্ণ কয়েনের পরিমাণ পর্যালোচনা করুন।"
            ),
        }

    # 9. Confirmed bull market.
    if zone == "BULL_MARKET":
        return {
            "action": "HOLD",
            "risk": "MODERATE",
            "reason": "BTC-এর মধ্যম ও দীর্ঘমেয়াদি প্রবণতা bullish।",
            "instruction": (
                "ভালো fundamentals-এর বিদ্যমান Spot কয়েন HOLD করুন। "
                "শুধু Market Zone দেখে নতুন কয়েন কিনবেন না।"
            ),
        }

    # 10. Early bullish / recovery.
    # This engine does not independently authorize DCA.
    if zone in {"EARLY_BULL", "POTENTIAL_RECOVERY"}:

        if btc_trend in {"STRONG_BULLISH", "BULLISH"}:
            return {
                "action": "WAIT",
                "risk": "MODERATE",
                "reason": (
                    "BTC-এর প্রবণতা উন্নতির ইঙ্গিত দিচ্ছে, "
                    "তবে পূর্ণ Bull Market confirmation হয়নি।"
                ),
                "instruction": (
                    "এখনই স্বয়ংক্রিয় DCA করবেন না। "
                    "প্রতিটি কয়েনের Fundamentals, Valuation, FDV, "
                    "Token Unlock ও Liquidity আলাদাভাবে যাচাই করুন।"
                ),
            }

    return {
        "action": "WAIT",
        "risk": "MODERATE",
        "reason": "বাজারের দিক এখনো পরিষ্কার নয়।",
        "instruction": (
            "নতুন Spot BUY আপাতত অপেক্ষায় রাখুন। "
            "BTC trend, লেনদেনের পরিমাণ এবং Macro confirmation পর্যবেক্ষণ করুন।"
        ),
    }


# ============================================================
# BENGALI LABELS
# ============================================================

ZONE_LABELS = {
    "INSUFFICIENT_DATA": "তথ্য অপর্যাপ্ত",
    "BEAR_MARKET": "বিয়ার মার্কেট",
    "BULL_MARKET": "বুল মার্কেট",
    "EARLY_BULL": "প্রাথমিক বুল পর্যায়",
    "POTENTIAL_RECOVERY": "সম্ভাব্য পুনরুদ্ধার পর্যায়",
    "BEARISH_RECOVERY_RISK": "বিয়ারিশ পুনরুদ্ধার ঝুঁকি",
    "DISTRIBUTION_RISK": "বিক্রির চাপের ঝুঁকি",
    "NEUTRAL": "নিরপেক্ষ বা অনিশ্চিত",
}

POSITION_LABELS = {
    "EARLY": "প্রাথমিক পর্যায়",
    "MID_OR_LATE": "মধ্যম অথবা শেষ পর্যায়",
    "TRANSITION": "পরিবর্তনশীল পর্যায়",
    "BEAR": "বিয়ার পর্যায়",
    "UNCLEAR": "নির্ধারণ করা যায়নি",
    "UNKNOWN": "তথ্য নেই",
}

ACTION_LABELS = {
    "WAIT": "অপেক্ষা করুন",
    "HOLD": "বিদ্যমান কয়েন ধরে রাখুন",
    "CAUTIOUS_DCA": "সতর্কভাবে DCA বিবেচনা",
}

RISK_LABELS = {
    "LOW": "কম",
    "MODERATE": "মাঝারি",
    "HIGH": "উচ্চ",
}

TREND_LABELS = {
    "STRONG_BULLISH": "শক্তিশালী বুলিশ",
    "BULLISH": "বুলিশ",
    "MIXED": "মিশ্র প্রবণতা",
    "BEARISH": "বিয়ারিশ",
    "STRONG_BEARISH": "শক্তিশালী বিয়ারিশ",
    "UNKNOWN": "তথ্য নেই",
}


# ============================================================
# MAIN ENGINE
# ============================================================

def build_market_zone() -> dict:

    market, market_error = read_json(MARKET_FILE)
    macro, macro_error = read_json(MACRO_FILE)
    advanced, advanced_error = read_json(ADVANCED_FILE)
    decision, decision_error = read_json(DECISION_FILE)

    # Snapshot validation.
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

    # BTC technical metrics.
    metrics, btc_checks = extract_btc_metrics(market)
    metrics["_checks"] = btc_checks

    btc_validation = validate_btc_metrics(metrics)
    btc_trend = classify_btc_trend(metrics)

    # Supporting market metrics.
    fear_greed, fear_check = extract_fear_greed(market)
    dominance, dominance_check = extract_btc_dominance(market)

    # Macro context.
    macro_context, macro_checks = extract_macro_context(macro)
    macro_risk = calculate_macro_risk(
        macro_context,
        macro_checks,
    )

    # Advanced context.
    advanced_context, advanced_checks = extract_advanced_context(
        advanced
    )

    # Decision Engine.
    final_decision_label = extract_final_decision(decision)

    macro_decision_label = macro_context["decision"]

    # Quality requirements.
    market_quality_ok = (
        market_status["status"] == "FRESH"
        and btc_validation["valid"]
    )

    macro_quality_ok = (
        macro_status["status"] == "FRESH"
        and all(
            check.get("valid")
            for check in macro_checks.values()
        )
        and macro_decision_label != "UNKNOWN"
    )

    advanced_quality_ok = (
        advanced_status["status"] == "FRESH"
        and advanced_checks["mvrv"].get("valid")
        and advanced_checks["breadth_ratio"].get("valid")
    )

    decision_quality_ok = (
        decision_status["status"] == "FRESH"
        and isinstance(decision.get("final_decision"), dict)
        and final_decision_label != "UNKNOWN"
    )

    # Missing and invalid data report.
    missing_data = []

    if market_status["status"] != "FRESH":
        missing_data.append(
            market_status["reason"]
            or "Market Snapshot যাচাই করা যায়নি।"
        )

    for name in REQUIRED_BTC_METRICS:

        check = btc_checks.get(name, {})

        if not check.get("valid"):
            missing_data.append(
                f"BTC {name}: {check.get('reason') or 'তথ্য যাচাই করা যায়নি।'}"
            )

    if not fear_check.get("valid"):
        missing_data.append(
            "Fear & Greed: তথ্য পাওয়া যায়নি অথবা যাচাই করা যায়নি।"
        )

    if not dominance_check.get("valid"):
        missing_data.append(
            "BTC Dominance: তথ্য পাওয়া যায়নি অথবা যাচাই করা যায়নি।"
        )

    if macro_status["status"] != "FRESH":
        missing_data.append(
            "Macro Snapshot নতুন নয় অথবা সময় যাচাই করা যায়নি।"
        )

    for name, check in macro_checks.items():
        if not check.get("valid"):
            missing_data.append(
                f"Macro {name}: {check.get('reason')}"
            )

    if advanced_status["status"] != "FRESH":
        missing_data.append(
            "Advanced Snapshot নতুন নয় অথবা সময় যাচাই করা যায়নি।"
        )

    for name, check in advanced_checks.items():
        if not check.get("valid"):
            missing_data.append(
                f"Advanced {name}: তথ্য পাওয়া যায়নি অথবা যাচাই করা যায়নি।"
            )

    if decision_status["status"] != "FRESH":
        missing_data.append(
            "Final Decision Snapshot নতুন নয় অথবা সময় যাচাই করা যায়নি।"
        )

    if final_decision_label == "UNKNOWN":
        missing_data.append(
            "Final Decision Engine-এর সিদ্ধান্ত পাওয়া যায়নি।"
        )

    # Classification.
    if not market_quality_ok:

        classification = {
            "zone": "INSUFFICIENT_DATA",
            "zone_code": "INSUFFICIENT_DATA",
            "position": "UNKNOWN",
            "bullish_score": 0,
            "bearish_score": 0,
            "confidence": 0,
            "reasons": [
                "BTC-এর প্রয়োজনীয় মূল্য ও Technical Data যাচাই হয়নি।"
            ],
        }

    else:

        classification = classify_market(
            metrics,
            fear_greed,
            dominance,
            advanced_context,
        )

    # Spot policy.
    spot = determine_spot_action(
        classification=classification,
        btc_trend=btc_trend,
        macro_risk=macro_risk,
        macro_decision=macro_decision_label,
        final_decision=final_decision_label,
        market_quality_ok=market_quality_ok,
        macro_quality_ok=macro_quality_ok,
        advanced_quality_ok=advanced_quality_ok,
        decision_quality_ok=decision_quality_ok,
    )

    # Overall quality.
    if not market_quality_ok:
        data_quality = "POOR"

    elif not (
        macro_quality_ok
        and advanced_quality_ok
        and decision_quality_ok
    ):
        data_quality = "PARTIAL"

    else:
        data_quality = "GOOD"

    # Add clear Bengali warnings.
    if macro_decision_label != "UNKNOWN" and is_macro_decision_restrictive(
        macro_decision_label
    ):
        missing_data.append(
            "সতর্কতা: Macro Engine-এর সিদ্ধান্ত নতুন BUY/DCA অনুমোদন করছে না।"
        )

    if final_decision_label != "UNKNOWN" and is_final_decision_restrictive(
        final_decision_label
    ):
        missing_data.append(
            "সতর্কতা: Final Decision Engine-এর সিদ্ধান্ত নতুন BUY/DCA সীমিত করছে।"
        )

    # Unique messages, preserving order.
    missing_data = list(dict.fromkeys(missing_data))

    result = {
        "schema_version": 3,
        "engine": "Crypto Market Zone Engine",
        "engine_version": VERSION,
        "generated_at": iso_now(),

        "data_quality": data_quality,

        "current_zone": ZONE_LABELS.get(
            classification["zone"],
            "তথ্য নেই",
        ),

        "zone_code": classification["zone_code"],

        "market_position": POSITION_LABELS.get(
            classification["position"],
            "তথ্য নেই",
        ),

        "confidence": classification["confidence"],

        "confidence_note": (
            "এটি লাভের সম্ভাবনা বা calibrated probability নয়। "
            "এটি পাওয়া তথ্য ও supporting evidence-এর coverage score।"
        ),

        "next_zone": (
            "ভবিষ্যৎ Market Zone নিশ্চিতভাবে অনুমান করা হচ্ছে না। "
            "পরবর্তী trend confirmation প্রয়োজন।"
        ),

        "spot_action": ACTION_LABELS.get(
            spot["action"],
            "অপেক্ষা করুন",
        ),

        "spot_action_code": spot["action"],

        "risk_level": RISK_LABELS.get(
            spot["risk"],
            "তথ্য নেই",
        ),

        "risk_code": spot["risk"],

        "reason": spot["reason"],
        "action_instruction": spot["instruction"],

        "btc_trend": btc_trend,
        "btc_trend_bn": TREND_LABELS.get(
            btc_trend,
            "তথ্য নেই",
        ),

        "macro_risk": {
            "score": macro_risk["score"],
            "level": macro_risk["level"],
            "reasons": macro_risk["reasons"],
            "missing": macro_risk["missing"],
        },

        "macro_decision": macro_decision_label,
        "macro_data_quality": macro_context["data_quality"],

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

            "btc_technical": {
                **btc_validation,
                "metrics": btc_checks,
            },

            "fear_greed": fear_check,
            "btc_dominance": dominance_check,

            "macro_metrics": macro_checks,
            "advanced_metrics": advanced_checks,

            "policy_checks": {
                "market_quality_ok": market_quality_ok,
                "macro_quality_ok": macro_quality_ok,
                "advanced_quality_ok": advanced_quality_ok,
                "decision_quality_ok": decision_quality_ok,
                "macro_decision_restrictive": (
                    is_macro_decision_restrictive(
                        macro_decision_label
                    )
                ),
                "final_decision_restrictive": (
                    is_final_decision_restrictive(
                        final_decision_label
                    )
                ),
            },
        },

        "limitations": [
            "এই রিপোর্ট পুরো Crypto Market-এর সামগ্রিক অবস্থা বোঝায়; কোনো নির্দিষ্ট কয়েনের BUY/SELL সংকেত নয়।",
            "Dashboard নির্দিষ্ট সময় পরপর Snapshot তৈরি করে; প্রতি Refresh-এ Provider-এর নতুন তথ্য পাওয়া নিশ্চিত নয়।",
            "Macro-এর FRED তথ্য প্রকাশের সময়সূচি অনুযায়ী বিলম্বিত হতে পারে।",
            "DTWEXBGS হলো Broad Trade-Weighted USD সূচক; এটি ICE DXY নয়।",
            "MVRV Ratio এবং MVRV Z-Score আলাদা সূচক।",
            "Fear & Greed একা BUY/SELL সিদ্ধান্ত নির্ধারণ করে না।",
            "Confidence হলো তথ্যের Coverage Score; লাভের সম্ভাবনা নয়।",
            "এই Engine কোনো কয়েনের Fundamentals, Valuation, FDV, Token Unlock বা Tokenomics যাচাই করে না।",
            "Market Zone-এ DCA-সংক্রান্ত ইতিবাচক অবস্থা দেখা গেলেও এটি স্বয়ংক্রিয় BUY অনুমোদন নয়।",
            "Spot Market Breadth শুধু উপলব্ধ Binance Spot Trading Pair-এর তথ্যের ওপর নির্ভরশীল।",
            "কোনো প্রয়োজনীয় তথ্য অনুপস্থিত, পুরোনো অথবা invalid হলে নিরাপদ সিদ্ধান্ত হিসেবে WAIT ব্যবহার করা হয়।",
        ],
    }

    return result


# ============================================================
# ENTRY POINT
# ============================================================

def main() -> int:

    try:
        result = build_market_zone()

        atomic_write_json(
            OUTPUT_FILE,
            result,
        )

        print("=" * 60)
        print("CRYPTO MARKET ZONE ENGINE")
        print("Version:", VERSION)
        print("Generated:", result["generated_at"])
        print("Data Quality:", result["data_quality"])
        print("Market Zone:", result["current_zone"])
        print("BTC Trend:", result["btc_trend_bn"])
        print("Spot Action:", result["spot_action"])
        print("Risk:", result["risk_level"])
        print("Macro Decision:", result["macro_decision"])
        print("Final Decision:", result["final_engine_decision"])
        print("Output:", OUTPUT_FILE)
        print("=" * 60)

        # Diagnostic JSON is still published when inputs are
        # incomplete. This prevents one missing source from
        # stopping the remaining dashboard workflow.
        return 0

    except Exception as exc:
        print("FATAL ERROR:", repr(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
