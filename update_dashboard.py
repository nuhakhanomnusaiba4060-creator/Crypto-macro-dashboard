import requests
import datetime

# ১. ফিয়ার অ্যান্ড গ্রিড ডেটা
def get_fear_and_greed():
    try:
        res = requests.get("https://api.alternative.me/fng/").json()
        return int(res['data'][0]['value']), res['data'][0]['value_classification']
    except:
        return 50, "Neutral"

# ২. Yahoo Finance থেকে একটি সূচকের দাম আনা
def get_yahoo_price(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers).json()
        price = res['chart']['result'][0]['meta']['regularMarketPrice']
        return round(price, 2)
    except:
        return "N/A"

# ৩. বিটকয়েনের দাম এবং গ্লোবাল মার্কেট ডেটা
def get_crypto_global_data():
    try:
        btc_res = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd").json()
        btc_price = btc_res['bitcoin']['usd']
        global_res = requests.get("https://api.coingecko.com/api/v3/global").json()
        total_mcap = global_res['data']['total_market_cap']['usd'] / 1e12
        btc_dominance = global_res['data']['market_cap_percentage']['btc']
        return btc_price, round(total_mcap, 2), round(btc_dominance, 1)
    except:
        return 0, 0.0, 0.0

# ৪. সাইকেল স্টেজ
def get_cycle_stage(fng, dxy):
    if fng < 30 and dxy != "N/A" and dxy < 105:
        return "ACCUMULATION (Buy Zone)", "text-green-500"
    elif fng > 70:
        return "MARKUP / DISTRIBUTION (Caution)", "text-red-500"
    else:
        return "NEUTRAL / GRINDING", "text-yellow-500"

# ৫. ম্যাক্রো লজিক এবং করণীয় (VIX, S&P, Oil, Gold)
def get_macro_insights(vix, spx, oil, gold):
    insights = []
    
    # VIX (ভোলাটিলিটি)
    vix_status = "NEUTRAL"
    vix_color = "text-yellow-500"
    vix_action = "বাজার স্থিতিশীল। ক্রিপ্টোতে বড় কোনো ঝাঁকুনি নেই।"
    if vix != "N/A":
        if vix > 25:
            vix_status, vix_color = "HIGH RISK", "text-red-500"
            vix_action = "ভোলাটিলিটি বেশি। নতুন কেনা থেকে বিরত থাকুন, বাজার পতনের ঝুঁকিতে থাকতে পারে।"
        elif vix < 15:
            vix_status, vix_color = "LOW RISK", "text-green-500"
            vix_action = "বাজারে ভয় নেই, রিস্ক-অন (Risk-on) পরিবেশ। ক্রিপ্টোর জন্য ভালো।"
    
    insights.append({"name": "VIX (Volatility)", "value": vix, "status": vix_status, "color": vix_color, "action": vix_action})

    # S&P 500 (স্টক মার্কেট)
    spx_status = "TRACKING"
    spx_color = "text-blue-400"
    spx_action = "স্টক মার্কেট ট্র্যাক করুন। S&P 500 বাড়লে সাধারণত ক্রিপ্টোও বাড়ে (Risk-on)।"
    insights.append({"name": "S&P 500", "value": spx, "status": spx_status, "color": spx_color, "action": spx_action})

    # Oil (মুদ্রাস্ফীতি)
    oil_status = "NEUTRAL"
    oil_color = "text-yellow-500"
    oil_action = "তেলের দাম স্বাভাবিক। মুদ্রাস্ফীতিতে বড় ধাক্কা নেই।"
    if oil != "N/A":
        if oil > 85:
            oil_status, oil_color = "INFLATION RISK", "text-red-500"
            oil_action = "তেলের দাম বেশি। এর ফলে CPI বাড়তে পারে, যা ফেডের সুদহার কমানো আটকে দিতে পারে (বেয়ারিশ)।"
        elif oil < 70:
            oil_status, oil_color = "DISINFLATION", "text-green-500"
            oil_action = "তেলের দাম কম। মুদ্রাস্ফীতি কমার ইঙ্গিত, যা ফেডের সুদহার কমানোর পথ সহজ করবে (বুলিশ)।"
    insights.append({"name": "Oil (WTI)", "value": f"${oil}", "status": oil_status, "color": oil_color, "action": oil_action})

    # Gold (সেফ হেভেন)
    gold_status = "SAFE HAVEN"
    gold_color = "text-yellow-600"
    gold_action = "সোনার দাম বাড়লে বোঝায় বিনিয়োগকারীরা ঝুঁকি এড়াতে চাইছে। এটি ক্রিপ্টোর জন্য কিছুটা নেতিবাচক হতে পারে।"
    insights.append({"name": "Gold", "value": f"${gold}", "status": gold_status, "color": gold_color, "action": gold_action})

    return insights

