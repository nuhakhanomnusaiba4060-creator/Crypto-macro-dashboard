
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crypto Spot Final Decision Engine v2.2.0"""

import json
import math
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

MARKET = DATA / "market_data.json"
MACRO = DATA / "macro_data.json"
OUT = DATA / "decision_data.json"

VERSION = "2.2.0"

MAX_MARKET_H = 36
MAX_MACRO_H = 72
MAX_TECH_H = 60
FUTURE_TOLERANCE_MIN = 5


def now():
    return datetime.now(timezone.utc)


def parse_time(value):
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        d = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )

        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)

        return d.astimezone(timezone.utc)

    except (ValueError, TypeError, OverflowError):
        return None


def age_hours(value):
    d = parse_time(value)

    if d is None:
        return None

    h = (now() - d).total_seconds() / 3600

    if h < -FUTURE_TOLERANCE_MIN / 60:
        return None

    return max(0.0, h)


def snapshot(data, limit):
    ts = (
        data.get("generated_at") or data.get("fetched_at")
        if isinstance(data, dict) else None
    )

    age = age_hours(ts)

    status = (
        "MISSING" if not data
        else "INVALID" if age is None
        else "STALE" if age > limit
        else "FRESH"
    )

    return {
        "status": status,
        "age_hours": round(age, 2) if age is not None else None,
        "timestamp": ts
    }


def read(path):
    try:
        with path.open(encoding="utf-8") as f:
            x = json.load(f)

        return x if isinstance(x, dict) else {}

    except (OSError, ValueError, UnicodeError):
        return {}


def n(value):
    if isinstance(value, dict):
        if str(value.get("status", "OK")).upper() not in (
            "OK", "SUCCESS", "FRESH"
        ):
            return None

        value = value.get("value")

    if isinstance(value, bool) or value is None:
        return None

    try:
        v = float(value)
        return v if math.isfinite(v) else None

    except (ValueError, TypeError, OverflowError):
        return None


def get(data, *keys):
    x = data

    for key in keys:
        if not isinstance(x, dict):
            return None

        x = x.get(key)

    return x


def metric_fresh(obj, limit_h):
    if not isinstance(obj, dict):
        return False

    if str(obj.get("status", "")).upper() != "OK":
        return False

    ts = (
        obj.get("source_updated_at")
        or obj.get("observation_date")
        or obj.get("observed_at")
        or obj.get("as_of")
    )

    if not ts:
        return False

    age = age_hours(ts)

    return age is not None and age <= limit_h


# ============================================================
# BTC / ETH TECHNICAL ANALYSIS
# ============================================================

def analyze_asset(market, symbol):
    asset = get(market, "technical", symbol)

    if not isinstance(asset, dict):
        asset = {}

    indicators = asset.get("indicators")

    if not isinstance(indicators, dict):
        indicators = {}

    price_obj = asset.get("price_usdt")

    values = {
        "price": n(price_obj),
        "ma20": n(indicators.get("ma20")),
        "ma50": n(indicators.get("ma50")),
        "ma200": n(indicators.get("ma200")),
        "rsi": n(indicators.get("rsi14")),
        "macd": n(indicators.get("macd")),
        "macd_signal": n(indicators.get("macd_signal")),
        "adx": n(indicators.get("adx14")),
        "volume_ratio": n(indicators.get("volume_ratio_20d")),
        "support": n(indicators.get("support_20d")),
        "resistance": n(indicators.get("resistance_20d")),
        "bollinger_lower": n(indicators.get("bollinger_lower"))
    }

    required = ("price", "ma20", "ma50", "ma200", "rsi")

    missing = [
        key for key in required
        if values[key] is None
    ]

    invalid = []

    if values["price"] is not None and values["price"] <= 0:
        invalid.append("price")

    for key in ("ma20", "ma50", "ma200"):
        if values[key] is not None and values[key] <= 0:
            invalid.append(key)

    if values["rsi"] is not None:
        if not 0 <= values["rsi"] <= 100:
            invalid.append("rsi")

    core_objects = [
        price_obj,
        indicators.get("ma20"),
        indicators.get("ma50"),
        indicators.get("ma200"),
        indicators.get("rsi14")
    ]

    timestamps_valid = all(
        metric_fresh(item, MAX_TECH_H)
        for item in core_objects
    )

    quality = (
        "FRESH"
        if not missing and not invalid and timestamps_valid
        else "INCOMPLETE"
    )

    trend = "UNKNOWN"

    if quality == "FRESH":
        p = values["price"]
        m20 = values["ma20"]
        m50 = values["ma50"]
        m200 = values["ma200"]

        if p > m20 > m50 > m200:
            trend = "STRONG_BULLISH"

        elif p > m50 and m20 > m50:
            trend = "BULLISH"

        elif p < m20 < m50 < m200:
            trend = "STRONG_BEARISH"

        elif p < m50 and m20 < m50:
            trend = "BEARISH"

        else:
            trend = "NEUTRAL"

    support_warning = (
        values["price"] is not None
        and values["support"] is not None
        and values["price"] < values["support"]
    )

    return {
        "symbol": symbol,
        "quality": quality,
        "trend": trend,
        **values,
        "missing": missing + invalid,
        "last_closed_candle_at": asset.get(
            "last_closed_candle_at"
        ),
        "support_warning": support_warning
    }


# ============================================================
# MACRO ENGINE INTEGRATION
# ============================================================

def analyze_macro(macro):
    """
    Compatible with actual macro_engine.py v2 schema.

    overall_macro_decision.DATA.risk_score
    overall_macro_decision.DATA.support_score
    overall_macro_decision.DATA.risk_flags
    overall_macro_decision.DECISION
    overall_macro_decision.ANALYSIS
    overall_macro_decision.ACTION
    overall_macro_decision.RISK

    FRED metric timestamp: observation_date
    Macro snapshot timestamp: fetched_at
    """

    metrics = macro.get("metrics")

    if not isinstance(metrics, dict):
        metrics = {}

    def read_metric(*keys):
        for key in keys:
            item = metrics.get(key)

            if not isinstance(item, dict):
                continue

            if str(item.get("status", "")).upper() != "OK":
                continue

            value = n(item.get("value"))

            if value is None:
                continue

            timestamp = (
                item.get("observation_date")
                or item.get("source_updated_at")
                or item.get("observed_at")
            )

            age = age_hours(timestamp)

            if age is None or age > MAX_MACRO_H:
                continue

            return value

        return None

    vix = read_metric("vix", "VIX", "VIXCLS")

    yield_10y = read_metric(
        "yield_10y", "DGS10", "10Y"
    )

    broad_usd = read_metric(
        "usd_broad_index",
        "DTWEXBGS",
        "broad_usd",
        "usd_broad"
    )

    checks = {
        "vix": vix is not None and 0 <= vix <= 150,
        "10y": yield_10y is not None and -1 <= yield_10y <= 20,
        "broad_usd": broad_usd is not None and broad_usd > 0
    }

    overall = macro.get("overall_macro_decision")

    if not isinstance(overall, dict):
        overall = {}

    # Actual Macro Engine uses uppercase DATA and DECISION.
    decision_data = overall.get("DATA")

    if not isinstance(decision_data, dict):
        decision_data = {}

    raw_decision = (
        overall.get("DECISION")
        or overall.get("decision")
        or overall.get("label")
        or "UNKNOWN"
    )

    label = " ".join(
        str(raw_decision).upper().replace("_", " ").split()
    )

    raw_risk_score = n(
        decision_data.get("risk_score")
    )

    raw_support_score = n(
        decision_data.get("support_score")
    )

    risk_flags = decision_data.get("risk_flags")

    if not isinstance(risk_flags, list):
        risk_flags = []

    supportive_flags = decision_data.get(
        "supportive_flags"
    )

    if not isinstance(supportive_flags, list):
        supportive_flags = []

    missing_calculations = decision_data.get(
        "unavailable_calculations",
        decision_data.get("missing_metrics", [])
    )

    if not isinstance(missing_calculations, list):
        missing_calculations = []

    insufficient = (
        "INSUFFICIENT DATA" in label
        or raw_risk_score is None
        or bool(missing_calculations)
        or label == "UNKNOWN"
    )

    if all(checks.values()) and not insufficient:
        quality = "GOOD"

    elif any(checks.values()):
        quality = "PARTIAL"

    else:
        quality = "POOR"

    score = (
        max(0, int(raw_risk_score))
        if raw_risk_score is not None else 0
    )

    if quality != "GOOD":
        risk_level = "UNKNOWN"

    elif score >= 4:
        risk_level = "VERY_HIGH"

    elif score >= 3:
        risk_level = "HIGH"

    elif score >= 1:
        risk_level = "MODERATE"

    else:
        risk_level = "LOW"

    return {
        "quality": quality,
        "decision": label,
        "risk_level": risk_level,
        "risk_score": score,

        "support_score": (
            max(0, int(raw_support_score))
            if raw_support_score is not None else None
        ),

        "risk_flags": [
            str(x) for x in risk_flags
        ],

        "supportive_flags": [
            str(x) for x in supportive_flags
        ],

        "missing_calculations": [
            str(x) for x in missing_calculations
        ],

        "analysis": str(
            overall.get("ANALYSIS") or ""
        ),

        "action": str(
            overall.get("ACTION") or ""
        ),

        "risk_note": str(
            overall.get("RISK") or ""
        ),

        "vix": vix,
        "yield_10y": yield_10y,
        "broad_usd": broad_usd,
        "critical_checks": checks
    }


# ============================================================
# FINAL MARKET DECISION
# ============================================================

def build(market, macro):

    market_quality = snapshot(
        market, MAX_MARKET_H
    )

    macro_quality = snapshot(
        macro, MAX_MACRO_H
    )

    btc = analyze_asset(market, "BTC")
    eth = analyze_asset(market, "ETH")

    macro_analysis = analyze_macro(macro)

    issues = []

    if market_quality["status"] != "FRESH":
        issues.append(
            "বাজারের Snapshot অনুপস্থিত, ভুল বা পুরোনো।"
        )

    if macro_quality["status"] != "FRESH":
        issues.append(
            "Macro Snapshot অনুপস্থিত, ভুল বা পুরোনো।"
        )

    if btc["quality"] != "FRESH":
        issues.append(
            "BTC Technical Data অসম্পূর্ণ/পুরোনো: "
            + ", ".join(btc["missing"])
        )

    if eth["quality"] != "FRESH":
        issues.append(
            "ETH Technical Data অসম্পূর্ণ/পুরোনো: "
            + ", ".join(eth["missing"])
        )

    if market.get("update_mode") != "realtime":
        issues.append(
            "বাজারের ডেটা নির্দিষ্ট বিরতিতে নেওয়া Snapshot; "
            "এটি Tick-by-tick Live নয়।"
        )

    if macro_analysis["quality"] != "GOOD":
        issues.append(
            "VIX, 10Y Yield, Broad USD অথবা Macro Decision "
            "সম্পূর্ণভাবে যাচাই হয়নি।"
        )

    limitations = macro.get("limitations")

    if isinstance(limitations, list):
        issues.extend(
            str(x) for x in limitations if x
        )

    ready = (
        market_quality["status"] == "FRESH"
        and macro_quality["status"] == "FRESH"
        and btc["quality"] == "FRESH"
        and macro_analysis["quality"] == "GOOD"
    )

    reasons = []
    actions = []
    risks = []

    if not ready:

        decision = "WAIT"

        reasons.append(
            "প্রয়োজনীয় বাজার, Macro অথবা BTC Technical Data "
            "সম্পূর্ণভাবে যাচাই হয়নি।"
        )

        actions.append(
            "নতুন Spot BUY/DCA করবেন না। "
            "ডেটা ঠিক ও হালনাগাদ না হওয়া পর্যন্ত অপেক্ষা করুন।"
        )

        risks.append(
            "অসম্পূর্ণ বা পুরোনো ডেটা ভুল সিদ্ধান্ত তৈরি করতে পারে।"
        )

        if macro_analysis["missing_calculations"]:
            risks.append(
                "Macro-এর অসম্পূর্ণ হিসাব: "
                + ", ".join(
                    macro_analysis["missing_calculations"]
                )
            )

    else:

        btc_bearish = btc["trend"] in (
            "BEARISH", "STRONG_BEARISH"
        )

        btc_bullish = btc["trend"] in (
            "BULLISH", "STRONG_BULLISH"
        )

        eth_bearish = (
            eth["quality"] != "FRESH"
            or eth["trend"] in (
                "BEARISH", "STRONG_BEARISH"
            )
        )

        macro_risk = (
            macro_analysis["risk_score"] >= 3
            or macro_analysis["decision"].startswith(
                "REDUCE RISK"
            )
        )

        if btc_bearish and macro_risk:

            decision = "REDUCE RISK"

            reasons.append(
                "BTC-এর Daily Trend দুর্বল এবং Macro ঝুঁকি বেশি।"
            )

            reasons.extend(
                macro_analysis["risk_flags"]
            )

            actions.append(
                "নতুন Altcoin exposure বাড়াবেন না। "
                "দুর্বল ও অতিরিক্ত ঝুঁকিপূর্ণ Spot position পর্যালোচনা করুন।"
            )

            risks.append(
                "বাজারে বড় পতনের ঝুঁকি বেড়েছে; "
                "এটি সব Coin বিক্রির নির্দেশ নয়।"
            )

        elif btc_bearish:

            decision = "WAIT"

            reasons.append(
                "BTC-এর Daily Trend Bearish।"
            )

            actions.append(
                "নতুন Spot BUY/DCA বন্ধ রাখুন; "
                "Trend উন্নতির নিশ্চিত সংকেতের অপেক্ষা করুন।"
            )

        elif macro_risk:

            decision = "REDUCE RISK"

            reasons.append(
                "Macro Engine-এর পূর্ণাঙ্গ Multi-Factor Risk Score উচ্চ।"
            )

            reasons.extend(
                macro_analysis["risk_flags"]
            )

            actions.append(
                "নতুন exposure বাড়াবেন না; "
                "Portfolio concentration ও দুর্বল Coin পর্যালোচনা করুন।"
            )

        elif (
            btc_bullish
            and not eth_bearish
            and macro_analysis["decision"] not in (
                "WAIT",
                "WAIT INSUFFICIENT DATA"
            )
        ):

            decision = "HOLD"

            reasons.append(
                "BTC Trend Bullish এবং Macro ঝুঁকি তুলনামূলক নিয়ন্ত্রণে।"
            )

            actions.append(
                "বিদ্যমান Spot position ধরে রাখুন। "
                "নতুন Coin কেনার আগে Fundamentals, Valuation ও Tokenomics যাচাই করুন।"
            )

        else:

            decision = "WAIT"

            reasons.append(
                "BTC/ETH-এর সংকেত একই দিকে নেই অথবা Trend নিশ্চিত নয়।"
            )

            actions.append(
                "নতুন Spot position না নিয়ে BTC ও ETH-এর "
                "Trend confirmation-এর অপেক্ষা করুন।"
            )

        if btc["rsi"] is not None and btc["rsi"] >= 70:
            risks.append(
                "BTC RSI 70 বা বেশি; অতিরিক্ত দামে Entry ঝুঁকিপূর্ণ।"
            )

        if eth["quality"] != "FRESH":
            risks.append(
                "ETH Technical Data যাচাই হয়নি; ETH confirmation দুর্বল।"
            )

        risks.extend(
            macro_analysis["risk_flags"]
        )

        if macro_analysis["decision"] == "WAIT":
            risks.append(
                "Macro Engine-এর সিদ্ধান্ত WAIT; "
                "Macro confirmation এখনো যথেষ্ট নয়।"
            )

        if btc["support_warning"]:
            risks.append(
                "BTC মূল্য Support reference-এর নিচে; "
                "Daily Candle Close দিয়ে ভাঙন নিশ্চিত করতে হবে।"
            )

    return {

        "engine": "CRYPTO FINAL DECISION ENGINE",
        "version": VERSION,
        "generated_at": now().isoformat(),

        "data_quality": {
            "status": "GOOD" if ready else "PARTIAL",
            "market_snapshot": market_quality,
            "macro_snapshot": macro_quality,
            "btc_technical": btc["quality"],
            "eth_technical": eth["quality"],
            "issues": list(dict.fromkeys(issues))
        },

        "macro_analysis": macro_analysis,

        "crypto_market": {
            "global_market": market.get(
                "global_market", {}
            ),
            "fear_greed": market.get(
                "fear_greed", {}
            ),
            "btc": btc,
            "eth": eth
        },

        "final_decision": {

            "decision": decision,
            "market_status": decision,
            "reasons": reasons,
            "actions": actions,
            "risk": risks,
            "data_ready": ready,

            "decision_scope": "BROAD_CRYPTO_MARKET_SPOT",
            "not_coin_specific": True
        },

        "limitations": [
            "এটি সামগ্রিক Crypto Spot Market ঝুঁকি বিশ্লেষণ; "
            "নির্দিষ্ট Coin-এর BUY/SELL নির্দেশ নয়।",

            "Scheduled Snapshot সম্পূর্ণ Real-time নয়।",

            "FRED Macro তথ্য প্রকাশে বিলম্ব হয়।",

            "শুধু RSI বা Support warning দিয়ে SELL সিদ্ধান্ত দেওয়া হয় না।",

            "Futures/Margin সংকেত তৈরি করা হয় না।",

            "Macro Risk Score একটি rule-based score; "
            "এটি calibrated probability নয়।"
        ]
    }


# ============================================================
# ATOMIC JSON WRITER
# ============================================================

def write(path, data):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent),
        suffix=".tmp"
    )

    try:

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2,
                allow_nan=False
            )

            f.write("\n")

        os.replace(tmp, path)

    finally:

        if os.path.exists(tmp):
            os.remove(tmp)


# ============================================================
# MAIN
# ============================================================

def main():

    output = build(
        read(MARKET),
        read(MACRO)
    )

    write(
        OUT,
        output
    )

    print("=" * 55)
    print("CRYPTO FINAL DECISION ENGINE")
    print("Version:", VERSION)

    print(
        "Decision:",
        output["final_decision"]["decision"]
    )

    print(
        "Data Quality:",
        output["data_quality"]["status"]
    )

    print(
        "BTC Trend:",
        output["crypto_market"]["btc"]["trend"]
    )

    print(
        "Macro Decision:",
        output["macro_analysis"]["decision"]
    )

    print(
        "Macro Risk Score:",
        output["macro_analysis"]["risk_score"]
    )

    print(
        "Macro Quality:",
        output["macro_analysis"]["quality"]
    )

    print(
        "Output:",
        OUT
    )

    print("=" * 55)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
