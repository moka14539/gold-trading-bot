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

def create_chart(df_1h, upper, lower, sma200_6h):
    file_path = "chart.png"
    ap = [
        mpf.make_addplot(sma200_6h.tail(50), color='orange', width=1.5),
        mpf.make_addplot([upper]*50, color='cyan', linestyle='--', width=0.8),
        mpf.make_addplot([lower]*50, color='cyan', linestyle='--', width=0.8),
    ]
    mpf.plot(df_1h.tail(50), type='candle', style='charles', savefig=file_path, 
             addplot=ap, title="GOLD V5.6 (MAX-SIGNAL)", tight_layout=True)
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
    gold_1h = yf.download("GC=F", interval="60m", period="max", auto_adjust=True)
    if gold_1h.empty: return

    # 2. 指標算出（6hトレンド用）
    gold_6h = gold_1h['Close'].resample('6h').last()
    sma200_6h_series = gold_6h.rolling(window=200).mean()
    sma50_6h_series = gold_6h.rolling(window=50).mean()
    
    now_p = gold_1h['Close'].iloc[-1].item()
    prev_p = gold_1h['Close'].iloc[-2].item()
    current_sma200_6h = sma200_6h_series.iloc[-1].item()
    current_sma50_6h = sma50_6h_series.iloc[-1].item()
    
    # 動的ATRフィルター
    atr = (gold_1h['High'] - gold_1h['Low']).rolling(14).mean().iloc[-1].item()
    atr_mean = (gold_1h['High'] - gold_1h['Low']).rolling(50).mean().iloc[-1].item()
    if atr < atr_mean * 0.8: return 

    # 6hトレンド同期フィルター
    if now_p > current_sma200_6h and current_sma50_6h > current_sma200_6h:
        trend = "STRONG_UP"
    elif now_p < current_sma200_6h and current_sma50_6h < current_sma200_6h:
        trend = "STRONG_DOWN"
    else:
        return 

    # 1Hタイミング用
    ma20_1h = gold_1h['Close'].rolling(window=20).mean().iloc[-1].item()
    std_1h = gold_1h['Close'].rolling(window=20).std().iloc[-1].item()
    upper, lower = ma20_1h + (std_1h * 2), ma20_1h - (std_1h * 2)
    rsi_1h = calculate_rsi(gold_1h['Close']).iloc[-1].item()

    # 3. 判定ロジック（④最強シグナル統合版）
    score = 0
    msgs = []

    if trend == "STRONG_UP":
        # 基本トレンド加算
        score += 3; msgs.append("🔥 【6hトレンド】上昇波に乗っています。")
        
        # 最強シグナル判定（反発＋勢い一致）
        if prev_p < lower and now_p > lower and rsi_1h > 55:
            score += 6; msgs.append("💎 【最強シグナル】押し目からの強い反発を確認。")
        # 通常の反発
        elif prev_p < lower and now_p > lower:
            score += 4; msgs.append("🎯 【押し目反発】安値圏からの復帰を確認。")
    
    elif trend == "STRONG_DOWN":
        score -= 3; msgs.append("⚡ 【6hトレンド】下落波に乗っています。")
        
        if prev_p > upper and now_p < upper and rsi_1h < 45:
            score -= 6; msgs.append("💎 【最強シグナル】戻りからの強い急落を確認。")
        elif prev_p > upper and now_p < upper:
            score -= 4; msgs.append("🎯 【戻り反落】高値圏からの反転を確認。")

    # トレンド逆行禁止
    if (trend == "STRONG_UP" and score < 0) or (trend == "STRONG_DOWN" and score > 0):
        return

    # 4. 通知
    total_score = abs(score)
    if total_score >= 4:
        direction = "🚀 LONG (BUY)" if score > 0 else "📉 SHORT (SELL)"
        # スコア7以上（最強シグナル等）なら爆益モード発動
        tp_mult = 4.5 if total_score >= 7 else 3.0
        sl = now_p - (atr * 2.0) if score > 0 else now_p + (atr * 2.0)
        tp = now_p + (atr * tp_mult) if score > 0 else now_p - (atr * tp_mult)

        try:
            sma200_6h_for_chart = sma200_6h_series.reindex(gold_1h.index, method='ffill')
            url = upload_to_imgbb(create_chart(gold_1h, upper, lower, sma200_6h_for_chart))
        except: url = None

        title = "👑 【最強・鉄の掟】" if total_score >= 9 else ("🔥 【厳選・V5.6】" if total_score >= 7 else "⚡ 【注目・V5.6】")
        text = f"{title}\n確信度: {'★' * (total_score // 2)} ({total_score})\n\n"
        text += "\n".join([f"{m}" for m in msgs])
        text += f"\n\n📍 価格: ${now_p:.2f}\n🛡️ 損切: ${sl:.2f}\n🎯 利確: ${tp:.2f}\n\n"
        text += f"📈 モード: {'💎爆益狙い' if tp_mult > 3 else '⚖️堅実トレード'}\n⏱ ボラ活性度: { (atr/atr_mean)*100:.1f}%"
        
        send_line_with_chart(text, url)

if __name__ == "__main__":
    main()