# ডেটা প্রসেসিং
fng_val, fng_class = get_fear_and_greed()
dxy_val = get_yahoo_price("DX-Y.NYB")
oil_val = get_yahoo_price("CL=F")
vix_val = get_yahoo_price("%5EVIX")
spx_val = get_yahoo_price("%5EGSPC")
gold_val = get_yahoo_price("GC=F") # Gold Futures
btc_val, total_mcap_val, btc_dom_val = get_crypto_global_data()

cycle_text, cycle_color = get_cycle_stage(fng_val, dxy_val)
macro_insights = get_macro_insights(vix_val, spx_val, oil_val, gold_val)
current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

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

        <!-- Top Summary Cards -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center">
                <p class="text-xs text-gray-400">BTC Price</p>
                <p class="text-xl font-bold text-orange-400">${btc_val:,}</p>
            </div>
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center">
                <p class="text-xs text-gray-400">Fear & Greed</p>
                <p class="text-xl font-bold { 'text-green-500' if fng_val < 30 else 'text-red-500' if fng_val > 75 else 'text-yellow-500' }">{fng_val}</p>
            </div>
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center">
                <p class="text-xs text-gray-400">DXY</p>
                <p class="text-xl font-bold { 'text-green-500' if dxy_val != 'N/A' and dxy_val < 105 else 'text-red-500' if dxy_val != 'N/A' else 'text-gray-500' }">{dxy_val}</p>
            </div>
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center">
                <p class="text-xs text-gray-400">ETF Flow</p>
                <p class="text-xl font-bold text-green-500">$50.5M</p>
            </div>
        </div>

        <!-- Cycle Stage Banner -->
        <div class="bg-gray-800 p-4 rounded-lg border border-gray-700 mb-6 text-center">
            <h2 class="text-sm font-semibold text-gray-400 mb-1">Current Cycle Stage</h2>
            <p class="text-2xl font-bold {cycle_color}">{cycle_text}</p>
        </div>

        <!-- Macro Insights & Actions (নতুন সেকশন) -->
        <div class="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden mb-6">
            <div class="p-4 bg-gray-700/50 border-b border-gray-600">
                <h2 class="text-lg font-bold text-gray-200 text-center">MACRO INDICATORS & ACTIONS</h2>
            </div>
            <div class="p-4 space-y-4">
"""

# ম্যাক্রো ইনসাইট লুপ
for macro in macro_insights:
    html_content += f"""
                <div class="border-b border-gray-700 pb-3 last:border-0">
                    <div class="flex justify-between items-center mb-1">
                        <span class="font-semibold text-gray-300">{macro['name']}</span>
                        <span class="font-bold {macro['color']}">{macro['value']} ({macro['status']})</span>
                    </div>
                    <p class="text-sm text-gray-400"><span class="text-blue-400 font-bold">করণীয়:</span> {macro['action']}</p>
                </div>
