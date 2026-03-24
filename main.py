import yfinance as yf
import pandas as pd
import mplfinance as mpf
import requests
import json
import os

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
    mpf.plot(df_1h.tail(50), type='candle', style='charles', savefig=file_path, 
             addplot=[mpf.make_addplot(sma200.tail(50), color='orange')], tight_layout=True)
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
    gold_1h = yf.download("GC=F", interval="60m", period="10d", auto_adjust=True)
    gold_d = yf.download("GC=F", period="2y", auto_adjust=True)
    if gold_1h.empty: return

    # 2. 指標計算
    now_p = gold_1h['Close'].iloc[-1].item()
    prev_p = gold_1h['Close'].iloc[-2].item()
    sma200_d = gold_d['Close'].rolling(window=200).mean().iloc[-1].item()
    sma50_d = gold_d['Close'].rolling(window=50).mean().iloc[-1].item()
    atr = (gold_1h['High'] - gold_1h['Low']).rolling(14).mean().iloc[-1].item()

    # --- ③ ATRフィルター ---
    if atr < 5: return 

    # --- ① トレンド同期フィルター（神フィルター） ---
    if now_p > sma200_d and sma50_d > sma200_d:
        trend = "STRONG_UP"
    elif now_p < sma200_d and sma50_d < sma200_d:
        trend = "STRONG_DOWN"
    else:
        return # 迷いがある相場は完全スルー

    # 1H指標
    ma20_1h = gold_1h['Close'].rolling(window=20).mean()
    std_1h = gold_1h['Close'].rolling(window=20).std()
    upper, lower = (ma20_1h + (std_1h * 2)).iloc[-1].item(), (ma20_1h - (std_1h * 2)).iloc[-1].item()
    rsi_1h = calculate_rsi(gold_1h['Close']).iloc[-1].item()

    # 3. 判定ロジック
    score = 0
    msgs = []

    # --- ② 押し目・戻り売り継続判定 ---
    if trend == "STRONG_UP":
        if now_p > ma20_1h.iloc[-1] and rsi_1h > 50:
            score += 3; msgs.append("📈強い上昇・押し目買い継続")
        if prev_p < lower and now_p > lower: # BB反発
            score += 4; msgs.append("🎯BB下限からの反発確定")
    
    elif trend == "STRONG_DOWN":
        if now_p < ma20_1h.iloc[-1] and rsi_1h < 50:
            score -= 3; msgs.append("📉強い下降・戻り売り継続")
        if prev_p > upper and now_p < upper: # BB反発
            score -= 4; msgs.append("🎯BB上限からの反落確定")

    # --- ④ トレンド逆行禁止フィルター ---
    if (trend == "STRONG_UP" and score < 0) or (trend == "STRONG_DOWN" and score > 0):
        return

    # 4. 通知判定
    total_score = abs(score)
    if total_score >= 4: # 厳選しつつチャンスも拾う
        direction = "BUY" if score > 0 else "SELL"
        
        # --- ③ 利確倍率の可変設定 ---
        tp_mult = 4.5 if total_score >= 7 else 3.0
        sl = now_p - (atr * 2.0) if direction == "BUY" else now_p + (atr * 2.0)
        tp = now_p + (atr * tp_mult) if direction == "BUY" else now_p - (atr * tp_mult)

        try:
            url = upload_to_imgbb(create_chart(gold_1h, upper, lower))
        except: url = None

        text = f"🏆 【3,000万・鉄の掟 V5.0】\n判定:{direction} / スコア:{total_score}\n\n" + "\n".join([f"・{m}" for m in msgs])
        text += f"\n\n価格: ${now_p:.2f}\n損切: ${sl:.2f}\n利確: ${tp:.2f}\n狙い: {'爆益モード' if tp_mult > 3 else '堅実モード'}"
        
        send_line_with_chart(text, url)

if __name__ == "__main__":
    main()
