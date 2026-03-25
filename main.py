import yfinance as yf
import pandas as pd
import mplfinance as mpf
import requests
import json
import os
import base64

# --- 設定（GitHub Secrets） ---
ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')
IMGBB_API_KEY = os.getenv('IMGBB_API_KEY')

def send_line_with_chart(text, image_url=None):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    messages = [{"type": "text", "text": text}]
    if image_url:
        messages.append({
            "type": "image", 
            "originalContentUrl": image_url, 
            "previewImageUrl": image_url
        })
    data = {"to": USER_ID, "messages": messages}
    requests.post(url, headers=headers, data=json.dumps(data))

def create_chart(df_1h, upper, lower, sma200_6h):
    file_path = "chart.png"
    # 型とインデックスを再確定
    df_1h.index = pd.to_datetime(df_1h.index)
    ap = [
        mpf.make_addplot(sma200_6h.tail(50), color='orange', width=1.5),
        mpf.make_addplot([upper]*50, color='cyan', linestyle='--', width=0.8),
        mpf.make_addplot([lower]*50, color='cyan', linestyle='--', width=0.8),
    ]
    mpf.plot(df_1h.tail(50), type='candle', style='charles', savefig=file_path, 
             addplot=ap, title="GOLD V5.7 (Tactical)", tight_layout=True)
    return file_path

def upload_to_imgbb(file_path):
    with open(file_path, "rb") as f:
        img_base64 = base64.b64encode(f.read())
        res = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_API_KEY, "image": img_base64}
        )
    return res.json()['data']['url']

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    return 100 - (100 / (1 + gain/loss))

def main():
    # 1. データ取得
    raw_df = yf.download("GC=F", interval="60m", period="max", auto_adjust=True)
    if raw_df.empty: return

    # --- 強力な型対策（テスト成功ロジックを移植） ---
    if isinstance(raw_df.columns, pd.MultiIndex):
        raw_df.columns = raw_df.columns.get_level_values(0)
    gold_1h = raw_df[['Open', 'High', 'Low', 'Close']].copy()
    gold_1h = gold_1h.astype(float).dropna()
    gold_1h.index = pd.to_datetime(gold_1h.index)

    # 2. 指標算出
    gold_6h = gold_1h['Close'].resample('6h').last()
    sma200_6h_series = gold_6h.rolling(window=200).mean()
    sma50_6h_series = gold_6h.rolling(window=50).mean()
    
    now_p = gold_1h['Close'].iloc[-1]
    prev_p = gold_1h['Close'].iloc[-2]
    current_sma200_6h = sma200_6h_series.iloc[-1]
    current_sma50_6h = sma50_6h_series.iloc[-1]
    
    # ① トレンド強度算出
    trend_strength = abs(current_sma50_6h - current_sma200_6h) / current_sma200_6h
    
    # ② ローソク足の実体判定用
    body_size = abs(gold_1h['Close'].iloc[-1] - gold_1h['Open'].iloc[-1])
    range_size = gold_1h['High'].iloc[-1] - gold_1h['Low'].iloc[-1]
    
    # 動性ATRフィルター
    atr = (gold_1h['High'] - gold_1h['Low']).rolling(14).mean().iloc[-1]
    atr_mean = (gold_1h['High'] - gold_1h['Low']).rolling(50).mean().iloc[-1]
    if atr < atr_mean * 0.8: return 

    # タイミング用
    ma20_1h = gold_1h['Close'].rolling(window=20).mean().iloc[-1]
    std_1h = gold_1h['Close'].rolling(window=20).std().iloc[-1]
    upper, lower = ma20_1h + (std_1h * 2), ma20_1h - (std_1h * 2)
    rsi_1h = calculate_rsi(gold_1h['Close']).iloc[-1]

    # 3. 判定ロジック
    score = 0
    msgs = []

    if now_p > current_sma200_6h and current_sma50_6h > current_sma200_6h:
        trend = "UP"
        score += 3 if trend_strength > 0.002 else 1
        msgs.append("🔥 【強トレンド】発生中" if trend_strength > 0.002 else "⚠️ 【弱トレンド】継続中")
        
        # ② 実体判定込みの最強シグナル
        if prev_p < lower and now_p > lower and rsi_1h > 55 and (body_size > range_size * 0.6):
            score += 6; msgs.append("💎 【最強シグナル】強い実体で反発確定")
        elif prev_p < lower and now_p > lower:
            score += 4; msgs.append("🎯 【押し目反発】反転を確認")
    elif now_p < current_sma200_6h and current_sma50_6h < current_sma200_6h:
        trend = "DOWN"
        score -= 3 if trend_strength > 0.002 else -1
        msgs.append("⚡ 【強トレンド】発生中" if trend_strength > 0.002 else "⚠️ 【弱トレンド】継続中")

        if prev_p > upper and now_p < upper and rsi_1h < 45 and (body_size > range_size * 0.6):
            score -= 6; msgs.append("💎 【最強シグナル】強い実体で急落確定")
        elif prev_p > upper and now_p < upper:
            score -= 4; msgs.append("🎯 【戻り反落】反転を確認")
    else:
        return

    # 4. 通知
    total_score = abs(score)
    if total_score >= 4:
        direction = "🚀 LONG (BUY)" if score > 0 else "📉 SHORT (SELL)"
        
        # ④ 動的ロット・利確調整
        if total_score >= 9:
            lot_mode = "🔥 攻め (1.5倍)"; tp_mult = 4.5
        elif total_score >= 7:
            lot_mode = "⚖️ 通常 (1.0倍)"; tp_mult = 3.5
        else:
            lot_mode = "🍃 軽め (0.5倍)"; tp_mult = 3.0

        sl = now_p - (atr * 2.0) if score > 0 else now_p + (atr * 2.0)
        tp = now_p + (atr * tp_mult) if score > 0 else now_p - (atr * tp_mult)

        try:
            sma200_6h_for_chart = sma200_6h_series.reindex(gold_1h.index, method='ffill')
            img_url = upload_to_imgbb(create_chart(gold_1h, upper, lower, sma200_6h_for_chart))
        except: img_url = None

        title = "👑 【最強・タクティカル】" if total_score >= 9 else "🔥 【厳選・V5.7】"
        text = f"{title}\n確信度: {'★' * (total_score // 2)} ({total_score})\n\n"
        text += "\n".join([f"{m}" for m in msgs])
        text += f"\n\n📍 価格: ${now_p:.2f}\n🛡️ 損切: ${sl:.2f}\n🎯 利確: ${tp:.2f}\n\n"
        text += f"💰 ロット: {lot_mode}\n⏱ ボラ活性: {(atr/atr_mean)*100:.1f}%"
        
        send_line_with_chart(text, img_url)

if __name__ == "__main__":
    main()
