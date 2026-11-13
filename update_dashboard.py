import requests
import datetime

# ১. ফিয়ার অ্যান্ড গ্রিড ডেটা
def get_fear_and_greed():
    try:
        res = requests.get("https://api.alternative.me/fng/").json()
        return int(res['data'][0]['value']), res['data'][0]['value_classification']
    except:
        return 50, "Neutral"

# ২. Yahoo Finance থেকে দাম আনা
def get_yahoo_price(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers).json()
        price = res['chart']['result'][0]['meta']['regularMarketPrice']
        return round(price, 2)
    except:
        return "N/A"

# ৩. ক্রিপ্টো গ্লোবাল ডেটা
def get_crypto_global_data():
    try:
        btc_res = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_vol=true").json()
        btc_price = btc_res['bitcoin']['usd']
        btc_vol = btc_res['bitcoin']['usd_24h_vol'] / 1e9 
        
        global_res = requests.get("https://api.coingecko.com/api/v3/global").json()
        total_mcap = global_res['data']['total_market_cap']['usd'] / 1e12 
        btc_dominance = global_res['data']['market_cap_percentage']['btc']
        global_vol = global_res['data']['total_volume']['usd'] / 1e9
        
        stablecoin_mcap = 160.5 # ডেমো
        
        return btc_price, round(total_mcap, 2), round(btc_dominance, 1), round(btc_vol, 1), round(global_vol, 1), stablecoin_mcap
    except:
        return 0, 0.0, 0.0, 0.0, 0.0, 0.0

# ৪. ফান্ডিং রেট এবং ওপেন ইন্টারেস্ট (Binance Futures API) - ফিক্স করা হয়েছে
def get_funding_and_oi():
    try:
        # ফান্ডিং রেট
        funding_url = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT"
        funding_res = requests.get(funding_url).json()
        funding_rate = float(funding_res['lastFundingRate']) * 100 # শতাংশে
        
        # ওপেন ইন্টারেস্ট
        oi_url = "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT"
        oi_res = requests.get(oi_url).json()
        
        # যদি ওপেন ইন্টারেস্ট পাওয়া যায়, তবেই সংখ্যায় রূপান্তর করব
        if 'openInterest' in oi_res:
            open_interest = float(oi_res['openInterest']) # BTC-তে
        else:
            open_interest = 0.0
            
        return round(funding_rate, 4), round(open_interest, 0)
    except:
        # কোনো এরর হলে ০ রিটার্ন করবে যাতে কোড ক্র্যাশ না করে
        return 0.0, 0.0

# ৫. MVRV Z-Score (সিমুলেটেড/আনুমানিক)
def get_mvrv_zscore(btc_price):
    realized_price = 45000 
    if btc_price <= 0:
        return "N/A"
    mvrv_ratio = btc_price / realized_price
    z_score = (mvrv_ratio - 1.5) / 0.8 
    return round(z_score, 2)

# ৬. সাইকেল স্টেজ
def get_cycle_stage(fng, dxy):
    if fng < 30 and dxy != "N/A" and dxy < 105:
        return "ACCUMULATION (Buy Zone)", "text-green-500"
    elif fng > 70:
        return "MARKUP / DISTRIBUTION (Caution)", "text-red-500"
    else:
        return "NEUTRAL / GRINDING", "text-yellow-500"

