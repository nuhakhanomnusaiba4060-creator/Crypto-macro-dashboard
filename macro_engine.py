
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CRYPTO MACRO DASHBOARD - MACRO ENGINE
Version: 2.0.0

Output:
data/macro_data.json

Source:
Federal Reserve Economic Data (FRED)

Important:
- DTWEXBGS is NOT ICE DXY.
- Gold remains unavailable without a verified source.
- Macro decisions are not standalone crypto trading signals.
- FRED data is delayed, not real-time.
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
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# ============================================================
# CONFIGURATION
# ============================================================

VERSION = "2.0.0"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "macro_data.json"

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"

FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()

TIMEOUT = 25
RETRIES = 2
MAX_WORKERS = 8

USER_AGENT = "CryptoMacroDashboard/2.0.0"

LIQUIDITY_LOOKBACK_DAYS = 60

MAX_TGA_ALIGNMENT_DAYS = 7
MAX_RRP_ALIGNMENT_DAYS = 3

CRITICAL_SERIES = (
    "cpi",
    "core_cpi",
    "pce",
    "core_pce",
    "fed_funds_rate",
    "unemployment",
    "nonfarm_payrolls",
    "yield_2y",
    "yield_10y",
    "yield_30y",
    "yield_curve_10y_2y",
    "usd_broad_index",
    "vix",
    "sp500",
    "nasdaq",
    "fed_balance_sheet",
    "reverse_repo",
    "treasury_general_account"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

LOGGER = logging.getLogger("macro_engine")


# ============================================================
# FRED SERIES
# ============================================================

SERIES = {

    "fed_funds_rate": {
        "id": "DFF",
        "name": "Federal Funds Effective Rate",
        "unit": "%",
        "freshness_days": 7,
        "frequency": "daily"
    },

    "cpi": {
        "id": "CPIAUCSL",
        "name": "Consumer Price Index",
        "unit": "index",
        "freshness_days": 75,
        "frequency": "monthly"
    },

    "core_cpi": {
        "id": "CPILFESL",
        "name": "Core CPI",
        "unit": "index",
        "freshness_days": 75,
        "frequency": "monthly"
    },

    "pce": {
        "id": "PCEPI",
        "name": "PCE Price Index",
        "unit": "index",
        "freshness_days": 100,
        "frequency": "monthly"
    },

    "core_pce": {
        "id": "PCEPILFE",
        "name": "Core PCE Price Index",
        "unit": "index",
        "freshness_days": 100,
        "frequency": "monthly"
    },

    "unemployment": {
        "id": "UNRATE",
        "name": "Unemployment Rate",
        "unit": "%",
        "freshness_days": 75,
        "frequency": "monthly"
    },

    "nonfarm_payrolls": {
        "id": "PAYEMS",
        "name": "Total Nonfarm Payrolls",
        "unit": "thousands",
        "freshness_days": 75,
        "frequency": "monthly"
    },

    "yield_2y": {
        "id": "DGS2",
        "name": "US 2-Year Treasury Yield",
        "unit": "%",
        "freshness_days": 7,
        "frequency": "daily"
    },

    "yield_10y": {
        "id": "DGS10",
        "name": "US 10-Year Treasury Yield",
        "unit": "%",
        "freshness_days": 7,
        "frequency": "daily"
    },

    "yield_30y": {
        "id": "DGS30",
        "name": "US 30-Year Treasury Yield",
        "unit": "%",
        "freshness_days": 7,
        "frequency": "daily"
    },

    "yield_curve_10y_2y": {
        "id": "T10Y2Y",
        "name": "10Y-2Y Treasury Spread",
        "unit": "percentage_points",
        "freshness_days": 7,
        "frequency": "daily"
    },

    "usd_broad_index": {
        "id": "DTWEXBGS",
        "name": "Trade Weighted US Dollar Index",
        "unit": "index",
        "freshness_days": 10,
        "frequency": "daily"
    },

    "vix": {
        "id": "VIXCLS",
        "name": "CBOE Volatility Index",
        "unit": "index",
        "freshness_days": 7,
        "frequency": "daily"
    },

    "sp500": {
        "id": "SP500",
        "name": "S&P 500",
        "unit": "index",
        "freshness_days": 7,
        "frequency": "daily"
    },

    "nasdaq": {
        "id": "NASDAQCOM",
        "name": "NASDAQ Composite",
        "unit": "index",
        "freshness_days": 7,
        "frequency": "daily"
    },

    "oil": {
        "id": "DCOILWTICO",
        "name": "WTI Crude Oil",
        "unit": "USD/barrel",
        "freshness_days": 10,
        "frequency": "daily"
    },

    "usd_jpy": {
        "id": "DEXJPUS",
        "name": "Japanese Yen per US Dollar",
        "unit": "JPY/USD",
        "freshness_days": 10,
        "frequency": "daily"
    },

    "fed_balance_sheet": {
        "id": "WALCL",
        "name": "Federal Reserve Total Assets",
        "unit": "millions USD",
        "freshness_days": 21,
        "frequency": "weekly"
    },

    "reverse_repo": {
        "id": "RRPONTSYD",
        "name": "Overnight Reverse Repurchase Agreements",
        "unit": "billions USD",
        "freshness_days": 7,
        "frequency": "daily"
    },

    "treasury_general_account": {
        "id": "WTREGEN",
        "name": "Treasury General Account",
        "unit": "millions USD",
        "freshness_days": 21,
        "frequency": "weekly"
    },

    "m2_money_supply": {
        "id": "M2SL",
        "name": "M2 Money Supply",
        "unit": "billions USD",
        "freshness_days": 100,
        "frequency": "monthly"
    }
}


DISABLED_SERIES = {
    "gold": {
        "name": "Gold Price",
        "unit": "USD/oz",
        "source": "Unavailable",
        "reason": (
            "No verified replacement Gold price source configured."
        )
    }
}


# ============================================================
# TIME AND NUMBER HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def iso_now():

    return (
        utc_now()
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_date(value):

    if not isinstance(value, str):
        return None

    try:

        return datetime.strptime(
            value,
            "%Y-%m-%d"
        ).replace(tzinfo=timezone.utc)

    except (ValueError, TypeError):

        return None


def safe_number(value):

    try:

        number = float(value)

        if math.isfinite(number):
            return number

    except (ValueError, TypeError, OverflowError):

        pass

    return None


def round_value(value, digits=4):

    if value is None:
        return None

    return round(value, digits)


def percentage_change(current, previous):

    if (
        current is None
        or previous is None
        or previous == 0
    ):
        return None

    return (
        (current - previous) / abs(previous)
    ) * 100


def observation_age_days(date_text):

    observed = parse_date(date_text)

    if observed is None:
        return None

    age = (
        utc_now() - observed
    ).total_seconds() / 86400

    # Future observation is invalid.
    if age < -0.01:
        return None

    return max(0, age)


def freshness_status(date_text, max_days):

    age = observation_age_days(date_text)

    if age is None:
        return "UNAVAILABLE"

    if age > max_days:
        return "STALE"

    return "OK"


def find_observation_at_or_before(observations, target_date):

    result = None

    for item in observations:

        observed = parse_date(item["date"])

        if observed is None:
            continue

        if observed <= target_date:
            result = item
        else:
            break

    return result


def historical_value(observations, days):

    if not observations:
        return None

    current_date = parse_date(
        observations[-1]["date"]
    )

    if current_date is None:
        return None

    cutoff = current_date - timedelta(days=days)

    item = find_observation_at_or_before(
        observations,
        cutoff
    )

    return item["value"] if item else None


def historical_change(observations, days):

    if not observations:
        return None

    current = observations[-1]

    previous = find_observation_at_or_before(
        observations,
        parse_date(current["date"]) - timedelta(days=days)
    )

    if previous is None:
        return None

    return round_value(
        percentage_change(
            current["value"],
            previous["value"]
        ),
        4
    )


def historical_absolute_change(observations, days):

    if not observations:
        return None

    current = observations[-1]

    current_date = parse_date(current["date"])

    if current_date is None:
        return None

    previous = find_observation_at_or_before(
        observations,
        current_date - timedelta(days=days)
    )

    if previous is None:
        return None

    return round_value(
        current["value"] - previous["value"],
        4
    )


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
        ) as error:

            last_error = str(error)

            if attempt < RETRIES:
                time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(
        last_error or "HTTP request failed"
    )


# ============================================================
# FRED FETCH
# ============================================================

def fetch_fred_csv(series_id):

    params = urlencode({
        "id": series_id
    })

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

    if not observations:

        raise RuntimeError(
            f"No valid CSV observations: {series_id}"
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

    payload = json.loads(
        http_get(url)
    )

    if not isinstance(payload, dict):
        raise RuntimeError("Invalid FRED API response")

    raw_observations = payload.get("observations")

    if not isinstance(raw_observations, list):
        raise RuntimeError("FRED observations missing")

    observations = []

    for item in raw_observations:

        if not isinstance(item, dict):
            continue

        date_text = item.get("date")

        if parse_date(date_text) is None:
            continue

        value = safe_number(
            item.get("value")
        )

        if value is None:
            continue

        observations.append({
            "date": date_text,
            "value": value
        })

    observations.sort(
        key=lambda item: item["date"]
    )

    if not observations:

        raise RuntimeError(
            f"No valid API observations: {series_id}"
        )

    return observations


def fetch_series(series_id):

    if FRED_API_KEY:

        try:

            return (
                fetch_fred_api(series_id),
                "FRED_API"
            )

        except Exception as error:

            LOGGER.warning(
                "%s API failed; CSV fallback: %s",
                series_id,
                error
            )

    return (
        fetch_fred_csv(series_id),
        "FRED_CSV_EXPORT"
    )


# ============================================================
# METRIC BUILD
# ============================================================

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

            "change_5d_percent": None,

            "change_20d_percent": None,

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

    status = freshness_status(
        current["date"],
        config["freshness_days"]
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

    return {

        "key": key,

        "name": config["name"],

        "value": round_value(
            current["value"]
        ),

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

        "change_5d_percent": historical_change(
            observations,
            5
        ),

        "change_20d_percent": historical_change(
            observations,
            20
        ),

        "change_5d": historical_absolute_change(
            observations,
            5
        ),

        "change_20d": historical_absolute_change(
            observations,
            20
        ),

        "source": source,

        "fetched_at": fetched_at,

        "age_days": round_value(
            observation_age_days(current["date"]),
            2
        ),

        "status": status,

        "error": (
            None
            if status == "OK"
            else "Observation is stale or timestamp invalid."
        )
    }


# ============================================================
# MONTHLY INFLATION CALCULATIONS
# ============================================================

def monthly_observation_map(observations):

    result = {}

    for item in observations:

        date_value = parse_date(
            item.get("date")
        )

        value = safe_number(
            item.get("value")
        )

        if date_value is None or value is None:
            continue

        key = (
            date_value.year,
            date_value.month
        )

        result[key] = value

    return result


def month_offset(year, month, offset):

    total = (
        year * 12
        + month - 1
        - offset
    )

    return (
        total // 12,
        total % 12 + 1
    )


def monthly_percent_change(values, periods):

    if not values:
        return None

    latest_key = max(values)

    previous_key = month_offset(
        latest_key[0],
        latest_key[1],
        periods
    )

    current = values.get(latest_key)
    previous = values.get(previous_key)

    if current is None or previous is None:
        return None

    return round_value(
        percentage_change(
            current,
            previous
        ),
        3
    )


def calculate_inflation_metrics(observations):

    values = monthly_observation_map(
        observations
    )

    mom = monthly_percent_change(
        values,
        1
    )

    three_month = monthly_percent_change(
        values,
        3
    )

    yoy = monthly_percent_change(
        values,
        12
    )

    if mom is None or yoy is None:

        status = "INSUFFICIENT_HISTORY"

    else:

        status = "OK"

    return {

        "mom_percent": mom,

        "three_month_percent": three_month,

        "yoy_percent": yoy,

        "status": status,

        "calculation_method": "CALENDAR_MONTH_COMPARISON",

        "seasonal_adjustment_note": (
            "FRED series CPIAUCSL, CPILFESL, PCEPI and PCEPILFE "
            "are seasonally adjusted index series."
        )
    }


def build_inflation_report(metrics, observations_by_key):

    labels = {

        "cpi": "CPI",

        "core_cpi": "Core CPI",

        "pce": "PCE",

        "core_pce": "Core PCE"
    }

    result = {}

    for key, label in labels.items():

        source_metric = metrics.get(
            key,
            {}
        )

        if source_metric.get("status") != "OK":

            result[key] = {

                "name": label,

                "mom_percent": None,

                "three_month_percent": None,

                "yoy_percent": None,

                "status": source_metric.get(
                    "status",
                    "UNAVAILABLE"
                )
            }

            continue

        calculated = calculate_inflation_metrics(
            observations_by_key.get(key, [])
        )

        result[key] = {

            "name": label,

            **calculated
        }

    return result


# ============================================================
# PAYROLL VALIDATION
# ============================================================

def calculate_payroll_change(observations):

    values = monthly_observation_map(
        observations
    )

    if not values:
        return None

    latest_key = max(values)

    previous_key = month_offset(
        latest_key[0],
        latest_key[1],
        1
    )

    current = values.get(latest_key)
    previous = values.get(previous_key)

    if current is None or previous is None:
        return None

    return round_value(
        current - previous,
        1
    )


# ============================================================
# REPORT HELPERS
# ============================================================

def make_report(data, analysis, decision, action, risk):

    return {

        "DATA": data,

        "ANALYSIS": analysis,

        "DECISION": decision,

        "ACTION": action,

        "RISK": risk
    }


def metric_value(metrics, key):

    item = metrics.get(key, {})

    if not isinstance(item, dict):
        return None

    if item.get("status") != "OK":
        return None

    return safe_number(
        item.get("value")
    )


def report_unavailable(label):

    return make_report(

        None,

        f"{label} data unavailable or stale.",

        "WAIT — INSUFFICIENT DATA",

        f"{label} data যাচাই না হওয়া পর্যন্ত সিদ্ধান্ত স্থগিত রাখুন।",

        "অসম্পূর্ণ বা পুরোনো ডেটা থেকে নির্ভরযোগ্য সিদ্ধান্ত নেওয়া যাবে না।"
    )


# ============================================================
# NET LIQUIDITY ENGINE
# ============================================================

def clean_liquidity_observations(items):

    cleaned = []

    for item in items:

        if not isinstance(item, dict):
            continue

        date_text = item.get("date")

        value = safe_number(
            item.get("value")
        )

        if parse_date(date_text) is None:
            continue

        if value is None:
            continue

        cleaned.append({

            "date": date_text,

            "value": value
        })

    cleaned.sort(
        key=lambda item: item["date"]
    )

    return cleaned


def build_liquidity_analysis(metrics, observations_by_key):

    required = (

        "fed_balance_sheet",

        "treasury_general_account",

        "reverse_repo"
    )

    missing = [

        key for key in required

        if metrics.get(key, {}).get("status") != "OK"
    ]

    if missing:

        return {

            "status": "UNAVAILABLE",

            "missing_metrics": missing,

            "unit": "billions USD",

            "current": None,

            "change_7d": None,

            "change_30d": None,

            "formula": "WALCL - TGA - RRP",

            "error": "Required liquidity series unavailable or stale."
        }

    walcl = clean_liquidity_observations(
        observations_by_key.get(
            "fed_balance_sheet",
            []
        )
    )

    tga = clean_liquidity_observations(
        observations_by_key.get(
            "treasury_general_account",
            []
        )
    )

    rrp = clean_liquidity_observations(
        observations_by_key.get(
            "reverse_repo",
            []
        )
    )

    if not walcl or not tga or not rrp:

        return {

            "status": "UNAVAILABLE",

            "missing_metrics": [],

            "unit": "billions USD",

            "current": None,

            "change_7d": None,

            "change_30d": None,

            "formula": "WALCL - TGA - RRP",

            "error": "Liquidity historical series incomplete."
        }

    combined = []

    for walcl_item in walcl:

        target_date = parse_date(
            walcl_item["date"]
        )

        if target_date is None:
            continue

        tga_item = find_observation_at_or_before(
            tga,
            target_date
        )

        rrp_item = find_observation_at_or_before(
            rrp,
            target_date
        )

        if tga_item is None or rrp_item is None:
            continue

        tga_date = parse_date(
            tga_item["date"]
        )

        rrp_date = parse_date(
            rrp_item["date"]
        )

        if tga_date is None or rrp_date is None:
            continue

        tga_age = (
            target_date - tga_date
        ).total_seconds() / 86400

        rrp_age = (
            target_date - rrp_date
        ).total_seconds() / 86400

        if (
            tga_age < 0
            or tga_age > MAX_TGA_ALIGNMENT_DAYS
        ):
            continue

        if (
            rrp_age < 0
            or rrp_age > MAX_RRP_ALIGNMENT_DAYS
        ):
            continue

        walcl_billions = (
            walcl_item["value"] / 1000
        )

        tga_billions = (
            tga_item["value"] / 1000
        )

        rrp_billions = rrp_item["value"]

        net_liquidity = (
            walcl_billions
            - tga_billions
            - rrp_billions
        )

        if not math.isfinite(net_liquidity):
            continue

        combined.append({

            "date": walcl_item["date"],

            "value": net_liquidity,

            "walcl": walcl_billions,

            "tga": tga_billions,

            "rrp": rrp_billions,

            "tga_observation_date": tga_item["date"],

            "rrp_observation_date": rrp_item["date"],

            "tga_age_days": round(tga_age, 2),

            "rrp_age_days": round(rrp_age, 2)
        })

    if not combined:

        return {

            "status": "UNAVAILABLE",

            "missing_metrics": [],

            "unit": "billions USD",

            "current": None,

            "change_7d": None,

            "change_30d": None,

            "formula": "WALCL - TGA - RRP",

            "error": (
                "No sufficiently aligned observations. "
                "Component observation dates are too far apart."
            )
        }

    latest = combined[-1]

    latest_date = parse_date(
        latest["date"]
    )

    cutoff = (
        latest_date
        - timedelta(days=LIQUIDITY_LOOKBACK_DAYS)
    )

    combined = [

        item for item in combined

        if parse_date(item["date"]) >= cutoff
    ]

    latest = combined[-1]

    def previous_value(days):

        target = (
            parse_date(latest["date"])
            - timedelta(days=days)
        )

        candidates = [

            item for item in combined

            if parse_date(item["date"]) <= target
        ]

        if not candidates:
            return None

        return candidates[-1]["value"]

    old_7d = previous_value(7)
    old_30d = previous_value(30)

    change_7d = (

        round_value(
            latest["value"] - old_7d,
            3
        )

        if old_7d is not None

        else None
    )

    change_30d = (

        round_value(
            latest["value"] - old_30d,
            3
        )

        if old_30d is not None

        else None
    )

    if change_30d is None:

        trend = "INSUFFICIENT_HISTORY"

    elif change_30d > 0:

        trend = "EXPANDING"

    elif change_30d < 0:

        trend = "CONTRACTING"

    else:

        trend = "FLAT"

    return {

        "status": "OK",

        "unit": "billions USD",

        "formula": "WALCL - TGA - RRP",

        "observation_date": latest["date"],

        "current": round_value(
            latest["value"],
            3
        ),

        "components": {

            "fed_assets": round_value(
                latest["walcl"],
                3
            ),

            "treasury_general_account": round_value(
                latest["tga"],
                3
            ),

            "reverse_repo": round_value(
                latest["rrp"],
                3
            ),

            "tga_observation_date": latest[
                "tga_observation_date"
            ],

            "reverse_repo_observation_date": latest[
                "rrp_observation_date"
            ]
        },

        "change_7d": change_7d,

        "change_30d": change_30d,

        "trend": trend,

        "observations_available": len(combined),

        "alignment_method": "STRICT_AS_OF_DATE",

        "lookback_days": LIQUIDITY_LOOKBACK_DAYS,

        "max_tga_age_days": MAX_TGA_ALIGNMENT_DAYS,

        "max_rrp_age_days": MAX_RRP_ALIGNMENT_DAYS
    }


def build_liquidity_report(metrics, observations_by_key):

    liquidity = build_liquidity_analysis(
        metrics,
        observations_by_key
    )

    if liquidity.get("status") != "OK":

        return make_report(

            liquidity,

            "US Net Liquidity calculation unavailable.",

            "WAIT — INSUFFICIENT DATA",

            "Liquidity data সম্পূর্ণ না হওয়া পর্যন্ত Net Liquidity signal ব্যবহার করবেন না।",

            "WALCL, TGA ও RRP-এর observation date যথেষ্ট কাছাকাছি নয়।"
        )

    change_30d = liquidity.get("change_30d")

    if change_30d is None:

        decision = "WAIT — INSUFFICIENT DATA"

        analysis = "30D liquidity comparison পাওয়া যায়নি।"

        action = "30D historical data সংগ্রহের অপেক্ষা করুন।"

        risk = "শুধু current value দিয়ে liquidity trend নির্ধারণ করা যাবে না।"

    elif change_30d <= -50:

        decision = "REDUCE RISK"

        analysis = "US Net Liquidity 30 দিনে $50B বা তার বেশি সংকুচিত হয়েছে।"

        action = "Liquidity contraction চলায় ঝুঁকিপূর্ণ Altcoin exposure সীমিত রাখুন।"

        risk = "US Net Liquidity একটি proxy; Global Liquidity নয়।"

    elif change_30d >= 50:

        decision = "HOLD / SELECTIVE"

        analysis = "US Net Liquidity 30 দিনে $50B বা তার বেশি বৃদ্ধি পেয়েছে।"

        action = "Liquidity support ইতিবাচক; BTC trend ও crypto breadth যাচাই করুন।"

        risk = "Liquidity expansion নিশ্চিত Bull Market নয়।"

    else:

        decision = "WAIT"

        analysis = "US Net Liquidity-তে বড় 30D expansion বা contraction নেই।"

        action = "পরবর্তী liquidity observation পর্যবেক্ষণ করুন।"

        risk = "এই proxy একা Crypto market direction নির্ধারণ করে না।"

    return make_report(

        liquidity,

        analysis,

        decision,

        action,

        risk
    )


# ============================================================
# YIELD CURVE
# ============================================================

def build_yield_curve_analysis(metrics, observations_by_key):

    item = metrics.get(
        "yield_curve_10y_2y",
        {}
    )

    observations = observations_by_key.get(
        "yield_curve_10y_2y",
        []
    )

    if item.get("status") != "OK":

        return {

            "status": "UNAVAILABLE",

            "spread": None,

            "change_30d": None,

            "inverted": None,

            "trend": "UNKNOWN"
        }

    spread = safe_number(
        item.get("value")
    )

    if spread is None:

        return {

            "status": "UNAVAILABLE",

            "spread": None,

            "change_30d": None,

            "inverted": None,

            "trend": "UNKNOWN"
        }

    old_value = historical_value(
        observations,
        30
    )

    change_30d = (

        round_value(
            spread - old_value,
            4
        )

        if old_value is not None

        else None
    )

    if change_30d is None:

        trend = "INSUFFICIENT_HISTORY"

    elif change_30d > 0.05:

        trend = "STEEPENING"

    elif change_30d < -0.05:

        trend = "FLATTENING"

    else:

        trend = "STABLE"

    return {

        "status": "OK",

        "spread": spread,

        "unit": "percentage_points",

        "observation_date": item.get(
            "observation_date"
        ),

        "change_30d": change_30d,

        "inverted": spread < 0,

        "trend": trend
    }


def build_yield_curve_report(metrics, observations_by_key):

    curve = build_yield_curve_analysis(
        metrics,
        observations_by_key
    )

    if curve["status"] != "OK":

        return report_unavailable(
            "Yield Curve"
        )

    if curve["trend"] == "INSUFFICIENT_HISTORY":

        decision = "WAIT"

        analysis = "10Y-2Y spread পাওয়া গেছে, কিন্তু 30D trend incomplete."

        action = "Historical spread data সম্পূর্ণ করুন।"

    elif curve["inverted"]:

        decision = "WAIT"

        analysis = "10Y-2Y Treasury yield curve inverted অবস্থায় রয়েছে।"

        action = "Labor market, credit conditions ও equity trend মিলিয়ে দেখুন।"

    elif curve["trend"] == "STEEPENING":

        decision = "HOLD / SELECTIVE"

        analysis = "10Y-2Y spread গত 30 দিনে বেড়েছে।"

        action = "Steepening growth expectation নাকি long-yield pressure থেকে হচ্ছে যাচাই করুন।"

    elif curve["trend"] == "FLATTENING":

        decision = "WAIT"

        analysis = "10Y-2Y spread গত 30 দিনে কমেছে।"

        action = "Growth expectation ও Treasury yield pressure পর্যবেক্ষণ করুন।"

    else:

        decision = "HOLD / SELECTIVE"

        analysis = "10Y-2Y spread positive এবং তুলনামূলক স্থিতিশীল।"

        action = "Inflation, employment ও long-term yield-এর সঙ্গে পর্যবেক্ষণ করুন।"

    return make_report(

        curve,

        analysis,

        decision,

        action,

        "Yield curve inversion recession নিশ্চিত করে না।"
    )


# ============================================================
# INFLATION REPORT
# ============================================================

def build_inflation_indicator_report(
    key,
    label,
    inflation,
    high_level,
    caution_level
):

    item = inflation.get(key, {})

    if item.get("status") != "OK":

        return report_unavailable(label)

    yoy = item.get("yoy_percent")

    mom = item.get("mom_percent")

    three_month = item.get("three_month_percent")

    if yoy is None or mom is None:

        return report_unavailable(label)

    if yoy >= high_level and mom >= 0.30:

        decision = "REDUCE RISK"

        analysis = f"{label} YoY এবং MoM উভয়ই উচ্চ inflation pressure নির্দেশ করছে।"

        action = "Fed policy, Treasury yield ও BTC trend-এর সঙ্গে inflation pressure যাচাই করুন।"

    elif yoy >= high_level:

        decision = "WAIT"

        analysis = f"{label} YoY elevated, কিন্তু সর্বশেষ MoM reading তুলনামূলক কম।"

        action = "পরবর্তী inflation release দিয়ে trend যাচাই করুন।"

    elif yoy >= caution_level:

        decision = "WAIT"

        analysis = f"{label} inflation এখনো সতর্কতার পর্যায়ে রয়েছে।"

        action = "MoM ও 3M trend পর্যবেক্ষণ করুন।"

    else:

        decision = "HOLD / SELECTIVE"

        analysis = f"{label} YoY তুলনামূলক নিয়ন্ত্রিত।"

        action = "Fed policy, yields ও BTC trend-এর সঙ্গে মিলিয়ে দেখুন।"

    return make_report(

        {

            "yoy_percent": yoy,

            "mom_percent": mom,

            "three_month_percent": three_month
        },

        analysis,

        decision,

        action,

        "একটি inflation reading দিয়ে Fed policy নিশ্চিত করা যায় না।"
    )


# ============================================================
# INDICATOR REPORTS
# ============================================================

def build_indicator_reports(metrics, inflation, observations_by_key):

    reports = {}

    inflation_rules = (

        ("cpi", "CPI", 4.0, 3.0),

        ("core_cpi", "Core CPI", 4.0, 3.0),

        ("pce", "PCE", 3.0, 2.0),

        ("core_pce", "Core PCE", 3.0, 2.0)
    )

    for key, label, high, caution in inflation_rules:

        reports[key] = build_inflation_indicator_report(

            key,
            label,
            inflation,
            high,
            caution
        )

    # FED RATE

    fed = metric_value(
        metrics,
        "fed_funds_rate"
    )

    if fed is None:

        reports["fed_rate"] = report_unavailable(
            "Fed Funds Rate"
        )

    else:

        reports["fed_rate"] = make_report(

            {

                "effective_rate_percent": fed,

                "observation_date": metrics[
                    "fed_funds_rate"
                ]["observation_date"]
            },

            "সর্বশেষ effective Fed Funds Rate পাওয়া গেছে।",

            "HOLD / SELECTIVE",

            "Fed rate-কে inflation, employment ও FOMC guidance-এর সঙ্গে বিশ্লেষণ করুন।",

            "Effective rate একা পরবর্তী FOMC সিদ্ধান্ত জানায় না।"
        )

    # LABOR MARKET

    unemployment = metric_value(
        metrics,
        "unemployment"
    )

    payroll = metrics.get(
        "nonfarm_payrolls",
        {}
    ).get(
        "monthly_change_thousands"
    )

    if unemployment is None or payroll is None:

        reports["labor_market"] = report_unavailable(
            "Labor Market"
        )

    elif unemployment >= 5 or payroll < 0:

        reports["labor_market"] = make_report(

            {

                "unemployment_percent": unemployment,

                "nfp_monthly_change_thousands": payroll
            },

            "Employment deterioration-এর লক্ষণ রয়েছে।",

            "REDUCE RISK",

            "Labor market দুর্বলতার সঙ্গে equity ও Fed policy যাচাই করুন।",

            "NFP revision ও labor force participation গুরুত্বপূর্ণ।"
        )

    elif unemployment >= 4.5:

        reports["labor_market"] = make_report(

            {

                "unemployment_percent": unemployment,

                "nfp_monthly_change_thousands": payroll
            },

            "Unemployment elevated range-এ রয়েছে।",

            "WAIT",

            "পরবর্তী NFP ও unemployment release পর্যবেক্ষণ করুন।",

            "Unemployment একা recession নিশ্চিত করে না।"
        )

    else:

        reports["labor_market"] = make_report(

            {

                "unemployment_percent": unemployment,

                "nfp_monthly_change_thousands": payroll
            },

            "Labor market তুলনামূলক স্থিতিশীল।",

            "HOLD / SELECTIVE",

            "Employment ও wage inflation একসঙ্গে পর্যবেক্ষণ করুন।",

            "শক্তিশালী employment inflation pressure বজায় রাখতে পারে।"
        )

    # BOND YIELDS

    y2 = metric_value(metrics, "yield_2y")

    y10 = metric_value(metrics, "yield_10y")

    y30 = metric_value(metrics, "yield_30y")

    y10_change = metrics.get(
        "yield_10y",
        {}
    ).get("change_20d")

    if (
        y2 is None
        or y10 is None
        or y30 is None
        or y10_change is None
    ):

        reports["bond_yields"] = report_unavailable(
            "Treasury Yield"
        )

    else:

        if y10_change >= 0.20:

            decision = "REDUCE RISK"

            analysis = "10Y Treasury yield-এর 20D পরিবর্তন উল্লেখযোগ্যভাবে বেড়েছে।"

            action = "Inflation, Treasury supply ও BTC trend যাচাই করুন।"

        elif y10_change <= -0.20:

            decision = "HOLD / SELECTIVE"

            analysis = "10Y Treasury yield-এর 20D পরিবর্তন কমেছে।"

            action = "Yield decline growth concern নাকি inflation cooling তা যাচাই করুন।"

        else:

            decision = "WAIT"

            analysis = "10Y yield-এর 20D পরিবর্তন উল্লেখযোগ্য নয়।"

            action = "Treasury yield trend পর্যবেক্ষণ করুন।"

        reports["bond_yields"] = make_report(

            {

                "2y": y2,

                "10y": y10,

                "30y": y30,

                "10y_20d_change_pp": y10_change
            },

            analysis,

            decision,

            action,

            "একটি yield movement দীর্ঘমেয়াদি trend নিশ্চিত করে না।"
        )

    # YIELD CURVE

    reports["yield_curve"] = build_yield_curve_report(
        metrics,
        observations_by_key
    )

    # BROAD USD

    usd = metrics.get(
        "usd_broad_index",
        {}
    )

    usd_change = usd.get(
        "change_20d_percent"
    )

    if usd.get("status") != "OK" or usd_change is None:

        reports["usd_index"] = report_unavailable(
            "Broad USD Index"
        )

    elif usd_change >= 1:

        reports["usd_index"] = make_report(

            {"change_20d_percent": usd_change},

            "Broad USD Index-এর 20D trend শক্তিশালী হয়েছে।",

            "REDUCE RISK",

            "Dollar strength-এর সঙ্গে Crypto risk exposure সতর্কভাবে পরিচালনা করুন।",

            "এটি ICE DXY নয়; trade-weighted USD proxy।"
        )

    elif usd_change <= -1:

        reports["usd_index"] = make_report(

            {"change_20d_percent": usd_change},

            "Broad USD Index-এর 20D trend দুর্বল হয়েছে।",

            "HOLD / SELECTIVE",

            "USD weakness BTC ও Altcoin trend-এর সঙ্গে যাচাই করুন।",

            "USD দুর্বল হলেই Crypto bullish হয় না।"
        )

    else:

        reports["usd_index"] = make_report(

            {"change_20d_percent": usd_change},

            "Broad USD Index-এর 20D পরিবর্তন সীমিত।",

            "WAIT",

            "USD trend পর্যবেক্ষণ করুন।",

            "এটি ICE DXY নয়।"
        )

    # VIX

    vix = metric_value(
        metrics,
        "vix"
    )

    if vix is None:

        reports["vix"] = report_unavailable("VIX")

    elif vix >= 30:

        reports["vix"] = make_report(

            {"value": vix},

            "VIX অত্যন্ত উচ্চ; Equity volatility stress elevated.",

            "REDUCE RISK",

            "নতুন ঝুঁকিপূর্ণ BUY সীমিত রাখুন।",

            "VIX equity volatility মাপে; Crypto volatility সরাসরি নয়।"
        )

    elif vix >= 25:

        reports["vix"] = make_report(

            {"value": vix},

            "VIX elevated risk range-এ রয়েছে।",

            "WAIT",

            "BTC volatility ও equity trend পর্যবেক্ষণ করুন।",

            "VIX একা Crypto market direction নির্ধারণ করে না।"
        )

    elif vix >= 18:

        reports["vix"] = make_report(

            {"value": vix},

            "VIX মাঝারি range-এ রয়েছে।",

            "WAIT",

            "Equity volatility পর্যবেক্ষণ করুন।",

            "Crypto-specific risk আলাদাভাবে যাচাই করতে হবে।"
        )

    else:

        reports["vix"] = make_report(

            {"value": vix},

            "VIX তুলনামূলক কম।",

            "HOLD / SELECTIVE",

            "কম VIX-কে একমাত্র BUY signal হিসেবে ব্যবহার করবেন না।",

            "কম VIX থাকলেও Crypto-specific risk থাকতে পারে।"
        )

    # EQUITY MARKET

    sp = metric_value(metrics, "sp500")

    nq = metric_value(metrics, "nasdaq")

    sp_change = metrics.get(
        "sp500",
        {}
    ).get("change_20d_percent")

    nq_change = metrics.get(
        "nasdaq",
        {}
    ).get("change_20d_percent")

    if (
        sp is None
        or nq is None
        or sp_change is None
        or nq_change is None
    ):

        reports["equity_market"] = report_unavailable(
            "Equity Market"
        )

    else:

        both_negative = (
            sp_change <= -3
            and nq_change <= -3
        )

        reports["equity_market"] = make_report(

            {

                "sp500": sp,

                "nasdaq": nq,

                "sp500_20d_change_percent": sp_change,

                "nasdaq_20d_change_percent": nq_change
            },

            (
                "S&P 500 ও Nasdaq উভয়ের 20D trend দুর্বল।"
                if both_negative
                else "S&P 500 ও Nasdaq-এর 20D data পাওয়া গেছে।"
            ),

            "WAIT" if both_negative else "HOLD / SELECTIVE",

            (
                "Equity weakness-এর সময়ে নতুন ঝুঁকিপূর্ণ BUY সীমিত রাখুন।"
                if both_negative
                else "Equity trend-কে VIX, yields ও BTC trend-এর সঙ্গে মিলিয়ে দেখুন।"
            ),

            "20D equity trend-ও Crypto market direction নিশ্চিত করে না।"
        )

    # COMMODITIES

    oil = metric_value(
        metrics,
        "oil"
    )

    gold = metrics.get(
        "gold",
        {}
    )

    reports["commodities"] = make_report(

        {

            "wti_oil_usd_per_barrel": oil,

            "gold_usd_per_oz": None,

            "gold_status": gold.get(
                "status",
                "UNAVAILABLE"
            ),

            "gold_note": gold.get("error")
        },

        (
            "WTI oil data পাওয়া গেছে; Gold source unavailable."
            if oil is not None
            else "Commodity data incomplete; Gold source unavailable."
        ),

        (
            "HOLD / SELECTIVE"
            if oil is not None
            else "WAIT — INSUFFICIENT DATA"
        ),

        "Oil-এর inflation impact পর্যবেক্ষণ করুন; Gold-এর জন্য verified source প্রয়োজন।",

        "Gold-এর কোনো কৃত্রিম বা পুরোনো মান ব্যবহার করা হচ্ছে না।"
    )

    # YEN

    yen = metric_value(
        metrics,
        "usd_jpy"
    )

    if yen is None:

        reports["yen"] = report_unavailable(
            "USD/JPY"
        )

    else:

        reports["yen"] = make_report(

            {

                "jpy_per_usd": yen,

                "observation_date": metrics[
                    "usd_jpy"
                ]["observation_date"]
            },

            "USD/JPY latest observation পাওয়া গেছে।",

            "WAIT",

            "Yen movement-এর সঙ্গে BOJ policy ও Japanese bond yield পর্যবেক্ষণ করুন।",

            "JGB yield curve ছাড়া carry-trade unwind নিশ্চিত করা যায় না।"
        )

    # US LIQUIDITY

    reports["liquidity"] = build_liquidity_report(
        metrics,
        observations_by_key
    )

    return reports


# ============================================================
# MULTI-FACTOR MACRO DECISION
# ============================================================

def build_overall_decision(
    metrics,
    inflation,
    liquidity,
    yield_curve
):

    risk_flags = []

    supportive_flags = []

    unavailable = []

    required = (

        "usd_broad_index",

        "vix",

        "yield_10y",

        "cpi",

        "core_pce",

        "unemployment",

        "sp500",

        "nasdaq"
    )

    for key in required:

        if metrics.get(key, {}).get("status") != "OK":

            unavailable.append(key)

    # Inflation history is required for the overall score.

    for key in ("cpi", "core_pce"):

        if inflation.get(key, {}).get("status") != "OK":

            unavailable.append(
                f"{key}_inflation_history"
            )

    # Required derived data.

    if metrics.get(
        "nonfarm_payrolls",
        {}
    ).get("monthly_change_thousands") is None:

        unavailable.append("consecutive_month_nfp_change")

    if liquidity.get("status") != "OK":

        unavailable.append("net_liquidity")

    if liquidity.get("change_30d") is None:

        unavailable.append("net_liquidity_30d_history")

    if yield_curve.get("status") != "OK":

        unavailable.append("yield_curve")

    if yield_curve.get("change_30d") is None:

        unavailable.append("yield_curve_30d_history")

    if unavailable:

        return {

            "DATA": {

                "required_metrics": list(required),

                "missing_metrics": sorted(set(unavailable)),

                "risk_flags": [],

                "supportive_flags": [],

                "risk_score": None,

                "support_score": None,

                "model_type": "RULE_BASED_MULTI_FACTOR",

                "calibrated_probability": None
            },

            "ANALYSIS": "Core Macro calculation incomplete বা stale.",

            "DECISION": "WAIT — INSUFFICIENT DATA",

            "ACTION": "Core Macro data সম্পূর্ণ না হওয়া পর্যন্ত Risk-On/Risk-Off সিদ্ধান্ত স্থগিত রাখুন।",

            "RISK": "অসম্পূর্ণ data থেকে ভুল market assessment হতে পারে।"
        }

    risk_score = 0

    support_score = 0

    # INFLATION

    cpi_yoy = inflation["cpi"]["yoy_percent"]

    core_pce_yoy = inflation["core_pce"]["yoy_percent"]

    cpi_mom = inflation["cpi"]["mom_percent"]

    core_pce_mom = inflation["core_pce"]["mom_percent"]

    inflation_pressure = (

        cpi_yoy >= 4

        and core_pce_yoy >= 3

        and cpi_mom >= 0.30

        and core_pce_mom >= 0.30
    )

    inflation_cooling = (

        cpi_yoy < 3

        and core_pce_yoy < 2.5

        and cpi_mom < 0.20

        and core_pce_mom < 0.20
    )

    if inflation_pressure:

        risk_score += 1

        risk_flags.append(
            "Broad inflation pressure"
        )

    elif inflation_cooling:

        support_score += 1

        supportive_flags.append(
            "CPI and Core PCE comparatively cooling"
        )

    # BROAD USD: 20D trend

    usd_change = metrics[
        "usd_broad_index"
    ].get("change_20d_percent")

    if usd_change is None:

        unavailable.append("usd_20d_trend")

    elif usd_change >= 1:

        risk_score += 1

        risk_flags.append(
            "Broad USD 20D strengthening"
        )

    elif usd_change <= -1:

        support_score += 1

        supportive_flags.append(
            "Broad USD 20D weakening"
        )

    # VIX

    vix = metric_value(
        metrics,
        "vix"
    )

    if vix >= 30:

        risk_score += 2

        risk_flags.append(
            "VIX >= 30"
        )

    elif vix >= 25:

        risk_score += 1

        risk_flags.append(
            "VIX >= 25"
        )

    elif vix < 18:

        support_score += 1

        supportive_flags.append(
            "VIX < 18"
        )

    # 10Y YIELD: 20D absolute change

    y10_change = metrics[
        "yield_10y"
    ].get("change_20d")

    if y10_change is None:

        unavailable.append("10y_20d_change")

    elif y10_change >= 0.20:

        risk_score += 1

        risk_flags.append(
            "10Y yield 20D increase >= 0.20 percentage points"
        )

    elif y10_change <= -0.20:

        support_score += 1

        supportive_flags.append(
            "10Y yield 20D decrease >= 0.20 percentage points"
        )

    # EQUITIES: 20D trend

    sp_change = metrics[
        "sp500"
    ].get("change_20d_percent")

    nq_change = metrics[
        "nasdaq"
    ].get("change_20d_percent")

    if sp_change is None or nq_change is None:

        unavailable.append("equity_20d_trend")

    elif sp_change <= -3 and nq_change <= -3:

        risk_score += 1

        risk_flags.append(
            "S&P 500 and Nasdaq both down 3% or more over 20D"
        )

    elif sp_change > 0 and nq_change > 0:

        support_score += 1

        supportive_flags.append(
            "S&P 500 and Nasdaq both positive over 20D"
        )

    # LABOR MARKET

    unemployment = metric_value(
        metrics,
        "unemployment"
    )

    payroll_change = metrics[
        "nonfarm_payrolls"
    ].get("monthly_change_thousands")

    if unemployment >= 5 or payroll_change < 0:

        risk_score += 1

        risk_flags.append(
            "Labor market deterioration"
        )

    elif unemployment < 4.5 and payroll_change > 0:

        support_score += 1

        supportive_flags.append(
            "Labor market comparatively stable"
        )

    # NET LIQUIDITY

    liquidity_change = liquidity.get(
        "change_30d"
    )

    if liquidity_change <= -50:

        risk_score += 1

        risk_flags.append(
            "US Net Liquidity 30D contraction >= $50B"
        )

    elif liquidity_change >= 50:

        support_score += 1

        supportive_flags.append(
            "US Net Liquidity 30D expansion >= $50B"
        )

    # YIELD CURVE

    if yield_curve.get("inverted"):

        risk_score += 1

        risk_flags.append(
            "10Y-2Y yield curve inverted"
        )

    # FINAL QUALITY CHECK

    if unavailable:

        decision = "WAIT — INSUFFICIENT DATA"

        analysis = "Derived Macro data incomplete."

        action = "Missing historical comparison সম্পূর্ণ না হওয়া পর্যন্ত বড় risk exposure নেবেন না।"

        risk = "Incomplete calculations থেকে পূর্ণাঙ্গ Macro assessment সম্ভব নয়।"

    elif risk_score >= 3:

        decision = "REDUCE RISK"

        analysis = "একাধিক স্বাধীন Macro category একই সময়ে risk pressure তৈরি করছে।"

        action = "ঝুঁকিপূর্ণ Altcoin exposure সীমিত রাখুন এবং নতুন BUY-তে সতর্ক থাকুন।"

        risk = "এটি চূড়ান্ত Crypto SELL signal নয়; BTC structure ও crypto-specific data প্রয়োজন।"

    elif risk_score >= 1:

        decision = "WAIT"

        analysis = "Macro environment-এ risk pressure রয়েছে, কিন্তু পূর্ণ Risk-Off confirmation নেই।"

        action = "নতুন বড় risk exposure নেওয়ার আগে BTC trend ও পরবর্তী Macro release পর্যবেক্ষণ করুন।"

        risk = "Supportive indicator থাকলেও risk pressure সম্পূর্ণ দূর হয়নি।"

    elif support_score >= 3:

        decision = "HOLD / SELECTIVE"

        analysis = "একাধিক Macro category তুলনামূলক supportive এবং উল্লেখযোগ্য risk flag নেই।"

        action = "Macro environment তুলনামূলক সহায়ক; BTC trend ও market breadth ছাড়া aggressive BUY নয়।"

        risk = "Macro support নিশ্চিত Crypto Bull Market signal নয়।"

    else:

        decision = "WAIT"

        analysis = "Macro signal এখনো যথেষ্ট শক্তিশালী নয়।"

        action = "Macro ও BTC trend-এর confirmation অপেক্ষা করুন।"

        risk = "কম Risk Score মানেই market risk অনুপস্থিত নয়।"

    return {

        "DATA": {

            "risk_score": risk_score,

            "support_score": support_score,

            "risk_flags": risk_flags,

            "supportive_flags": supportive_flags,

            "unavailable_calculations": unavailable,

            "risk_categories": 8,

            "model_type": "RULE_BASED_MULTI_FACTOR",

            "calibrated_probability": None
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

                result_key, result_metric, observations = future.result()

                metrics[result_key] = result_metric

                observations_by_key[result_key] = observations

                LOGGER.info(
                    "%s | %s | %s",
                    result_key,
                    result_metric["status"],
                    result_metric["observation_date"]
                )

            except Exception as error:

                LOGGER.error(
                    "%s fetch failed: %s",
                    key,
                    error
                )

                config = SERIES[key]

                metrics[key] = build_metric(
                    key,
                    config,
                    [],
                    "FRED"
                )

                metrics[key]["error"] = str(error)[:500]

                observations_by_key[key] = []

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
# DATA QUALITY
# ============================================================

def build_data_quality(metrics):

    critical_missing = [

        key for key in CRITICAL_SERIES

        if metrics.get(key, {}).get("status") != "OK"
    ]

    optional_unavailable = [

        key

        for key, item in metrics.items()

        if item.get("status") == "UNAVAILABLE"

        and key not in CRITICAL_SERIES
    ]

    stale = [

        key

        for key, item in metrics.items()

        if item.get("status") == "STALE"
    ]

    if critical_missing:

        quality = (

            "PARTIAL"

            if len(critical_missing) <= 5

            else "POOR"
        )

    elif stale:

        quality = "PARTIAL"

    elif optional_unavailable:

        quality = "GOOD_WITH_OPTIONAL_GAPS"

    else:

        quality = "GOOD"

    return {

        "data_quality": quality,

        "critical_missing": critical_missing,

        "optional_unavailable": optional_unavailable,

        "stale_metrics": stale,

        "critical_series_count": len(CRITICAL_SERIES),

        "critical_series_available": (

            len(CRITICAL_SERIES)
            - len(critical_missing)
        )
    }


# ============================================================
# SOURCE MODE
# ============================================================

def determine_source_mode(metrics):

    sources = {

        item.get("source")

        for item in metrics.values()

        if item.get("source") in (
            "FRED_API",
            "FRED_CSV_EXPORT"
        )
    }

    if sources == {"FRED_API"}:

        return "FRED API"

    if sources == {"FRED_CSV_EXPORT"}:

        return "FRED CSV export"

    if sources:

        return "FRED API with CSV fallback"

    return "FRED source unavailable"


# ============================================================
# BUILD PAYLOAD
# ============================================================

def build_payload():

    LOGGER.info(
        "Starting Macro Engine v%s",
        VERSION
    )

    metrics, observations = fetch_all_series()

    payroll_change = calculate_payroll_change(
        observations.get(
            "nonfarm_payrolls",
            []
        )
    )

    metrics["nonfarm_payrolls"][
        "monthly_change_thousands"
    ] = payroll_change

    inflation = build_inflation_report(
        metrics,
        observations
    )

    liquidity = build_liquidity_analysis(
        metrics,
        observations
    )

    yield_curve = build_yield_curve_analysis(
        metrics,
        observations
    )

    reports = build_indicator_reports(
        metrics,
        inflation,
        observations
    )

    overall = build_overall_decision(
        metrics,
        inflation,
        liquidity,
        yield_curve
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

    data_quality = build_data_quality(
        metrics
    )

    return {

        "schema_version": 2,

        "engine": "Crypto Macro Engine",

        "engine_version": VERSION,

        "fetched_at": iso_now(),

        "source": "Federal Reserve Economic Data (FRED)",

        "source_mode": determine_source_mode(metrics),

        "summary": {

            "total_series": len(metrics),

            "ok": ok_count,

            "stale": stale_count,

            "unavailable": unavailable_count,

            **data_quality
        },

        "metrics": metrics,

        "inflation": inflation,

        "liquidity": liquidity,

        "yield_curve": yield_curve,

        "reports": reports,

        "overall_macro_decision": overall,

        "limitations": [

            "DTWEXBGS is a broad trade-weighted USD proxy, not ICE DXY.",

            "FRED observations are released with delays.",

            "Freshness limits are series-specific.",

            "Gold is unavailable because no verified replacement source is configured.",

            "US Net Liquidity is a proxy calculated as WALCL - TGA - RRP.",

            "Net Liquidity is not a complete Global Liquidity Composite.",

            "Economic calendar forecast/actual/surprise is not integrated.",

            "BOJ policy and Japanese government bond yield curves are not integrated.",

            "JPY carry-trade risk model is not integrated.",

            "Crypto ETF flows are not integrated.",

            "BTC market structure and technical confirmation are not integrated.",

            "Crypto-specific on-chain data are not integrated.",

            "Rule-based Macro Risk Score is not a calibrated probability.",

            "Macro decision is not a standalone crypto trading signal."
        ],

        "not_integrated_yet": [

            "Economic calendar with verified forecast and actual",

            "BOJ policy and JGB yields",

            "JPY carry-trade risk model",

            "Global central-bank liquidity composite",

            "Verified live Gold market price source",

            "Crypto ETF flows",

            "BTC market structure and technical confirmation",

            "Crypto-specific on-chain data",

            "Macro event surprise analysis"
        ]
    }


# ============================================================
# PAYLOAD VALIDATION
# ============================================================

def validate_payload(payload):

    if not isinstance(payload, dict):

        raise ValueError(
            "Payload must be a dictionary."
        )

    if payload.get("engine_version") != VERSION:

        raise ValueError(
            "Incorrect engine version."
        )

    required_fields = (

        "summary",

        "metrics",

        "inflation",

        "liquidity",

        "yield_curve",

        "reports",

        "overall_macro_decision"
    )

    for key in required_fields:

        if key not in payload:

            raise ValueError(
                f"Missing payload field: {key}"
            )

    summary = payload["summary"]

    if not isinstance(summary, dict):

        raise ValueError(
            "Invalid summary object."
        )

    if (

        summary.get("ok", 0)

        + summary.get("stale", 0)

        + summary.get("unavailable", 0)

        != summary.get("total_series", -1)
    ):

        raise ValueError(
            "Series summary counts do not match."
        )

    metrics = payload["metrics"]

    if not isinstance(metrics, dict):

        raise ValueError(
            "Invalid metrics object."
        )

    for key, item in metrics.items():

        if not isinstance(item, dict):

            raise ValueError(
                f"Invalid metric object: {key}"
            )

        if item.get("status") not in (

            "OK",

            "STALE",

            "UNAVAILABLE"
        ):

            raise ValueError(
                f"Invalid metric status: {key}"
            )

        value = item.get("value")

        if value is not None:

            number = safe_number(value)

            if number is None:

                raise ValueError(
                    f"Invalid numeric value: {key}"
                )

    for key, report in payload["reports"].items():

        if not isinstance(report, dict):

            raise ValueError(
                f"Invalid report: {key}"
            )

        for field in (

            "DATA",

            "ANALYSIS",

            "DECISION",

            "ACTION",

            "RISK"
        ):

            if field not in report:

                raise ValueError(
                    f"Missing {field} in report {key}"
                )

    overall = payload["overall_macro_decision"]

    for field in (

        "DATA",

        "ANALYSIS",

        "DECISION",

        "ACTION",

        "RISK"
    ):

        if field not in overall:

            raise ValueError(
                f"Missing overall decision field: {field}"
            )

    json.dumps(
        payload,
        allow_nan=False
    )

    return True


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

        validate_payload(payload)

        save_json(payload)

        summary = payload["summary"]

        LOGGER.info(
            "Macro Engine completed | OK=%s | STALE=%s | UNAVAILABLE=%s",
            summary["ok"],
            summary["stale"],
            summary["unavailable"]
        )

        LOGGER.info(
            "Data quality: %s",
            summary["data_quality"]
        )

        LOGGER.info(
            "Critical series available: %s/%s",
            summary["critical_series_available"],
            summary["critical_series_count"]
        )

        LOGGER.info(
            "US Net Liquidity: %s",
            payload["liquidity"]["status"]
        )

        LOGGER.info(
            "Yield Curve: %s",
            payload["yield_curve"]["status"]
        )

        LOGGER.info(
            "Overall decision: %s",
            payload["overall_macro_decision"]["DECISION"]
        )

        LOGGER.info(
            "Output: %s",
            OUTPUT_FILE
        )

        # Partial data is written and reported.
        # Do not fail the whole scheduled workflow only
        # because one or more FRED series are unavailable.
        if summary["critical_missing"]:

            LOGGER.warning(
                "Critical missing series: %s",
                ", ".join(summary["critical_missing"])
            )

        return 0

    except Exception:

        LOGGER.exception(
            "Macro Engine failed"
        )

        return 1


if __name__ == "__main__":

    sys.exit(main())
