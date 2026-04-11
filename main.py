import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime
import pytz

# 環境変数（設定済みを想定）
ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')

def send_line(text):
    if not text: return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    data = {"to": USER_ID, "messages": [{"type": "text", "text": text}]}
    try:
        res = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
        res.raise_for_status()
    except Exception as e:
        print(f"LINE送信エラー: {e}")

def is_market_safe():
    jst = datetime.now(pytz.timezone('Asia/Tokyo'))
    if jst.weekday() >= 5: return False, "土日休止"
    if jst.weekday() == 0 and 6 <= jst.hour < 9: return False, "月曜早朝リスク"
    if 6 <= jst.hour <= 7:
        if jst.hour == 6 or (jst.hour == 7 and jst.minute < 30): return False, "早朝メンテ"
    return True, "取引可能"

def analyze_and_send():
    is_safe, reason = is_market_safe()
    if not is_safe: return

    # --- 1. データ取得 ---
    gold_1h = yf.download("GC=F", interval="60m", period="7d", progress=False)
    gold_15m = yf.download("GC=F", interval="15m", period="5d", progress=False)
    gold_d = yf.download("GC=F", period="2y", progress=False)
    tnx = yf.download("^TNX", interval="60m", period="5d", progress=False)
    dxy = yf.download("DX-Y.NYB", interval="60m", period="5d", progress=False)

    if gold_1h.empty or gold_15m.empty or dxy.empty: return

    # 各種スコア・メッセージ初期化
    trend_score = 0
    macro_score = 0
    logic_score = 0
    messages = []
    
    now_p = float(gold_15m['Close'].iloc[-1].item())
    jst_now = datetime.now(pytz.timezone('Asia/Tokyo'))
    h = jst_now.hour

    # --- 2. 指標計算 ---
    # ATR (1h)
    high_low = gold_1h['High'] - gold_1h['Low']
    high_close = (gold_1h['High'] - gold_1h['Close'].shift()).abs()
    low_close = (gold_1h['Low'] - gold_1h['Close'].shift()).abs()
    atr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean().iloc[-1].item()

    # ADX (15m)
    plus_dm = (gold_15m['High'].diff()).where(lambda x: (x > 0) & (x > (gold_15m['Low'].diff() * -1)), 0)
    minus_dm = (gold_15m['Low'].diff() * -1).where(lambda x: (x > 0) & (x > gold_15m['High'].diff()), 0)
    tr = pd.concat([(gold_15m['High'] - gold_15m['Low']), 
                   (gold_15m['High'] - gold_15m['Close'].shift()).abs(), 
                   (gold_15m['Low'] - gold_15m['Close'].shift()).abs()], axis=1).max(axis=1)
    atr_adx = tr.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr_adx)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr_adx)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    adx_series = dx.rolling(14).mean()
    adx_now = adx_series.iloc[-1].item()

    # RSI (15m)
    delta_15 = gold_15m['Close'].diff()
    gain = (delta_15.where(delta_15 > 0, 0)).rolling(window=14).mean()
    loss = (-delta_15.where(delta_15 < 0, 0)).rolling(window=14).mean()
    rsi_15 = (100 - (100 / (1 + (gain / loss.replace(0, 0.00001))))).iloc[-1].item()

    # --- 3. ロジック判定 ---
    # A. トレンド (SMA200)
    sma200 = gold_d['Close'].rolling(window=200).mean().iloc[-1].item()
    if now_p > sma200:
        trend_score += 2
        messages.append("🟢長期上昇トレンド")
    else:
        trend_score -= 2
        messages.append("🔴長期下落トレンド")

    # B. マクロ (金利・ドル)
    t_diff = tnx['Close'].iloc[-1].item() - tnx['Close'].iloc[-2].item()
    dxy_diff = dxy['Close'].iloc[-1].item() - dxy['Close'].iloc[-2].item()
    if t_diff < 0 and dxy_diff < 0:
        macro_score += 2
        messages.append("🌍マクロ追い風")
    elif t_diff > 0 and dxy_diff > 0:
        macro_score -= 2
        messages.append("⛔マクロ逆風")

    # C. ADXトレンド強度
    if adx_now > 25:
        if plus_di.iloc[-1] > minus_di.iloc[-1]:
            logic_score += 1
            messages.append(f"🔥上昇勢いあり(ADX:{adx_now:.1f})")
        else:
            logic_score -= 1
            messages.append(f"🧊下落勢いあり(ADX:{adx_now:.1f})")

    # D. 当日VWAP
    today_data = gold_15m[gold_15m.index.date == gold_15m.index[-1].date()].copy()
    today_data = today_data[today_data['Volume'] > 0]
    if not today_data.empty:
        vwap_now = (today_data['Close'] * today_data['Volume']).sum() / today_data['Volume'].sum()
        if now_p < vwap_now * 0.998: logic_score += 1 # 割安
        elif now_p > vwap_now * 1.002: logic_score -= 1 # 割高

    # E. フェイク抜け・上ヒゲ
    ph = gold_15m['High'].rolling(20).max().iloc[-2]
    pl = gold_15m['Low'].rolling(20).min().iloc[-2]
    last_bar = gold_15m.iloc[-1]
    body = abs(last_bar['Close'] - last_bar['Open'])
    wick_up = last_bar['High'] - max(last_bar['Open'], last_bar['Close'])

    if last_bar['High'] > ph and (last_bar['High'] - ph) < atr * 0.5:
        logic_score -= 1
        if wick_up > body * 1.5:
            logic_score -= 1
            messages.append("⚠️フェイク上抜け(上ヒゲ)")
    if last_bar['Low'] < pl and (pl - last_bar['Low']) < atr * 0.5:
        logic_score += 1
        messages.append("⚠️フェイク下抜け")

    # F. 時間帯加重
    time_score = 1 if 16 <= h <= 23 else (-1 if 0 <= h <= 8 else 0)

    # --- 4. 総合判定 ---
    total_score = trend_score + macro_score + logic_score + time_score
    abs_score = abs(total_score)

    # デバッグログ
    print(f"[{jst_now}] Total:{total_score} (Trend:{trend_score} Macro:{macro_score} Logic:{logic_score} Time:{time_score})")

    if abs_score >= 3:
        direction = "BUY" if total_score > 0 else "SELL"
        sl_mult = 3.5 if rsi_15 < 30 or rsi_15 > 70 else 2.5
        sl = now_p - (atr * sl_mult) if direction == "BUY" else now_p + (atr * sl_mult)
        tp = now_p + (atr * 4.0) if direction == "BUY" else now_p - (atr * 4.0)
        
        status = "👑【極・推奨】" if abs_score >= 6 else "📢【チャンス】"
        output_text = f"{status} {direction}\nスコア:{abs_score}\n\n"
        output_text += "\n".join([f"・{m}" for m in messages])
        output_text += f"\n\n💰価格: ${now_p:.2f}\n🛡️SL: ${sl:.2f} | 🎯TP: ${tp:.2f}"
        output_text += f"\n\n⏱️RSI: {rsi_15:.1f} | ADX: {adx_now:.1f}"
        
        send_line(output_text)

if __name__ == "__main__":
    analyze_and_send()