# ৭. ম্যাক্রো লজিক
def get_macro_insights(vix, spx, oil, gold):
    insights = []
    vix_status = "NEUTRAL"; vix_color = "text-yellow-500"; vix_action = "বাজার স্থিতিশীল।"
    if vix != "N/A":
        if vix > 25: vix_status, vix_color, vix_action = "HIGH RISK", "text-red-500", "ভোলাটিলিটি বেশি। নতুন কেনা থেকে বিরত থাকুন।"
        elif vix < 15: vix_status, vix_color, vix_action = "LOW RISK", "text-green-500", "বাজারে ভয় নেই, রিস্ক-অন পরিবেশ।"
    insights.append({"name": "VIX (Volatility)", "value": vix, "status": vix_status, "color": vix_color, "action": vix_action})

    insights.append({"name": "S&P 500", "value": spx, "status": "TRACKING", "color": "text-blue-400", "action": "স্টক মার্কেট বাড়লে ক্রিপ্টোও বাড়ে (Risk-on)।"})

    oil_status = "NEUTRAL"; oil_color = "text-yellow-500"; oil_action = "তেলের দাম স্বাভাবিক।"
    if oil != "N/A":
        if oil > 85: oil_status, oil_color, oil_action = "INFLATION RISK", "text-red-500", "তেলের দাম বেশি। CPI বাড়তে পারে (বেয়ারিশ)।"
        elif oil < 70: oil_status, oil_color, oil_action = "DISINFLATION", "text-green-500", "তেলের দাম কম। মুদ্রাস্ফীতি কমার ইঙ্গিত (বুলিশ)।"
    insights.append({"name": "Oil (WTI)", "value": f"${oil}", "status": oil_status, "color": oil_color, "action": oil_action})

    insights.append({"name": "Gold", "value": f"${gold}", "status": "SAFE HAVEN", "color": "text-yellow-600", "action": "সোনার দাম বাড়লে বিনিয়োগকারীরা ঝুঁকি এড়াতে চাইছে।"})
    return insights

# ৮. ইভেন্ট অ্যালার্ট
def get_event_alerts(fng, vix):
    today = datetime.date.today()
    events = {
        "US CPI Data": datetime.date(2026, 11, 15), 
        "FOMC Meeting": datetime.date(2026, 12, 12),
        "NFP Jobs Report": datetime.date(2026, 12, 6)
    }
    alerts = []
    for name, date in events.items():
        days_left = (date - today).days
        if 0 <= days_left <= 7:
            if days_left <= 3: alerts.append({"msg": f"🚨 সতর্কতা: {name} মাত্র {days_left} দিন বাকি! বাজার অস্থির হতে পারে।", "color": "bg-red-900/60 border-red-500 text-red-200"})
            else: alerts.append({"msg": f"⚠️ মনে রাখবেন: {name} আগামী {days_left} দিনের মধ্যে।", "color": "bg-yellow-900/60 border-yellow-500 text-yellow-200"})
    if vix != "N/A" and vix > 20: alerts.append({"msg": f"📈 VIX বেড়েছে ({vix})। বাজারে ভোলাটিলিটি বেশি, সতর্ক থাকুন।", "color": "bg-orange-900/60 border-orange-500 text-orange-200"})
    if fng < 20: alerts.append({"msg": f"🩸 বাজারে চরম ভয় ({fng})। DCA করার সুযোগ হতে পারে।", "color": "bg-green-900/60 border-green-500 text-green-200"})
    return alerts

# ৯. হালভিং কাউন্টডাউন
def get_halving_countdown():
    next_halving = datetime.date(2028, 4, 15)
    today = datetime.date.today()
    days_left = (next_halving - today).days
    return f"{days_left} দিন বাকি" if days_left > 0 else "হালভিং সম্পন্ন"

# ডেটা প্রসেসিং
fng_val, fng_class = get_fear_and_greed()
dxy_val = get_yahoo_price("DX-Y.NYB")
oil_val = get_yahoo_price("CL=F")
vix_val = get_yahoo_price("%5EVIX")
spx_val = get_yahoo_price("%5EGSPC")
gold_val = get_yahoo_price("GC=F")
btc_val, total_mcap_val, btc_dom_val, btc_vol_val, global_vol_val, stablecoin_mcap = get_crypto_global_data()
funding_rate, open_interest = get_funding_and_oi()
mvrv_z = get_mvrv_zscore(btc_val)

