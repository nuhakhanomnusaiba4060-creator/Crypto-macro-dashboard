
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CRYPTO MACRO DASHBOARD - MACRO ENGINE
Version: 1.1

Output: data/macro_data.json

Source: Federal Reserve Economic Data (FRED)

IMPORTANT:
DTWEXBGS = Broad USD Index Proxy, NOT ICE DXY.
Gold FRED series disabled after HTTP 404.
No fake values or synthetic defaults.
"""

import csv
import io
import json
import logging
import math
import os
import sys
import tempfile
import time

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# ============================================================
# CONFIGURATION
# ============================================================

VERSION = "1.1"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "macro_data.json"

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"

FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()

TIMEOUT = 20
RETRIES = 2
MAX_WORKERS = 8

USER_AGENT = "CryptoMacroDashboard/1.1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

LOGGER = logging.getLogger("macro_engine")


# ============================================================
# FRED SERIES
# ============================================================

# Freshness limits are series-specific.
# Monthly observation dates differ from publication dates.

SERIES = {
    "fed_funds_rate": {
        "id": "DFF",
        "name": "Federal Funds Effective Rate",
        "unit": "%",
        "freshness_days": 7
    },
    "cpi": {
        "id": "CPIAUCSL",
        "name": "Consumer Price Index",
        "unit": "index",
        "freshness_days": 75
    },
    "core_cpi": {
        "id": "CPILFESL",
        "name": "Core CPI",
        "unit": "index",
        "freshness_days": 75
    },
    "pce": {
        "id": "PCEPI",
        "name": "PCE Price Index",
        "unit": "index",
        "freshness_days": 100
    },
    "core_pce": {
        "id": "PCEPILFE",
        "name": "Core PCE Price Index",
        "unit": "index",
        "freshness_days": 100
    },
    "unemployment": {
        "id": "UNRATE",
        "name": "Unemployment Rate",
        "unit": "%",
        "freshness_days": 75
    },
    "nonfarm_payrolls": {
        "id": "PAYEMS",
        "name": "Total Nonfarm Payrolls",
        "unit": "thousands",
        "freshness_days": 75
    },
    "yield_2y": {
        "id": "DGS2",
        "name": "US 2-Year Treasury Yield",
        "unit": "%",
        "freshness_days": 7
    },
    "yield_10y": {
        "id": "DGS10",
        "name": "US 10-Year Treasury Yield",
        "unit": "%",
        "freshness_days": 7
    },
    "yield_30y": {
        "id": "DGS30",
        "name": "US 30-Year Treasury Yield",
        "unit": "%",
        "freshness_days": 7
    },
    "yield_curve_10y_2y": {
        "id": "T10Y2Y",
        "name": "10Y-2Y Treasury Spread",
        "unit": "percentage_points",
        "freshness_days": 7
    },
    "usd_broad_index": {
        "id": "DTWEXBGS",
        "name": "Trade Weighted US Dollar Index",
        "unit": "index",
        "freshness_days": 10
    },
    "vix": {
        "id": "VIXCLS",
        "name": "CBOE Volatility Index",
        "unit": "index",
        "freshness_days": 7
    },
    "sp500": {
        "id": "SP500",
        "name": "S&P 500",
        "unit": "index",
        "freshness_days": 7
    },
    "nasdaq": {
        "id": "NASDAQCOM",
        "name": "NASDAQ Composite",
        "unit": "index",
        "freshness_days": 7
    },
    "oil": {
        "id": "DCOILWTICO",
        "name": "WTI Crude Oil",
        "unit": "USD/barrel",
        "freshness_days": 10
    },
    "usd_jpy": {
        "id": "DEXJPUS",
        "name": "Japanese Yen per US Dollar",
        "unit": "JPY/USD",
        "freshness_days": 10
    },
    "fed_balance_sheet": {
        "id": "WALCL",
        "name": "Federal Reserve Total Assets",
        "unit": "millions USD",
        "freshness_days": 21
    },
    "reverse_repo": {
        "id": "RRPONTSYD",
        "name": "Overnight Reverse Repurchase Agreements",
        "unit": "billions USD",
        "freshness_days": 7
    },
    "treasury_general_account": {
        "id": "WTREGEN",
        "name": "Treasury General Account",
        "unit": "millions USD",
        "freshness_days": 21
    },
    "m2_money_supply": {
        "id": "M2SL",
        "name": "M2 Money Supply",
        "unit": "billions USD",
        "freshness_days": 100
    }
}


# Gold is intentionally disabled.
# Previous FRED request returned HTTP 404.

DISABLED_SERIES = {
    "gold": {
        "name": "Gold Price",
        "unit": "USD/oz",
        "source": "FRED GOLDAMGBD228NLBM (disabled)",
        "reason": (
            "FRED endpoint returned HTTP 404. "
            "No verified replacement price source is configured."
        )
    }
}


# ============================================================
# TIME AND NUMBER HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def parse_date(value):
    try:
        return datetime.strptime(
            value, "%Y-%m-%d"
        ).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def safe_number(value):
    try:
        number = float(value)

        if not math.isfinite(number):
            return None

        return number

    except (ValueError, TypeError):
        return None


def round_value(value, digits=4):
    if value is None:
        return None

    return round(value, digits)


def percentage_change(current, previous):
    if current is None or previous is None or previous == 0:
        return None

    return (
        (current - previous) / abs(previous)
    ) * 100


# ============================================================
# HTTP CLIENT
# ============================================================

def http_get(url):
    last_error = None

    for attempt in range(RETRIES + 1):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/csv, application/json"
                }
            )

            with urlopen(
                request,
                timeout=TIMEOUT
            ) as response:

                return response.read().decode("utf-8-sig")

        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError
        ) as exc:

            last_error = str(exc)

            if attempt < RETRIES:
                time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(
        last_error or "HTTP request failed"
    )


# ============================================================
# FRED DATA FETCH
# ============================================================

def fetch_fred_csv(series_id):
    params = urlencode({"id": series_id})

    url = f"{FRED_CSV_URL}?{params}"

    raw = http_get(url)

    reader = csv.DictReader(
        io.StringIO(raw)
    )

    observations = []

    for row in reader:

        date_text = (
            row.get("observation_date")
            or row.get("DATE")
            or row.get("date")
        )

        value_text = (
            row.get(series_id)
            or row.get("value")
            or row.get("VALUE")
        )

        if not date_text:
            continue

        if parse_date(date_text) is None:
            continue

        value = safe_number(value_text)

        if value is None:
            continue

        observations.append({
            "date": date_text,
            "value": value
        })

    observations.sort(
        key=lambda item: item["date"]
    )

    return observations


def fetch_fred_api(series_id):
    params = urlencode({
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "asc"
    })

    url = f"{FRED_API_URL}?{params}"

    payload = json.loads(http_get(url))

    observations = []

    for item in payload.get("observations", []):

        date_text = item.get("date")
        value = safe_number(item.get("value"))

        if not date_text:
            continue

        if parse_date(date_text) is None:
            continue

        if value is None:
            continue

        observations.append({
            "date": date_text,
            "value": value
        })

    observations.sort(
        key=lambda item: item["date"]
    )

    return observations


def fetch_series(series_id):

    if FRED_API_KEY:

        try:
            return (
                fetch_fred_api(series_id),
                "FRED_API"
            )

        except Exception as exc:

            LOGGER.warning(
                "%s API failed; trying CSV: %s",
                series_id,
                exc
            )

    return (
        fetch_fred_csv(series_id),
        "FRED_CSV_EXPORT"
    )


# ============================================================
# FRESHNESS AND METRIC PROCESSING
# ============================================================

def classify_freshness(observation_date, config):

    observed = parse_date(observation_date)

    if observed is None:
        return "UNAVAILABLE"

    age_days = (
        utc_now() - observed
    ).total_seconds() / 86400

    limit = config.get("freshness_days", 7)

    if age_days > limit:
        return "STALE"

    return "OK"


def build_metric(key, config, observations, source):

    fetched_at = iso_now()

    if not observations:

        return {
            "key": key,
            "name": config["name"],
            "value": None,
            "unit": config["unit"],
            "observation_date": None,
            "previous_value": None,
            "previous_date": None,
            "change": None,
            "change_percent": None,
            "source": source,
            "fetched_at": fetched_at,
            "status": "UNAVAILABLE",
            "error": "No valid observations returned."
        }

    observations.sort(
        key=lambda item: item["date"]
    )

    current = observations[-1]

    previous = (
        observations[-2]
        if len(observations) >= 2
        else None
    )

    change = None
    change_percent = None

    if previous:

        change = (
            current["value"] - previous["value"]
        )

        change_percent = percentage_change(
            current["value"],
            previous["value"]
        )

    status = classify_freshness(
        current["date"],
        config
    )

    return {
        "key": key,
        "name": config["name"],
        "value": round_value(current["value"]),
        "unit": config["unit"],
        "observation_date": current["date"],
        "previous_value": (
            round_value(previous["value"])
            if previous else None
        ),
        "previous_date": (
            previous["date"]
            if previous else None
        ),
        "change": round_value(change),
        "change_percent": round_value(
            change_percent
        ),
        "source": source,
        "fetched_at": fetched_at,
        "status": status,
        "error": (
            None
            if status == "OK"
            else "Latest observation is older than freshness limit."
        )
    }


# ============================================================
# INFLATION AND PAYROLL CALCULATIONS
# ============================================================

def historical_change(observations, periods):

    if len(observations) <= periods:
        return None

    current = observations[-1]["value"]

    previous = observations[
        -1 - periods
    ]["value"]

    return round_value(
        percentage_change(current, previous),
        3
    )


def calculate_payroll_change(observations):

    if len(observations) < 2:
        return None

    return round_value(
        observations[-1]["value"]
        - observations[-2]["value"],
        1
    )


def build_inflation_report(metrics, observations_by_key):

    labels = {
        "cpi": "CPI",
        "core_cpi": "Core CPI",
        "pce": "PCE",
        "core_pce": "Core PCE"
    }

    result = {}

    for key, label in labels.items():

        metric = metrics.get(key, {})

        observations = observations_by_key.get(
            key, []
        )

        if metric.get("status") != "OK":

            result[key] = {
                "name": label,
                "mom_percent": None,
                "yoy_percent": None,
                "status": metric.get(
                    "status",
                    "UNAVAILABLE"
                )
            }

        else:

            result[key] = {
                "name": label,
                "mom_percent": historical_change(
                    observations, 1
                ),
                "yoy_percent": historical_change(
                    observations, 12
                ),
                "status": "OK"
            }

    return result


# ============================================================
# REPORT FORMAT
# ============================================================

def make_report(
    data,
    analysis,
    decision,
    action,
    risk
):

    return {
        "DATA": data,
        "ANALYSIS": analysis,
        "DECISION": decision,
        "ACTION": action,
        "RISK": risk
    }


def metric_value(metrics, key):

    item = metrics.get(key, {})

    if item.get("status") != "OK":
        return None

    return item.get("value")


# ============================================================
# INDICATOR REPORT ENGINE
# ============================================================

def build_indicator_reports(metrics, inflation):

    reports = {}

    # --------------------------------------------------------
    # CPI, CORE CPI, PCE, CORE PCE
    # --------------------------------------------------------

    inflation_rules = [
        ("cpi", "CPI", 4.0, 3.0),
        ("core_cpi", "Core CPI", 4.0, 3.0),
        ("pce", "PCE", 3.0, 2.0),
        ("core_pce", "Core PCE", 3.0, 2.0)
    ]

    for key, label, high_level, caution_level in inflation_rules:

        item = inflation.get(key, {})

        yoy = item.get("yoy_percent")
        mom = item.get("mom_percent")

        if item.get("status") != "OK" or yoy is None:

            reports[key] = make_report(
                None,
                f"{label} data unavailable or stale.",
                "WAIT — INSUFFICIENT DATA",
                f"{label} data যাচাই না হওয়া পর্যন্ত সিদ্ধান্ত স্থগিত রাখুন।",
                "প্রকাশিত observation ও freshness যাচাই প্রয়োজন।"
            )

        elif yoy >= high_level:

            reports[key] = make_report(
                {
                    "yoy_percent": yoy,
                    "mom_percent": mom
                },
                f"{label} YoY উচ্চ পর্যায়ে রয়েছে।",
                "REDUCE RISK",
                f"{label} inflation বেশি—ঝুঁকিপূর্ণ Altcoin exposure কমান।",
                "একটি inflation reading দিয়ে Fed-এর পরবর্তী সিদ্ধান্ত নিশ্চিত হয় না।"
            )

        elif yoy >= caution_level:

            reports[key] = make_report(
                {
                    "yoy_percent": yoy,
                    "mom_percent": mom
                },
                f"{label} এখনো সতর্কতার পর্যায়ে রয়েছে।",
                "WAIT",
                "নতুন ঝুঁকিপূর্ণ BUY সীমিত রাখুন এবং পরবর্তী inflation release পর্যবেক্ষণ করুন।",
                "YoY একা inflation momentum পুরোপুরি দেখায় না; MoM-ও গুরুত্বপূর্ণ।"
            )

        else:

            reports[key] = make_report(
                {
                    "yoy_percent": yoy,
                    "mom_percent": mom
                },
                f"{label} YoY তুলনামূলকভাবে নিয়ন্ত্রিত।",
                "HOLD / SELECTIVE",
                "Inflation trend-কে Fed policy, yields ও BTC trend-এর সঙ্গে মিলিয়ে দেখুন।",
                "কম inflation একাই Crypto bullish signal নয়।"
            )

    # --------------------------------------------------------
    # FED RATE
    # --------------------------------------------------------

    fed = metric_value(
        metrics,
        "fed_funds_rate"
    )

    reports["fed_rate"] = make_report(
        {
            "effective_rate_percent": fed
        } if fed is not None else None,

        (
            "সর্বশেষ effective Fed funds rate পাওয়া গেছে।"
            if fed is not None
            else "Fed rate unavailable or stale."
        ),

        (
            "HOLD / SELECTIVE"
            if fed is not None
            else "WAIT — INSUFFICIENT DATA"
        ),

        (
            "Fed rate-কে CPI, PCE, employment ও Treasury yield-এর সঙ্গে বিশ্লেষণ করুন।"
            if fed is not None
            else "Fed policy-ভিত্তিক সিদ্ধান্ত স্থগিত রাখুন।"
        ),

        "Effective rate একা FOMC-এর পরবর্তী সিদ্ধান্ত জানায় না।"
    )

    # --------------------------------------------------------
    # LABOR MARKET
    # --------------------------------------------------------

    unemployment = metric_value(
        metrics,
        "unemployment"
    )

    payroll_change = metrics.get(
        "nonfarm_payrolls", {}
    ).get("monthly_change_thousands")

    if unemployment is None or payroll_change is None:

        reports["labor_market"] = make_report(
            None,
            "Labor market data incomplete.",
            "WAIT — INSUFFICIENT DATA",
            "NFP ও Unemployment উভয় ডেটা fresh না হওয়া পর্যন্ত সিদ্ধান্ত স্থগিত রাখুন।",
            "অসম্পূর্ণ employment data থেকে recession signal নিশ্চিত করা যাবে না।"
        )

    elif unemployment >= 5.0 or payroll_change < 0:

        reports["labor_market"] = make_report(
            {
                "unemployment_percent": unemployment,
                "nfp_monthly_change_thousands": payroll_change
            },
            "Employment deterioration দেখা যাচ্ছে।",
            "REDUCE RISK",
            "Labor market দুর্বল—ঝুঁকিপূর্ণ Altcoin exposure কমান।",
            "একটি মাসের NFP revision ও participation rate-ও গুরুত্বপূর্ণ।"
        )

    elif unemployment >= 4.5:

        reports["labor_market"] = make_report(
            {
                "unemployment_percent": unemployment,
                "nfp_monthly_change_thousands": payroll_change
            },
            "Labor market দুর্বল হওয়ার লক্ষণ রয়েছে।",
            "WAIT",
            "নতুন BUY সীমিত রাখুন এবং পরবর্তী employment release পর্যবেক্ষণ করুন।",
            "Unemployment একা recession নিশ্চিত করে না।"
        )

    else:

        reports["labor_market"] = make_report(
            {
                "unemployment_percent": unemployment,
                "nfp_monthly_change_thousands": payroll_change
            },
            "Labor market তুলনামূলকভাবে স্থিতিশীল।",
            "HOLD / SELECTIVE",
            "Employment trend ও wage inflation একসঙ্গে পর্যবেক্ষণ করুন।",
            "শক্তিশালী employment inflation pressure বজায় রাখতে পারে।"
        )

    # --------------------------------------------------------
    # TREASURY YIELDS
    # --------------------------------------------------------

    y10 = metrics.get("yield_10y", {})

    y10_change = y10.get("change")

    if y10.get("status") != "OK" or y10_change is None:

        reports["bond_yields"] = make_report(
            None,
            "Treasury yield data unavailable or stale.",
            "WAIT — INSUFFICIENT DATA",
            "Fresh yield data না পাওয়া পর্যন্ত সিদ্ধান্ত স্থগিত রাখুন।",
            "Yield-এর daily movement অনুপস্থিত।"
        )

    else:

        yield_data = {
            "2y": metric_value(metrics, "yield_2y"),
            "10y": metric_value(metrics, "yield_10y"),
            "30y": metric_value(metrics, "yield_30y"),
            "10y_daily_change_pp": y10_change
        }

        if y10_change >= 0.05:

            reports["bond_yields"] = make_report(
                yield_data,
                "10Y Treasury yield সর্বশেষ observation-এ বেড়েছে।",
                "REDUCE RISK",
                "10Y yield বাড়ছে—ঝুঁকিপূর্ণ Altcoin exposure কমান।",
                "Yield বৃদ্ধি inflation বা Treasury supply concern—দুই কারণেই হতে পারে।"
            )

        elif y10_change <= -0.05:

            reports["bond_yields"] = make_report(
                yield_data,
                "10Y Treasury yield সর্বশেষ observation-এ কমেছে।",
                "HOLD / SELECTIVE",
                "Yield decline-কে BTC ও equity trend-এর সঙ্গে যাচাই করুন।",
                "Yield পতন growth concern থেকেও হতে পারে।"
            )

        else:

            reports["bond_yields"] = make_report(
                yield_data,
                "10Y yield-এ বড় দৈনিক পরিবর্তন নেই।",
                "WAIT",
                "Treasury yield trend পর্যবেক্ষণ করুন।",
                "এক দিনের পরিবর্তন দীর্ঘমেয়াদি yield trend নয়।"
            )

    # --------------------------------------------------------
    # BROAD USD INDEX PROXY
    # --------------------------------------------------------

    usd = metrics.get("usd_broad_index", {})

    usd_change = usd.get("change_percent")

    if usd.get("status") != "OK" or usd_change is None:

        reports["usd_index"] = make_report(
            None,
            "Broad USD index data unavailable or stale.",
            "WAIT — INSUFFICIENT DATA",
            "USD trend যাচাই না হওয়া পর্যন্ত macro সিদ্ধান্ত স্থগিত রাখুন।",
            "DTWEXBGS হলো broad dollar proxy, ICE DXY নয়।"
        )

    elif usd_change >= 0.30:

        reports["usd_index"] = make_report(
            {"daily_change_percent": usd_change},
            "Broad USD index সর্বশেষ observation-এ বেড়েছে।",
            "REDUCE RISK",
            "Dollar strength বাড়ছে—ঝুঁকিপূর্ণ Altcoin exposure কমান।",
            "এটি ICE DXY নয়; broad trade-weighted USD index।"
        )

    elif usd_change <= -0.30:

        reports["usd_index"] = make_report(
            {"daily_change_percent": usd_change},
            "Broad USD index সর্বশেষ observation-এ কমেছে।",
            "HOLD / SELECTIVE",
            "USD দুর্বলতা BTC ও Altcoin trend-এর সঙ্গে যাচাই করুন।",
            "USD দুর্বল হলেই Crypto bullish হয় না।"
        )

    else:

        reports["usd_index"] = make_report(
            {"daily_change_percent": usd_change},
            "Broad USD index-এ বড় দৈনিক পরিবর্তন নেই।",
            "WAIT",
            "USD trend পর্যবেক্ষণ করুন।",
            "এটি ICE DXY নয়; broad trade-weighted USD index।"
        )

    # --------------------------------------------------------
    # VIX
    # --------------------------------------------------------

    vix = metric_value(metrics, "vix")

    if vix is None:

        reports["vix"] = make_report(
            None,
            "VIX data unavailable or stale.",
            "WAIT — INSUFFICIENT DATA",
            "Volatility data না পাওয়া পর্যন্ত risk assessment সীমিত রাখুন।",
            "বর্তমান VIX যাচাই করা যাচ্ছে না।"
        )

    elif vix >= 30:

        reports["vix"] = make_report(
            {"value": vix},
            "VIX অত্যন্ত উচ্চ।",
            "REDUCE RISK",
            "VIX অত্যন্ত উচ্চ—Crypto risk exposure কমান।",
            "VIX equity volatility মাপে; Crypto volatility সরাসরি মাপে না।"
        )

    elif vix >= 25:

        reports["vix"] = make_report(
            {"value": vix},
            "VIX উচ্চ।",
            "REDUCE RISK",
            "VIX বাড়তি ঝুঁকি দেখাচ্ছে—নতুন ঝুঁকিপূর্ণ BUY বন্ধ রাখুন।",
            "VIX equity volatility মাপে; Crypto volatility সরাসরি মাপে না।"
        )

    elif vix >= 18:

        reports["vix"] = make_report(
            {"value": vix},
            "VIX elevated range-এ রয়েছে।",
            "WAIT",
            "নতুন BUY-তে সতর্ক থাকুন।",
            "VIX একা Crypto market direction নির্ধারণ করে না।"
        )

    else:

        reports["vix"] = make_report(
            {"value": vix},
            "VIX তুলনামূলক কম।",
            "HOLD / SELECTIVE",
            "কম VIX-কে একমাত্র BUY signal হিসেবে ব্যবহার করবেন না।",
            "কম VIX থাকা সত্ত্বেও Crypto-specific risk থাকতে পারে।"
        )

    # --------------------------------------------------------
    # EQUITY MARKET
    # --------------------------------------------------------

    sp = metric_value(metrics, "sp500")
    nq = metric_value(metrics, "nasdaq")

    equity_data = {
        "sp500": sp,
        "nasdaq": nq
    }

    equity_missing = [
        key for key, value in equity_data.items()
        if value is None
    ]

    reports["equity_market"] = make_report(
        equity_data if not equity_missing else None,

        (
            "S&P 500 ও Nasdaq-এর latest observations পাওয়া গেছে।"
            if not equity_missing
            else "Equity index data incomplete."
        ),

        (
            "HOLD / SELECTIVE"
            if not equity_missing
            else "WAIT — INSUFFICIENT DATA"
        ),

        (
            "Equity trend-কে VIX, yields ও BTC trend-এর সঙ্গে মিলিয়ে দেখুন।"
            if not equity_missing
            else "Equity data সম্পূর্ণ না হওয়া পর্যন্ত সিদ্ধান্ত স্থগিত রাখুন।"
        ),

        "Closing index value একা market trend নিশ্চিত করে না।"
    )

    # --------------------------------------------------------
    # OIL AND GOLD
    # --------------------------------------------------------

    oil = metric_value(metrics, "oil")

    gold = metrics.get("gold", {})

    reports["commodities"] = make_report(
        {
            "wti_oil_usd_per_barrel": oil,
            "gold_usd_per_oz": None,
            "gold_status": gold.get("status", "UNAVAILABLE"),
            "gold_note": gold.get("error")
        },

        (
            "WTI oil data পাওয়া গেছে; Gold price source unavailable."
            if oil is not None
            else "Commodity data incomplete; Gold source unavailable."
        ),

        (
            "HOLD / SELECTIVE"
            if oil is not None
            else "WAIT — INSUFFICIENT DATA"
        ),

        "Oil-এর inflation impact পর্যবেক্ষণ করুন; Gold-এর জন্য verified replacement source প্রয়োজন।",

        "Gold-এর কোনো কৃত্রিম বা পুরোনো মান ব্যবহার করা হচ্ছে না।"
    )

    # --------------------------------------------------------
    # YEN
    # --------------------------------------------------------

    yen = metric_value(metrics, "usd_jpy")

    reports["yen"] = make_report(
        {"jpy_per_usd": yen} if yen is not None else None,

        (
            "USD/JPY latest observation পাওয়া গেছে।"
            if yen is not None
            else "USD/JPY data unavailable or stale."
        ),

        "WAIT" if yen is not None else "WAIT — INSUFFICIENT DATA",

        (
            "Yen movement-এর সঙ্গে BOJ policy ও Japanese bond yield পর্যবেক্ষণ করুন।"
            if yen is not None
            else "Yen-related macro সিদ্ধান্ত স্থগিত রাখুন।"
        ),

        "শুধু USD/JPY দিয়ে carry-trade unwind নিশ্চিত করা যায় না; JGB yield curve এখনো যুক্ত হয়নি।"
    )

    # --------------------------------------------------------
    # US LIQUIDITY
    # --------------------------------------------------------

    liquidity_keys = (
        "fed_balance_sheet",
        "reverse_repo",
        "treasury_general_account",
        "m2_money_supply"
    )

    liquidity_data = {
        key: metric_value(metrics, key)
        for key in liquidity_keys
    }

    missing = [
        key for key, value in liquidity_data.items()
        if value is None
    ]

    reports["liquidity"] = make_report(
        liquidity_data,

        (
            "US liquidity series incomplete."
            if missing
            else "Fed assets, RRP, TGA ও M2-এর latest observations পাওয়া গেছে।"
        ),

        (
            "WAIT — INSUFFICIENT DATA"
            if missing
            else "HOLD / SELECTIVE"
        ),

        "সব series-এর change একত্রে বিশ্লেষণ করুন; একটি metric দিয়ে liquidity সিদ্ধান্ত নেবেন না।",

        "এটি পূর্ণ global liquidity composite নয়; M2-এর প্রকাশ-ল্যাগও বিবেচনা করতে হবে।"
    )

    return reports


# ============================================================
# OVERALL MACRO DECISION
# ============================================================

def build_overall_decision(metrics):

    required = (
        "usd_broad_index",
        "vix",
        "yield_10y"
    )

    missing = [
        key for key in required
        if metrics.get(key, {}).get("status") != "OK"
    ]

    if missing:

        return {
            "DATA": {
                "required_metrics": list(required),
                "missing_metrics": missing
            },
            "ANALYSIS": "প্রয়োজনীয় Macro data incomplete বা stale.",
            "DECISION": "WAIT — INSUFFICIENT DATA",
            "ACTION": "Fresh macro data না পাওয়া পর্যন্ত risk-on/risk-off সিদ্ধান্ত নেবেন না।",
            "RISK": "অসম্পূর্ণ data থেকে ভুল market assessment হতে পারে।"
        }

    usd = metrics["usd_broad_index"]
    vix = metrics["vix"]
    y10 = metrics["yield_10y"]

    usd_change = usd.get("change_percent")
    vix_value = vix.get("value")
    y10_change = y10.get("change")

    if (
        usd_change is None
        or vix_value is None
        or y10_change is None
    ):

        return {
            "DATA": None,
            "ANALYSIS": "প্রয়োজনীয় পরিবর্তনের হিসাব অনুপস্থিত।",
            "DECISION": "WAIT — INSUFFICIENT DATA",
            "ACTION": "নির্ভরযোগ্য change data সংগ্রহ করুন।",
            "RISK": "শুধু level দিয়ে macro direction নির্ধারণ করা যাচ্ছে না।"
        }

    risk_flags = []
    supportive_flags = []

    if usd_change >= 0.30:
        risk_flags.append(
            "Broad USD index daily change >= +0.30%"
        )

    elif usd_change <= -0.30:
        supportive_flags.append(
            "Broad USD index daily change <= -0.30%"
        )

    if vix_value >= 25:
        risk_flags.append("VIX >= 25")

    elif vix_value < 18:
        supportive_flags.append("VIX < 18")

    if y10_change >= 0.05:
        risk_flags.append(
            "10Y yield daily change >= +0.05 percentage points"
        )

    elif y10_change <= -0.05:
        supportive_flags.append(
            "10Y yield daily change <= -0.05 percentage points"
        )

    if len(risk_flags) >= 2:

        decision = "REDUCE RISK"

        analysis = (
            "একাধিক Macro risk indicator একই সময়ে চাপ তৈরি করছে।"
        )

        action = (
            "Macro risk elevated—ঝুঁকিপূর্ণ Altcoin exposure কমান "
            "এবং নতুন BUY সীমিত রাখুন।"
        )

        risk = (
            "BTC trend, ETF flows ও crypto liquidity-ও যাচাই করা প্রয়োজন।"
        )

    elif len(supportive_flags) >= 2 and not risk_flags:

        decision = "HOLD / SELECTIVE"

        analysis = (
            "একাধিক Macro indicator তুলনামূলক supportive."
        )

        action = (
            "Macro পরিবেশ তুলনামূলক সহায়ক; তবু BTC trend ও "
            "market breadth ছাড়া aggressive BUY নয়।"
        )

        risk = (
            "Macro support নিশ্চিত Bull market signal নয়।"
        )

    else:

        decision = "WAIT"

        analysis = (
            "Macro signal মিশ্র বা একমুখী নয়।"
        )

        action = (
            "নতুন বড় risk exposure নেবেন না; "
            "BTC ও পরবর্তী macro release পর্যবেক্ষণ করুন।"
        )

        risk = (
            "এই assessment intraday price বা BTC technical trend-এর বিকল্প নয়।"
        )

    return {
        "DATA": {
            "broad_usd_daily_change_percent": usd_change,
            "vix": vix_value,
            "10y_yield_daily_change_percentage_points": y10_change,
            "risk_flags": risk_flags,
            "supportive_flags": supportive_flags
        },
        "ANALYSIS": analysis,
        "DECISION": decision,
        "ACTION": action,
        "RISK": risk
    }


# ============================================================
# FETCH ALL SERIES
# ============================================================

def fetch_worker(key, config):

    observations, source = fetch_series(
        config["id"]
    )

    metric = build_metric(
        key,
        config,
        observations,
        source
    )

    return key, metric, observations


def fetch_all_series():

    metrics = {}
    observations_by_key = {}

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {
            executor.submit(
                fetch_worker,
                key,
                config
            ): key

            for key, config in SERIES.items()
        }

        for future in as_completed(futures):

            key = futures[future]

            try:

                result_key, metric, observations = (
                    future.result()
                )

                metrics[result_key] = metric

                observations_by_key[result_key] = (
                    observations
                )

                LOGGER.info(
                    "%s | %s | %s",
                    result_key,
                    metric["status"],
                    metric["observation_date"]
                )

            except Exception as exc:

                config = SERIES[key]

                LOGGER.error(
                    "%s fetch failed: %s",
                    key,
                    exc
                )

                metrics[key] = build_metric(
                    key,
                    config,
                    [],
                    "FRED"
                )

                metrics[key]["error"] = str(exc)[:500]

                observations_by_key[key] = []

    # Gold is disabled to avoid repeated HTTP 404 requests.

    gold_config = DISABLED_SERIES["gold"]

    metrics["gold"] = {
        "key": "gold",
        "name": gold_config["name"],
        "value": None,
        "unit": gold_config["unit"],
        "observation_date": None,
        "previous_value": None,
        "previous_date": None,
        "change": None,
        "change_percent": None,
        "source": gold_config["source"],
        "fetched_at": iso_now(),
        "status": "UNAVAILABLE",
        "error": gold_config["reason"]
    }

    observations_by_key["gold"] = []

    return metrics, observations_by_key


# ============================================================
# BUILD FINAL PAYLOAD
# ============================================================

def build_payload():

    LOGGER.info(
        "Starting Macro Engine v%s",
        VERSION
    )

    metrics, observations = fetch_all_series()

    payroll_change = calculate_payroll_change(
        observations.get("nonfarm_payrolls", [])
    )

    if "nonfarm_payrolls" in metrics:

        metrics["nonfarm_payrolls"][
            "monthly_change_thousands"
        ] = payroll_change

    inflation = build_inflation_report(
        metrics,
        observations
    )

    reports = build_indicator_reports(
        metrics,
        inflation
    )

    overall = build_overall_decision(
        metrics
    )

    ok_count = sum(
        1 for item in metrics.values()
        if item.get("status") == "OK"
    )

    stale_count = sum(
        1 for item in metrics.values()
        if item.get("status") == "STALE"
    )

    unavailable_count = sum(
        1 for item in metrics.values()
        if item.get("status") == "UNAVAILABLE"
    )

    return {
        "schema_version": 2,
        "engine": "Crypto Macro Engine",
        "engine_version": VERSION,
        "fetched_at": iso_now(),
        "source": "Federal Reserve Economic Data (FRED)",

        "source_mode": (
            "FRED API with CSV fallback"
            if FRED_API_KEY
            else "FRED CSV export"
        ),

        "summary": {
            "total_series": len(metrics),
            "ok": ok_count,
            "stale": stale_count,
            "unavailable": unavailable_count,

            "data_quality": (
                "GOOD"
                if ok_count >= 18
                else "PARTIAL"
                if ok_count >= 8
                else "POOR"
            )
        },

        "metrics": metrics,

        "inflation": inflation,

        "reports": reports,

        "overall_macro_decision": overall,

        "limitations": [
            "DTWEXBGS is a broad trade-weighted USD index proxy, not ICE DXY.",
            "FRED observations are released with delays.",
            "Per-series freshness limits account for normal release lags.",
            "Gold series is disabled after HTTP 404.",
            "No unverified replacement Gold price is used.",
            "Economic calendar forecast/actual/surprise is not integrated.",
            "BOJ policy and Japanese government bond yield curves are not integrated.",
            "Global central-bank liquidity composite is not integrated.",
            "Crypto ETF flows and crypto-specific on-chain data are not integrated.",
            "Macro decision is not a standalone trading signal."
        ],

        "not_integrated_yet": [
            "Economic calendar with forecast and actual",
            "BOJ policy and JGB yields",
            "JPY carry-trade risk model",
            "Global central-bank liquidity composite",
            "Verified live Gold market price source",
            "Crypto ETF flows",
            "BTC market structure and technical confirmation",
            "Crypto-specific on-chain data"
        ]
    }


# ============================================================
# ATOMIC JSON WRITER
# ============================================================

def save_json(payload):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    fd, temp_path = tempfile.mkstemp(
        prefix="macro_data_",
        suffix=".tmp",
        dir=str(DATA_DIR)
    )

    try:

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                payload,
                file,
                ensure_ascii=False,
                indent=2,
                allow_nan=False
            )

            file.write("\n")

        os.replace(
            temp_path,
            OUTPUT_FILE
        )

    except Exception:

        try:
            os.unlink(temp_path)
        except OSError:
            pass

        raise


# ============================================================
# MAIN
# ============================================================

def main():

    try:

        payload = build_payload()

        save_json(payload)

        summary = payload["summary"]

        LOGGER.info(
            "Macro Engine completed | OK=%s | STALE=%s | UNAVAILABLE=%s",
            summary["ok"],
            summary["stale"],
            summary["unavailable"]
        )

        LOGGER.info(
            "Overall decision: %s",
            payload["overall_macro_decision"]["DECISION"]
        )

        LOGGER.info(
            "Output: %s",
            OUTPUT_FILE
        )

        if summary["ok"] < 8:

            LOGGER.error(
                "Insufficient successful data series: %s",
                summary["ok"]
            )

            return 1

        return 0

    except Exception:

        LOGGER.exception(
            "Macro Engine failed"
        )

        return 1


if __name__ == "__main__":
    sys.exit(main())
