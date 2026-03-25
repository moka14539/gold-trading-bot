import yfinance as yf
import pandas as pd
import mplfinance as mpf
import requests
import json
import os
from datetime import datetime

# --- 設定（GitHub Secrets） ---
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

def create_chart(df_1h, upper, lower):
    file_path = "chart.png"
    sma200 = df_1h['Close'].rolling(window=200).mean()
    ap = [
        mpf.make_addplot(sma200.tail(50), color='orange', width=1.5),
        mpf.make_addplot([upper]*50, color='cyan', linestyle='--', width=0.8),
        mpf.make_addplot([lower]*50, color='cyan', linestyle='--', width=0.8),
    ]
    mpf.plot(df_1h.tail(50), type='candle', style='charles', savefig=file_path, 
             addplot=ap, title="GOLD V5.3 (ATR 3.5)", tight_layout=True)
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
    gold_1h = yf.download("GC=F", interval="60m", period="15d", auto_adjust=True)
    gold_d = yf.download("GC=F", period="2y", auto_adjust=True)
    if gold_1h.empty or gold_d.empty: return

    # 2. 指標計算
    now_p = gold_1h['Close'].iloc[-1].item()
    prev_p = gold_1h['Close'].iloc[-2].item()
    sma200_d = gold_d['Close'].rolling(window=200).mean().iloc[-1].item()
    sma50_d = gold_d['Close'].rolling(window=50).mean().iloc[-1].item()
    atr = (gold_1h['High'] - gold_1h['Low']).rolling(14).mean().iloc[-1].item()

    # --- ③ ATRフィルター（3.5：絶妙なバランス型） ---
    if atr < 3.5: return 

    # --- ① トレンド同期フィルター ---
    if now_p > sma200_d and sma50_d > sma200_d:
        trend = "STRONG_UP"
    elif now_p < sma200_d and sma50_d < sma200_d:
        trend = "STRONG_DOWN"
    else:
        return 

    # 指標
    ma20_series = gold_1h['Close'].rolling(window=20).mean()
    ma20_1h = ma20_series.iloc[-1].item()
    std_1h = gold_1h['Close'].rolling(window=20).std().iloc[-1].item()
    upper, lower = ma20_1h + (std_1h * 2), ma20_1h - (std_1h * 2)
    rsi_1h = calculate_rsi(gold_1h['Close']).iloc[-1].item()

    # 3. 判定ロジック
    score = 0
    msgs = []

    if trend == "STRONG_UP":
        if now_p > ma20_1h and rsi_1h > 50:
            score += 3
            msgs.append("🔥 【トレンド追随】上昇の勢いが継続中。押し目買いの好機。")
        if prev_p < lower and now_p > lower: 
            score += 4
            msgs.append("🎯 【反発確定】安値圏での反転を確認。期待値上昇。")
    
    elif trend == "STRONG_DOWN":
        if now_p < ma20_1h and rsi_1h < 50:
            score -= 3
            msgs.append("⚡ 【トレンド追随】下落の勢いが継続中。戻り売りの好機。")
        if prev_p > upper and now_p < upper: 
            score -= 4
            msgs.append("🎯 【反落確定】高値圏での反転を確認。期待値上昇。")

    # --- ④ トレンド逆行禁止フィルター ---
    if (trend == "STRONG_UP" and score < 0) or (trend == "STRONG_DOWN" and score > 0):
        return

    # 4. 通知判定
    total_score = abs(score)
    if total_score >= 4:
        direction = "🚀 LONG (BUY)" if score > 0 else "📉 SHORT (SELL)"
        tp_mult = 4.5 if total_score >= 7 else 3.0
        sl = now_p - (atr * 2.0) if score > 0 else now_p + (atr * 2.0)
        tp = now_p + (atr * tp_mult) if score > 0 else now_p - (atr * tp_mult)

        try:
            url = upload_to_imgbb(create_chart(gold_1h, upper, lower))
        except: url = None

        title = "👑 【究極・鉄の掟】" if total_score >= 7 else "🔥 【厳選・鉄の掟】"
        text = f"{title}\n\n方向: {direction}\n確信度: {'★' * total_score} ({total_score})\n\n"
        text += "\n".join([f"{m}" for m in msgs])
        text += f"\n\n📍 エントリー目標: ${now_p:.2f}\n🛡️ 損切ライン: ${sl:.2f}\n🎯 利確ライン: ${tp:.2f}\n\n"
        text += f"📈 モード: {'爆益' if tp_mult > 3 else '堅実'}\n⏱ ATR(ボラ): {atr:.2f}"
        
        send_line_with_chart(text, url)

if __name__ == "__main__":
    main()