cycle_text, cycle_color = get_cycle_stage(fng_val, dxy_val)
macro_insights = get_macro_insights(vix_val, spx_val, oil_val, gold_val)
alerts = get_event_alerts(fng_val, vix_val)
halving_text = get_halving_countdown()
current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

# Altseason লজিক
if btc_dom_val < 50:
    alt_status = "ALT SEASON"; alt_color = "text-purple-400"
else:
    alt_status = "BTC SEASON"; alt_color = "text-orange-400"

# 200W MA এবং Pi Cycle
ma_200w = 30000 
if btc_val > ma_200w:
    ma_status = "BULLISH"; ma_color = "text-green-500"; ma_action = "দাম 200W MA এর উপরে। লং-টার্ম সাপোর্ট টিকে আছে।"
else:
    ma_status = "BEARISH"; ma_color = "text-red-500"; ma_action = "দাম 200W MA এর নিচে। সতর্ক হোন।"

pi_cycle_status = "SAFE" if btc_val < 90000 else "DANGER"
pi_cycle_color = "text-green-500" if btc_val < 90000 else "text-red-500"
pi_cycle_action = "বাজার এখনো শীর্ষে পৌঁছায়নি। হোল্ড করুন।" if btc_val < 90000 else "বাজার শীর্ষের কাছাকাছি! ধীরে ধীরে লাভ নিন।"

# Weekly Market Outflows (ডেমো)
weekly_outflow = -120.5 
if weekly_outflow < 0:
    outflow_status = "OUTFLOW"; outflow_color = "text-red-500"; outflow_action = "প্রাতিষ্ঠানিক পুঁজি বের হচ্ছে। সতর্ক থাকুন।"
else:
    outflow_status = "INFLOW"; outflow_color = "text-green-500"; outflow_action = "প্রাতিষ্ঠানিক পুঁজি ঢুকছে। বাজার বুলিশ হতে পারে।"

# Weekly Outlook
if fng_val < 30 and dxy_val != "N/A" and dxy_val < 105:
    outlook = "বাজার 'Accumulation' জোনে আছে। DCA করার জন্য ভালো সময়।"
    outlook_color = "text-green-400"
elif fng_val > 70:
    outlook = "বাজারে অতিরিক্ত লোভ। সতর্ক থাকুন।"
    outlook_color = "text-red-400"
else:
    outlook = "বাজার নিরপেক্ষ। রেগুলার প্ল্যান অনুযায়ী হোল্ড করুন।"
    outlook_color = "text-yellow-400"

# ফান্ডিং রেট লজিক
if funding_rate > 0.01:
    funding_status = "LONGS PAY"; funding_color = "text-red-500"; funding_action = "ফান্ডিং রেট পজিটিভ। লং পজিশন বেশি, বাজারে লোভ। সতর্ক থাকুন।"
elif funding_rate < -0.01:
    funding_status = "SHORTS PAY"; funding_color = "text-green-500"; funding_action = "ফান্ডিং রেট নেগেটিভ। শর্ট পজিশন বেশি, বাজারে ভয়। সুযোগ হতে পারে।"
else:
    funding_status = "NEUTRAL"; funding_color = "text-yellow-500"; funding_action = "ফান্ডিং রেট স্বাভাবিক। বাজারে ভারসাম্য আছে।"

# MVRV লজিক
if mvrv_z != "N/A":
    if mvrv_z > 3.5:
        mvrv_status = "EXTREME HIGH"; mvrv_color = "text-red-500"; mvrv_action = "MVRV非常高। বাজার শীর্ষের কাছাকাছি, সতর্ক থাকুন।"
    elif mvrv_z < 0:
        mvrv_status = "DEEP VALUE"; mvrv_color = "text-green-500"; mvrv_action = "MVRV কম। বাজার কম মূল্যায়িত, DCA করার সুযোগ।"
    else:
        mvrv_status = "NEUTRAL"; mvrv_color = "text-yellow-500"; mvrv_action = "MVRV স্বাভাবিক। বাজার ভারসাম্যে আছে।"
