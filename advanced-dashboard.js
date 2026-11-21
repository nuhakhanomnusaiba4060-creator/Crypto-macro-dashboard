
/* =====================================================
   CRYPTO MACRO DASHBOARD — ADVANCED MODULE
   বাংলা UI | Verified JSON Data | Spot Investor
   ===================================================== */

(() => {
  "use strict";

  if (document.getElementById("advancedCryptoDashboard")) return;

  const DATA_URL = "./data/advanced_data.json";

  const style = document.createElement("style");
  style.textContent = `
    #advancedCryptoDashboard {
      margin-top:28px;
      color:#e8f0fa;
      font-family:Arial,"Noto Sans Bengali",sans-serif;
    }
    #advancedCryptoDashboard .adv-title {
      font-size:17px;font-weight:bold;
      margin:25px 0 12px;
      border-left:3px solid #3988ff;
      padding-left:10px;
    }
    #advancedCryptoDashboard .adv-grid {
      display:grid;
      grid-template-columns:repeat(auto-fit,minmax(210px,1fr));
      gap:10px;
    }
    #advancedCryptoDashboard .adv-card {
      background:#101e30;border:1px solid #263951;
      border-radius:10px;padding:13px;min-width:0;
    }
    #advancedCryptoDashboard .adv-name {
      color:#91a4bb;font-size:12px;margin-bottom:8px;
    }
    #advancedCryptoDashboard .adv-value {
      font-size:19px;font-weight:bold;overflow-wrap:anywhere;
    }
    #advancedCryptoDashboard .adv-detail {
      font-size:11px;color:#bdcada;line-height:1.7;margin-top:9px;
    }
    #advancedCryptoDashboard .adv-detail b {color:#e8f0fa}
    #advancedCryptoDashboard .good {color:#16c784}
    #advancedCryptoDashboard .bad {color:#ea3943}
    #advancedCryptoDashboard .warn {color:#f0b90b}
    #advancedCryptoDashboard .adv-table-wrap {
      overflow-x:auto;background:#101e30;
      border:1px solid #263951;border-radius:10px;
    }
    #advancedCryptoDashboard table {
      width:100%;min-width:520px;border-collapse:collapse;font-size:12px;
    }
    #advancedCryptoDashboard th,
    #advancedCryptoDashboard td {
      padding:9px;text-align:left;border-bottom:1px solid #263951;
    }
    #advancedCryptoDashboard th {color:#91a4bb}
    #advancedCryptoDashboard .adv-form {
      display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));
      gap:9px;margin-top:12px;
    }
    #advancedCryptoDashboard input {
      width:100%;padding:10px;background:#07111f;
      border:1px solid #34445b;border-radius:7px;color:white;
      box-sizing:border-box;
    }
    #advancedCryptoDashboard button {
      margin-top:10px;padding:10px 14px;background:#3988ff;
      border:0;border-radius:7px;color:white;font-weight:bold;
    }
    #advancedCryptoDashboard .adv-status {
      display:inline-block;padding:4px 7px;border-radius:5px;
      background:#1c3049;font-size:10px;margin-top:5px;
    }
  `;
  document.head.appendChild(style);

  const root = document.createElement("section");
  root.id = "advancedCryptoDashboard";

  root.innerHTML = `
    <div class="adv-title">১১. অতিরিক্ত On-chain তথ্য</div>
    <div class="adv-grid" id="advOnchain"></div>

    <div class="adv-title">১২. Bitcoin Halving পর্যবেক্ষণ</div>
    <div class="adv-grid" id="advHalving"></div>

    <div class="adv-title">১৩. Spot Order Book ও ক্রয়-বিক্রির চাপ</div>
    <div class="adv-grid" id="advOrderbook"></div>

    <div class="adv-title">১৪. Futures বাজারের ঝুঁকি পর্যবেক্ষণ</div>
    <div class="adv-detail">
      এগুলো Cross-exchange Futures তথ্য। Spot কেনাবেচার সংকেত নয়।
    </div>
    <div class="adv-grid" id="advDerivatives"></div>

    <div class="adv-title">১৫. ব্যক্তিগত Spot Portfolio হিসাব</div>
    <div class="adv-card">
      <div class="adv-detail">
        আপনার Coin, পরিমাণ, গড় ক্রয়মূল্য ও বর্তমান মূল্য লিখুন।
        হিসাব শুধু এই ব্রাউজারে হবে। কোনো API Key বা Wallet Password লাগবে না।
      </div>
      <div class="adv-form">
        <input id="advCoin" placeholder="Coin (যেমন BTC)">
        <input id="advQty" type="number" min="0" step="any" placeholder="পরিমাণ">
        <input id="advAvg" type="number" min="0" step="any" placeholder="গড় ক্রয়মূল্য USD">
        <input id="advPrice" type="number" min="0" step="any" placeholder="বর্তমান মূল্য USD">
      </div>
      <button id="advCalculate" type="button">লাভ / ক্ষতি হিসাব করুন</button>
      <div id="advPortfolioResult" class="adv-detail" aria-live="polite"></div>
    </div>

    <div class="adv-detail" id="advUpdated"></div>
  `;

  const main = document.querySelector("main");
  (main || document.body).appendChild(root);

  const $ = id => document.getElementById(id);
  const missing = "তথ্য পাওয়া যায়নি";

  function valid(v) {
    return v !== null && v !== undefined && v !== "" &&
      Number.isFinite(Number(v));
  }

  function n(v, digits = 2) {
    if (!valid(v)) return missing;
    return Number(v).toLocaleString("en-US", {
      maximumFractionDigits: digits
    });
  }

  function compactUSD(v) {
    if (!valid(v)) return missing;
    const x = Number(v);
    const a = Math.abs(x);
    if (a >= 1e12) return "$" + n(x / 1e12, 2) + " ট্রিলিয়ন";
    if (a >= 1e9) return "$" + n(x / 1e9, 2) + " বিলিয়ন";
    if (a >= 1e6) return "$" + n(x / 1e6, 2) + " মিলিয়ন";
    return "$" + n(x, 2);
  }

  function itemValue(obj) {
    if (!obj || obj.status !== "OK" || !valid(obj.value)) return null;
    return Number(obj.value);
  }

  function card(container, title, value, details, tone = "") {
    const el = $(container);
    if (!el) return;

    const box = document.createElement("div");
    box.className = "adv-card";

    const name = document.createElement("div");
    name.className = "adv-name";
    name.textContent = title;

    const val = document.createElement("div");
    val.className = "adv-value " + tone;
    val.textContent = value;

    const detail = document.createElement("div");
    detail.className = "adv-detail";
    detail.textContent = details;

    box.append(name, val, detail);
    el.appendChild(box);
  }

  function explainRatio(v) {
    if (v === null) return "যাচাইকৃত মান পাওয়া যায়নি।";
    if (v < 1) return "MVRV ১-এর নিচে: বাজারমূল্য Realized Value-এর নিচে। ঐতিহাসিকভাবে কম মূল্যায়নের অঞ্চল হতে পারে, তবে Bottom নিশ্চিত নয়।";
    if (v < 2) return "MVRV ১–২: বাজারমূল্য Realized Value-এর ওপরে। একে একা অতিরিক্ত মূল্যায়ন বলা যায় না।";
    return "MVRV ২ বা বেশি: বাজারমূল্য Realized Value-এর তুলনায় বেশি। অন্যান্য সূচকের সঙ্গে মূল্যায়ন করুন।";
  }

  function addOnchain(data) {
    const on = data.on_chain || {};

    const mvrv = itemValue(on.mvrv_ratio);
    card(
      "advOnchain",
      "Bitcoin MVRV Ratio",
      n(mvrv, 3),
      "এটি Market Value বনাম Realized Value-এর অনুপাত। " +
      explainRatio(mvrv),
      mvrv !== null && mvrv < 1 ? "good" : "warn"
    );

    const hash = itemValue(on.hashrate);
    card(
      "advOnchain",
      "Bitcoin Network Hashrate",
      hash === null ? missing : n(hash / 1e18, 2) + " EH/s",
      "মাইনিং নেটওয়ার্কের মোট গণনাশক্তি। দীর্ঘমেয়াদে নেটওয়ার্ক নিরাপত্তা ও অংশগ্রহণ বোঝাতে সহায়ক।",
      "good"
    );

    const difficulty = itemValue(on.mining_difficulty);
    card(
      "advOnchain",
      "Mining Difficulty",
      difficulty === null ? missing : n(difficulty / 1e12, 2) + " ট্রিলিয়ন",
      "নতুন Bitcoin ব্লক তৈরি করতে কতটা গণনাগত কঠিনতা রয়েছে তা বোঝায়। এটি সরাসরি BUY/SELL সংকেত নয়।"
    );

    const unavailableFields = [
      ["NUPL", on.nupl],
      ["Exchange Netflow", on.exchange_netflow],
      ["Whale Activity", on.whale_activity],
      ["MVRV Z-Score", on.mvrv_z_score]
    ];

    unavailableFields.forEach(([name, obj]) => {
      if (itemValue(obj) !== null) {
        card(
          "advOnchain",
          name,
          n(itemValue(obj), 3),
          "উৎসের যাচাইকৃত মান পাওয়া গেছে। ব্যাখ্যার জন্য আলাদা ঐতিহাসিক সীমা ও trend প্রয়োজন।"
        );
      }
    });
  }

  function addHalving(data) {
    const h = data.halving || {};

    if (h.status !== "OK") {
      card("advHalving", "Bitcoin Halving", missing,
        "যাচাইকৃত Halving তথ্য পাওয়া যায়নি।");
      return;
    }

    card("advHalving", "বর্তমান Block Height",
      n(h.current_block_height, 0),
      "Mempool.space তথ্য");

    card("advHalving", "পরবর্তী Halving Block",
      n(h.next_halving_block, 0),
      "Halving নির্ধারিত হয় Block Height অনুযায়ী।");

    card("advHalving", "বাকি Block",
      n(h.blocks_remaining, 0),
      "পরবর্তী Halving পর্যন্ত আনুমানিক অবশিষ্ট Block।");

    card("advHalving", "আনুমানিক সময়",
      valid(h.estimated_days_remaining)
        ? n(h.estimated_days_remaining, 0) + " দিন"
        : missing,
      "Block উৎপাদনের গতি অনুযায়ী সময় পরিবর্তিত হতে পারে।",
      "warn"
    );
  }

  function addOrderbook(data) {
    const book = data.spot_order_book || {};
    const taker = data.spot_taker_activity || {};

    ["BTCUSDT", "ETHUSDT"].forEach(symbol => {
      const label = symbol === "BTCUSDT" ? "Bitcoin" : "Ethereum";
      const b = book[symbol] || {};
      const t = taker[symbol] || {};

      const imbalance = itemValue(b.imbalance_percent);
      card(
        "advOrderbook",
        label + " Spot Order Book Imbalance",
        imbalance === null ? missing : n(imbalance, 2) + "%",
        "অর্ডার বুকের Bid ও Ask-এর ভারসাম্য। এটি snapshot; বড় অর্ডার দ্রুত সরিয়ে নেওয়া হতে পারে।",
        imbalance !== null && imbalance > 0 ? "good" : "warn"
      );

      const bid = itemValue(b.bid_value_usdt);
      card(
        "advOrderbook",
        label + " Bid Liquidity",
        compactUSD(bid),
        "দেখানো Order Book-এ ক্রয় অর্ডারের আনুমানিক মূল্য।"
      );

      const ask = itemValue(b.ask_value_usdt);
      card(
        "advOrderbook",
        label + " Ask Liquidity",
        compactUSD(ask),
        "দেখানো Order Book-এ বিক্রয় অর্ডারের আনুমানিক মূল্য।"
      );

      const ratio = itemValue(t.taker_buy_sell_ratio);
      card(
        "advOrderbook",
        label + " ১৫ মিনিটের Taker Buy/Sell",
        ratio === null ? missing : n(ratio, 3),
        ratio === null
          ? "যাচাইকৃত তথ্য পাওয়া যায়নি।"
          : ratio > 1
            ? "এই ক্যান্ডেলে Taker Buy Volume বেশি। এটি স্বল্পমেয়াদি ক্রয়চাপের ইঙ্গিত; একা Trend Reversal নিশ্চিত করে না।"
            : "এই ক্যান্ডেলে Taker Sell Volume বেশি। স্বল্পমেয়াদি বিক্রির চাপ রয়েছে।",
        ratio !== null && ratio > 1 ? "good" : "warn"
      );
    });
  }

  function addDerivatives(data) {
    const all = data.derivatives || {};

    ["BTCUSDT", "ETHUSDT"].forEach(symbol => {
      const label = symbol === "BTCUSDT" ? "Bitcoin" : "Ethereum";
      const d = all[symbol] || {};

      const oi = itemValue(d.open_interest_usd);
      card(
        "advDerivatives",
        label + " Futures Open Interest",
        compactUSD(oi),
        "Cross-exchange Futures-এর মোট Open Interest। এটি Spot Holdings নয়।"
      );

      const funding = itemValue(d.last_funding_rate);
      card(
        "advDerivatives",
        label + " সর্বশেষ Funding Rate",
        funding === null ? missing : n(funding * 100, 5) + "%",
        "প্রতি ৮ ঘণ্টার হার। এটি Futures বাজারের অবস্থান বোঝায়, Spot কেনার সংকেত নয়।"
      );

      const longShort = itemValue(d.global_long_short_ratio);
      card(
        "advDerivatives",
        label + " Futures Long/Short Ratio",
        n(longShort, 3),
        longShort === null
          ? "যাচাইকৃত তথ্য পাওয়া যায়নি।"
          : "১-এর বেশি হলে Long অ্যাকাউন্ট তুলনামূলক বেশি; অতিরিক্ত একদিকে অবস্থান থাকলে squeeze risk তৈরি হতে পারে।"
      );

      const longPct = itemValue(d.global_long_percent);
      card(
        "advDerivatives",
        label + " Futures Long Account",
        longPct === null ? missing : n(longPct, 2) + "%",
        "Cross-exchange account distribution; Spot buyer percentage নয়।"
      );

      const consistency = d.funding_apr_consistency;
      if (consistency && consistency !== "MATCH") {
        card(
          "advDerivatives",
          label + " Funding Data Quality",
          "অমিল পাওয়া গেছে",
          "Provider APR ও গণনা করা APR-এর মধ্যে অমিল আছে। Funding APR দিয়ে সিদ্ধান্ত নেবেন না।",
          "warn"
        );
      }
    });
  }

  function setupPortfolio() {
    $("advCalculate").addEventListener("click", () => {
      const coin = $("advCoin").value.trim().toUpperCase();
      const qty = Number($("advQty").value);
      const avg = Number($("advAvg").value);
      const price = Number($("advPrice").value);
      const out = $("advPortfolioResult");

      if (!coin || !Number.isFinite(qty) || !Number.isFinite(avg) ||
          !Number.isFinite(price) || qty <= 0 || avg <= 0 || price < 0) {
        out.textContent = "সঠিক Coin, পরিমাণ, গড় ক্রয়মূল্য ও বর্তমান মূল্য লিখুন।";
        return;
      }

      const invested = qty * avg;
      const current = qty * price;
      const pnl = current - invested;
      const pct = (pnl / invested) * 100;

      out.textContent =
        coin + " | বিনিয়োগ: $" + n(invested, 2) +
        " | বর্তমান মূল্য: $" + n(current, 2) +
        " | লাভ/ক্ষতি: $" + n(pnl, 2) +
        " (" + n(pct, 2) + "%)";
      out.className = "adv-detail " + (pnl >= 0 ? "good" : "bad");
    });
  }

  async function load() {
    try {
      const response = await fetch(DATA_URL + "?v=" + Date.now(), {
        cache: "no-store"
      });

      if (!response.ok) throw new Error("HTTP " + response.status);

      const data = await response.json();

      $("advOnchain").innerHTML = "";
      $("advHalving").innerHTML = "";
      $("advOrderbook").innerHTML = "";
      $("advDerivatives").innerHTML = "";

      addOnchain(data);
      addHalving(data);
      addOrderbook(data);
      addDerivatives(data);

      $("advUpdated").textContent =
        "Advanced Data তৈরি: " +
        (data.generated_at || missing) +
        " | Source: " +
        (Array.isArray(data.data_sources)
          ? data.data_sources.join(", ")
          : missing);

    } catch (error) {
      $("advUpdated").textContent =
        "Advanced Data লোড হয়নি: " + error.message;
    }
  }

  setupPortfolio();
  load();
  setInterval(load, 300000);
})();
