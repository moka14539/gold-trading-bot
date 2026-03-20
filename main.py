import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime
import pytz

ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')

def send_line(text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    data = {"to": USER_ID, "messages": [{"type": "text", "text": text}]}
    requests.post(url, headers=headers, data=json.dumps(data))

def analyze_gold_cfd():
    # 1. データ取得 (CFD取引で指標となる先物とドル円・金利)
    # GC=F はゴールド先物、XAUUSD=X は現物。ここでは取引量の多い先物をメインにします。
    gold = yf.download("GC=F", interval="60m", period="7d")
    gold_d = yf.download("GC=F", period="2y")
    tnx = yf.download("^TNX", interval="60m", period="5d")
    usdjpy = yf.download("JPY=X", interval="60m", period="5d")

    messages = []
    score = 0
    now_g = gold['Close'].iloc[-1].item()
    
    # --- 指標計算 ---
    # 200日線 (長期トレンドの境界線)
    sma200 = gold_d['Close'].rolling(window=200).mean().iloc[-1].item()
    # ボリンジャーバンド
    ma20 = gold['Close'].rolling(window=20).mean()
    std = gold['Close'].rolling(window=20).std()
    upper, lower = ma20 + (std * 2), ma20 - (std * 2)
    # MACD
    exp1 = gold['Close'].ewm(span=12, adjust=False).mean()
    exp2 = gold['Close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    # RSI
    delta = gold['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rsi = (100 - (100 / (1 + gain/loss))).iloc[-1].item()

    # 外部要因（金利・為替）
    t_now, t_prev = tnx['Close'].iloc[-1].item(), tnx['Close'].iloc[-2].item()
    u_now, u_prev = usdjpy['Close'].iloc[-1].item(), usdjpy['Close'].iloc[-2].item()

    # --- 時間帯判定 (CFDが激しく動く欧米時間) ---
    jst = datetime.now(pytz.timezone('Asia/Tokyo'))
    is_active_time = 16 <= jst.hour <= 24 or 0 <= jst.hour <= 4 # NY終盤まで拡大
    time_bonus = 1 if is_active_time else 0

    # --- 🟢 BUY戦略 (OR条件) ---
    if now_g > sma200 and rsi < 40:
        messages.append("🟢【長期押し目】200日線上での反発チャンス。"); score += 2
    if now_g > upper.iloc[-2].item():
        messages.append("📈【加速】ボリバン上限突破。強い買い圧力を検知。"); score += 1
    if macd.iloc[-2].item() <= signal.iloc[-2].item() and macd.iloc[-1].item() > signal.iloc[-1].item():
        messages.append("🔵【転換】MACDゴールデンクロス。"); score += 1
    if t_now < t_prev and u_now < u_prev:
        messages.append("🌍【マクロ環境◎】金利低下＆ドル安。ゴールド上昇の鉄板環境。"); score += 2

    # --- 🔴 SELL戦略 (OR条件) ---
    if now_g < sma200 and rsi > 60:
        messages.append("🔴【長期戻り売り】200日線下での反落ポイント。"); score -= 2
    if now_g < lower.iloc[-2].item():
        messages.append("📉【急落】ボリバン下限を突破。売り加速のサイン。"); score -= 1
    if macd.iloc[-2].item() >= signal.iloc[-2].item() and macd.iloc[-1].item() < signal.iloc[-1].item():
        messages.append("🟠【転換】MACDデッドクロス。"); score -= 1
    if t_now > t_prev and u_now > u_prev:
        messages.append("⛔【マクロ逆風】金利上昇＆ドル高。ショート（売り）推奨環境。"); score -= 2

    # --- 判定と損切り・利確目安 ---
    if messages:
        score += (time_bonus if score > 0 else -time_bonus)
        total_score = abs(score)
        direction = "BUY" if score > 0 else "SELL"
        
        # ボラティリティに基づいた損切り(SL)と利確(TP)の提示
        volatility = std.iloc[-1].item()
        sl_price = now_g - (volatility * 2) if direction == "BUY" else now_g + (volatility * 2)
        tp_price = now_g + (volatility * 3) if direction == "BUY" else now_g - (volatility * 3)

        title = f"🔥【CFD全力{direction}推奨】" if total_score >= 4 else f"📢 CFDゴールド監視報告"
        output = f"{title}\n時別: {'欧米市場(高ボラ) ✅' if is_active_time else 'アジア市場(低ボラ)'}\n\n"
        output += "\n---\n".join(messages)
        output += f"\n\n💰現在価格: ${now_g:.2f}"
        output += f"\n🛡️損切り目安: ${sl_price:.2f}"
        output += f"\n🎯利確目安: ${tp_price:.2f}"
        output += f"\n📊期待度スコア: {total_score}"
        send_line(output)

if __name__ == "__main__":
    analyze_gold_cfd()