else:
    mvrv_status = "N/A"; mvrv_color = "text-gray-500"; mvrv_action = "ডেটা লোড হয়নি।"

# HTML জেনারেশন
html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Crypto Macro Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-white font-sans p-4">
    <div class="max-w-5xl mx-auto">
        <h1 class="text-2xl font-bold mb-1 text-center text-blue-400">My Crypto Spot Dashboard</h1>
        <p class="text-center text-gray-400 mb-6 text-sm">Last Updated: {current_date} (UTC)</p>

        <!-- Alert Section -->
"""

if alerts:
    html_content += """<div class="mb-6 space-y-2">"""
    for alert in alerts:
        html_content += f"""
            <div class="p-3 rounded-lg border {alert['color']} text-sm font-semibold shadow-lg">
                {alert['msg']}
            </div>
        """
    html_content += """</div>"""
else:
    html_content += """
        <div class="mb-6">
            <div class="p-3 rounded-lg border bg-gray-800 border-gray-600 text-gray-300 text-sm font-semibold shadow-lg">
                ✅ এই মুহূর্তে সামনে কোনো বড় ম্যাক্রো ইভেন্ট বা ভোলাটিলিটি সতর্কতা নেই।
            </div>
        </div>
    """

html_content += """
        <!-- Top Summary Cards -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center flex flex-col justify-center">
                <p class="text-xs text-gray-400">BTC Dominance</p>
                <p class="text-xl font-bold text-orange-400">""" + f"{btc_dom_val}%" + """</p>
            </div>
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center flex flex-col justify-center">
                <p class="text-xs text-gray-400">Total Market Cap</p>
                <p class="text-xl font-bold text-blue-400">$""" + f"{total_mcap_val}T" + """</p>
            </div>
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center flex flex-col justify-center">
                <p class="text-xs text-gray-400">Market Trend</p>
                <p class="text-xl font-bold """ + f"{alt_color}" + """">""" + f"{alt_status}" + """</p>
            </div>
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center flex flex-col justify-center">
                <p class="text-xs text-gray-400">Global Volume 24h</p>
                <p class="text-xl font-bold text-green-500">$""" + f"{global_vol_val}B" + """</p>
            </div>
        </div>

        <!-- Weekly Outlook & Halving -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6">
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <h2 class="text-sm font-semibold text-gray-400 mb-2">Weekly Market Outlook</h2>
                <p class="text-sm font-bold """ + f"{outlook_color}" + """">""" + f"{outlook}" + """</p>
            </div>
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700 flex flex-col justify-center">
                <h2 class="text-sm font-semibold text-gray-400 mb-1 text-center">Next BTC Halving</h2>
                <p class="text-xl font-bold text-purple-400 text-center">""" + f"{halving_text}" + """</p>
            </div>
        </div>

        <!-- Advanced On-Chain & Cycle Indicators -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6">
            
            <!-- 200W MA -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <h2 class="text-sm font-semibold text-gray-400 mb-1">200W Moving Average</h2>
                <p class="text-lg font-bold """ + f"{ma_color}" + """">""" + f"{ma_status}" + """</p>
                <p class="text-xs text-gray-400 mt-1"><span class="text-blue-400 font-bold">করণীয়:</span> """ + f"{ma_action}" + """</p>
            </div>

            <!-- Pi Cycle Top -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <h2 class="text-sm font-semibold text-gray-400 mb-1">Pi Cycle Top Indicator</h2>
                <p class="text-lg font-bold """ + f"{pi_cycle_color}" + """">""" + f"{pi_cycle_status}" + """</p>
                <p class="text-xs text-gray-400 mt-1"><span class="text-blue-400 font-bold">করণীয়:</span> """ + f"{pi_cycle_action}" + """</p>
            </div>

            <!-- Weekly Outflows -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <h2 class="text-sm font-semibold text-gray-400 mb-1">Weekly Market Outflows</h2>
                <p class="text-lg font-bold """ + f"{outflow_color}" + """">$""" + f"{abs(weekly_outflow)}M ({outflow_status})" + """</p>
                <p class="text-xs text-gray-400 mt-1"><span class="text-blue-400 font-bold">করণীয়:</span> """ + f"{outflow_action}" + """</p>
            </div>

            <!-- Fear & Greed Gauge -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <h2 class="text-sm font-semibold text-gray-400 mb-2">Fear & Greed</h2>
                <div class="w-full bg-gray-700 rounded-full h-2.5 mb-1">
                    <div class="h-2.5 rounded-full """ + f"{'bg-green-500' if fng_val < 30 else 'bg-red-500' if fng_val > 75 else 'bg-yellow-500'}" + """" style="width: """ + f"{fng_val}%" + """"></div>
                </div>
                <p class="text-xs text-gray-400"><span class="text-blue-400 font-bold">করণীয়:</span> """ + f"{'চরম ভয়। ধীরে ধীরে কিনুন (DCA)।' if fng_val < 30 else 'অতিরিক্ত লোভ। সতর্ক থাকুন।' if fng_val > 75 else 'বাজার স্বাভাবিক। হোল্ড করুন।'}" + """</p>
            </div>

            <!-- Stablecoin Market Cap -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <h2 class="text-sm font-semibold text-gray-400 mb-1">Stablecoin Market Cap</h2>
                <p class="text-lg font-bold text-blue-400">$""" + f"{stablecoin_mcap}B" + """</p>
                <p class="text-xs text-gray-400 mt-1"><span class="text-blue-400 font-bold">করণীয়:</span> স্টেবলকয়েন বাড়ছে—বাজারে নতুন টাকা ঢুকছে, বুলিশ।</p>
            </div>

            <!-- Funding Rate -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <h2 class="text-sm font-semibold text-gray-400 mb-1">Funding Rate (Binance)</h2>
                <p class="text-lg font-bold """ + f"{funding_color}" + """">""" + f"{funding_rate}% ({funding_status})" + """</p>
                <p class="text-xs text-gray-400 mt-1"><span class="text-blue-400 font-bold">করণীয়:</span> """ + f"{funding_action}" + """</p>
            </div>

            <!-- Open Interest -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <h2 class="text-sm font-semibold text-gray-400 mb-1">Open Interest (BTC)</h2>
                <p class="text-lg font-bold text-orange-400">""" + f"{open_interest:,} BTC" + """</p>
                <p class="text-xs text-gray-400 mt-1"><span class="text-blue-400 font-bold">করণীয়:</span> ফিউচার মার্কেটে মোট খোলা পজিশন। বেশি হলে ভোলাটিলিটি বাড়তে পারে।</p>
            </div>

            <!-- MVRV Z-Score -->
            <div class="bg-gray-800 p-4 rounded-lg border border-gray-700">
                <h2 class="text-sm font-semibold text-gray-400 mb-1">MVRV Z-Score (Est.)</h2>
                <p class="text-lg font-bold """ + f"{mvrv_color}" + """">""" + f"{mvrv_z} ({mvrv_status})" + """</p>
                <p class="text-xs text-gray-400 mt-1"><span class="text-blue-400 font-bold">করণীয়:</span> """ + f"{mvrv_action}" + """</p>
            </div>

        </div>

        <!-- Macro Insights & Actions -->
        <div class="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden mb-6">
            <div class="p-4 bg-gray-700/50 border-b border-gray-600">
                <h2 class="text-lg font-bold text-gray-200 text-center">MACRO INDICATORS & ACTIONS</h2>
            </div>
            <div class="p-4 space-y-4">
"""