"""

html_content += """
            </div>
        </div>

        <!-- Signal Table (আপনার আগের টেবিল) -->
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
                        <!-- ১. Price Structure -->
                        <tr class="border-b border-gray-700 hover:bg-gray-750">
                            <td class="px-3 py-3 font-medium text-white">Price Structure</td>
                            <td class="px-3 py-3">
                                <div class="font-semibold">$""" + f"{btc_val:,}" + """</div>
                                <div class="text-xs text-gray-500">Holding above key support</div>
                                <div class="text-xs text-gray-400 mt-1 italic">↳ মার্কেট সাপোর্টের উপরে আছে, বড় পতন নেই।</div>
                            </td>
                            <td class="px-3 py-3 text-right font-bold text-yellow-500">NEUTRAL</td>
                        </tr>
                        <!-- ২. ETF Flow -->
                        <tr class="border-b border-gray-700 hover:bg-gray-750">
                            <td class="px-3 py-3 font-medium text-white">ETF Flows</td>
                            <td class="px-3 py-3">
                                <div class="font-semibold">$50.5M</div>
                                <div class="text-xs text-gray-500">Institutional Demand</div>
                                <div class="text-xs text-gray-400 mt-1 italic">↳ প্রাতিষ্ঠানিক পুঁজি ঢুকছে (Inflow)।</div>
                            </td>
                            <td class="px-3 py-3 text-right font-bold text-green-500">BULLISH</td>
                        </tr>
                        <!-- ৩. Market Sentiment -->
                        <tr class="border-b border-gray-700 hover:bg-gray-750">
                            <td class="px-3 py-3 font-medium text-white">Market Sentiment</td>
                            <td class="px-3 py-3">
                                <div class="font-semibold">""" + f"{fng_val} ({fng_class})" + """</div>
                                <div class="text-xs text-gray-500">Retail Mania / Fear</div>
                                <div class="text-xs text-gray-400 mt-1 italic">↳ ফিয়ার অ্যান্ড গ্রিড """ + f"{fng_val}, " + """অর্থাৎ বাজারে """ + f"{'ভয়' if fng_val < 30 else 'লোভ' if fng_val > 75 else 'স্বাভাবিক অবস্থা'}" + """।</div>
                            </td>
                            <td class="px-3 py-3 text-right font-bold text-green-500">BUY</td>
                        </tr>
                        <!-- ৪. DXY -->
                        <tr class="border-b border-gray-700 hover:bg-gray-750">
                            <td class="px-3 py-3 font-medium text-white">Dollar Index (DXY)</td>
                            <td class="px-3 py-3">
                                <div class="font-semibold">""" + f"{dxy_val}" + """</div>
                                <div class="text-xs text-gray-500">Macro Liquidity</div>
                                <div class="text-xs text-gray-400 mt-1 italic">↳ ডলার দুর্বল, যা ক্রিপ্টোর জন্য ভালো।</div>
                            </td>
                            <td class="px-3 py-3 text-right font-bold text-green-500">BULLISH</td>
                        </tr>
                        <!-- ৫. BTC Dominance -->
                        <tr class="border-b border-gray-700 hover:bg-gray-750">
                            <td class="px-3 py-3 font-medium text-white">Market Breadth</td>
                            <td class="px-3 py-3">
                                <div class="font-semibold">""" + f"{btc_dom_val}%" + """</div>
                                <div class="text-xs text-gray-500">BTC Dominance</div>
                                <div class="text-xs text-gray-400 mt-1 italic">↳ বিটকয়েন ও অল্টকয়েনে টাকা ভাগ হয়ে আছে।</div>
                            </td>
                            <td class="px-3 py-3 text-right font-bold text-yellow-500">MIXED</td>
                        </tr>
                        <!-- ৬. Total Market Cap -->
                        <tr class="border-b border-gray-700 hover:bg-gray-750">
                            <td class="px-3 py-3 font-medium text-white">Total Market Cap</td>
                            <td class="px-3 py-3">
                                <div class="font-semibold">$""" + f"{total_mcap_val}T" + """</div>
                                <div class="text-xs text-gray-500">Overall Crypto Health</div>
                                <div class="text-xs text-gray-400 mt-1 italic">↳ পুরো ক্রিপ্টো মার্কেটের সামগ্রিক মূলধন।</div>
                            </td>
                            <td class="px-3 py-3 text-right font-bold text-blue-400">NEUTRAL</td>
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
                <li class="flex items-start">
                    <span class="text-purple-400 mr-2">🤖</span>
                    <div>
                        <p class="font-semibold text-white">AI News / Trends</p>
                        <p class="text-xs text-gray-400">AI sector developments may affect tech stocks and risk sentiment. Update manually as needed.</p>
                    </div>
                </li>
            </ul>
            <p class="text-xs text-gray-500 mt-4 text-center italic">*Note: News section is manually updated.</p>
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
