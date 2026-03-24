import yfinance as yf
import pandas as pd
import mplfinance as mpf
import requests
import json
import os
from datetime import datetime
import pytz

# --- 設定（GitHub Secretsに以下を登録してください） ---
ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')
IMGBB_API_KEY = os.getenv('IMGBB_API_KEY')

def send_line_with_chart(text, image_url=None):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    messages = [{"type": "text", "text": text}]
    if image_url:
        messages.append({"type": "image", "originalContentUrl": image_url, "previewImageUrl": image_url})
    data = {"to": USER_ID, "messages": messages}
    requests.post(url, headers=headers, data=json.dumps(data))

def create_chart(df_1h, last_upper, last_lower):
    file_path = "chart.png"
    sma200 = df_1h['Close'].rolling(window=200).mean()
    ap = [
        mpf.make_addplot(sma200, color='orange', width=1.5),
        mpf.make_addplot([last_upper]*len(df_1h.tail(50)), color='cyan', linestyle='--', width=0.8),
        mpf.make_addplot([last_lower]*len(df_1h.tail(50)), color='cyan', linestyle='--', width=0.8),
    ]
    mpf.plot(df_1h.tail(50), type='candle', style='charles', savefig=file_path, addplot=ap, volume=False, title="GOLD 1H Strategy-V3", tight_layout=True)
    return file_path

def upload_to_imgbb(file_path):
    url = "https://api.imgbb.com/1/upload"
    with open(file_path, "rb") as f:
        payload = {"key": IMGBB_API_KEY, "image": f.read()}
        res = requests.post(url, data=payload)
    return res.json()['data']['url']

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    return 100 - (100 / (1 + gain/loss))

def main():
    # 1. データ取得
    gold_1h = yf.download("GC=F", interval="60m", period="10d")
    gold_15m = yf.download("GC=F", interval="15m", period="3d")
    gold_d = yf.download("GC=F", period="2y")
    tnx = yf.download("^TNX", interval="60m", period="5d")
    dxy = yf.download("DX-Y.NYB", interval="60m", period="5d")

    if gold_1h.empty or gold_15m.empty or dxy.empty: return

    # 2. テクニカル指標計算
    now_p = gold_1h['Close'].iloc[-1].item()
    prev_p = gold_1h['Close'].iloc[-2].item()
    sma200 = gold_d['Close'].rolling(window=200).mean().iloc[-1].item()
    
    ma20_1h = gold_1h['Close'].rolling(window=20).mean()
    std_1h = gold_1h['Close'].rolling(window=20).std()
    last_upper = (ma20_1h + (std_1h * 2)).iloc[-1].item()
    last_lower = (ma20_1h - (std_1h * 2)).iloc[-1].item()

    rsi_1h = calculate_rsi(gold_1h['Close']).iloc[-1].item()
    rsi_15m = calculate_rsi(gold_15m['Close']).iloc[-1].item()

    # マクロ要因：3時間平均でのトレンド判定
    t_short = tnx['Close'].iloc[-3:].mean().item()
    t_long = tnx['Close'].iloc[-6:-3].mean().item()
    d_short = dxy['Close'].iloc[-3:].mean().item()
    d_long = dxy['Close'].iloc[-6:-3].mean().item()

    # 3. 判定ロジック
    messages = []
    score = 0

    # A. トレンド & マクロ確定トレンド
    if now_p > sma200: 
        score += 1
        if t_short < t_long and d_short < d_long: 
            messages.append("🌍マクロ確定追い風（3H平均低下中）"); score += 2
    elif now_p < sma200:
        score -= 1
        if t_short > t_long and d_short > d_long: 
            messages.append("⛔マクロ確定逆風（3H平均上昇中）"); score -= 2

    # B. 1H RSI 大波の環境認識
    if rsi_1h < 35: messages.append("💎1H RSI 大底圏"); score += 2
    elif rsi_1h > 65: messages.append("💎1H RSI 天井圏"); score -= 2

    # C. BB戻り確認 & 15M RSI
    # BUY側
    if now_p <= last_lower and rsi_15m < 30:
        messages.append("📉 BB下限到達（反発準備）"); score += 2
    if prev_p < last_lower and now_p > last_lower:
        messages.append("🎯 BB復帰（反発確定）"); score += 4

    # SELL側
    if now_p >= last_upper and rsi_15m > 70:
        messages.append("📈 BB上限到達（反落準備）"); score -= 2
    if prev_p > last_upper and now_p < last_upper:
        messages.append("🎯 BB復帰（反落確定）"); score -= 4

    # 4. 通知判定
    total_score = abs(score)
    if total_score >= 5:
        try:
            img_path = create_chart(gold_1h, last_upper, last_lower)
            img_url = upload_to_imgbb(img_path)
        except: img_url = None

        direction = "BUY" if score > 0 else "SELL"
        atr = (gold_1h['High'] - gold_1h['Low']).rolling(14).mean().iloc[-1].item()
        sl = now_p - (atr * 2.5) if direction == "BUY" else now_p + (atr * 2.5)
        tp = now_p + (atr * 4.0) if direction == "BUY" else now_p - (atr * 4.0)

        title = "👑 【超・確定推奨】" if total_score >= 7 else "🔥 【反発確定推奨】"
        text = f"{title}\nスコア:{total_score}\n\n" + "\n".join([f"・{m}" for m in messages])
        text += f"\n\n💰価格: ${now_p:.2f}\n🛡️損切: ${sl:.2f}\n🎯利確: ${tp:.2f}\n⏱️1H:{rsi_1h:.1f} / 15M:{rsi_15m:.1f}"
        
        send_line_with_chart(text, img_url)

if __name__ == "__main__":
    main()