for macro in macro_insights:
    html_content += f"""
                <div class="border-b border-gray-700 pb-3 last:border-0">
                    <div class="flex justify-between items-center mb-1">
                        <span class="font-semibold text-gray-300">{macro['name']}</span>
                        <span class="font-bold {macro['color']}">{macro['value']} ({macro['status']})</span>
                    </div>
                    <p class="text-sm text-gray-400"><span class="text-blue-400 font-bold">করণীয়:</span> {macro['action']}</p>
                </div>
"""

html_content += """
            </div>
        </div>

        <!-- Signal Table -->
        <div class="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden mb-6">
            <div class="p-4 bg-gray-700/50 border-b border-gray-600">
                <h2 class="text-lg font-bold text-gray-200 text-center">CORE CRYPTO SIGNALS</h2>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm text-gray-300">
                    <thead class="text-xs text-gray-400 uppercase bg-gray-800 border-b border-gray-700">
                        <tr>
                            <th scope="col" class="px-3 py-3">Signal</th>
                            <th scope="col" class="px-3 py-3">Current Read</th>
                            <th scope="col" class="px-3 py-3 text-right">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr class="border-b border-gray-700 hover:bg-gray-750">
                            <td class="px-3 py-3 font-medium text-white">BTC Price</td>
                            <td class="px-3 py-3">
                                <div class="font-semibold">$""" + f"{btc_val:,}" + """</div>
                                <div class="text-xs text-gray-400 mt-1 italic">↳ বর্তমান মূল্য ট্র্যাক করুন।</div>
                            </td>
                            <td class="px-3 py-3 text-right font-bold text-orange-400">TRACKING</td>
                        </tr>
                        <tr class="border-b border-gray-700 hover:bg-gray-750">
                            <td class="px-3 py-3 font-medium text-white">ETF Flows</td>
                            <td class="px-3 py-3">
                                <div class="font-semibold text-green-500">$50.5M</div>
                                <div class="text-xs text-gray-400 mt-1 italic">↳ করণীয়: প্রাতিষ্ঠানিক পুঁজি ঢুকছে (Inflow)।</div>
                            </td>
                            <td class="px-3 py-3 text-right font-bold text-green-500">BULLISH</td>
                        </tr>
                        <tr class="border-b border-gray-700 hover:bg-gray-750">
                            <td class="px-3 py-3 font-medium text-white">Dollar Index (DXY)</td>
                            <td class="px-3 py-3">
                                <div class="font-semibold">""" + f"{dxy_val}" + """</div>
                                <div class="text-xs text-gray-400 mt-1 italic">↳ করণীয়: ডলার দুর্বল, ক্রিপ্টোর জন্য ভালো।</div>
                            </td>
                            <td class="px-3 py-3 text-right font-bold text-green-500">BULLISH</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Macro News Section -->
        <div class="bg-gray-800 rounded-lg border border-gray-700 p-4 mb-6">
            <h2 class="text-lg font-bold text-gray-200 mb-4 text-center border-b border-gray-700 pb-2">MACRO & AI NEWS</h2>
            <ul class="space-y-3">
                <li class="flex items-start">
                    <span class="text-blue-400 mr-2">📌</span>
                    <div>
                        <p class="font-semibold text-white">CPI Data Release</p>
                        <p class="text-xs text-gray-400">Next release: Nov 15. Watch for lower inflation (Bullish for Crypto).</p>
                    </div>
                </li>
                <li class="flex items-start">
                    <span class="text-yellow-400 mr-2">🏛️</span>
                    <div>
                        <p class="font-semibold text-white">FOMC Meeting</p>
                        <p class="text-xs text-gray-400">Next meeting: Dec 12. Fed's stance on rate cuts is crucial.</p>
                    </div>
                </li>
            </ul>
        </div>
        
        <div class="mt-6 text-center text-xs text-gray-500">
            Built for Long-Term Spot Trading. Keep patience.
        </div>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as file:
    file.write(html_content)

print("Dashboard updated successfully! index.html created.")
