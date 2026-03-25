import yfinance as yf
import mplfinance as mpf
import requests
import json
import os
import pandas as pd
import base64

# --- 設定 ---
ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')
IMGBB_API_KEY = os.getenv('IMGBB_API_KEY')

def main():
    # 1. データを取得
    df = yf.download("GC=F", interval="60m", period="5d", auto_adjust=True)
    
    # --- 型対策 ---
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[['Open', 'High', 'Low', 'Close']].copy()
    df = df.astype(float).dropna()
    
    if df.empty: return

    # 2. チャート画像を作成
    file_path = "test_chart.png"
    df.index = pd.to_datetime(df.index)
    mpf.plot(df.tail(50), type='candle', style='charles', savefig=file_path)
    
    # 3. ImgBBにアップロード（Base64エンコード方式に変更）
    with open(file_path, "rb") as f:
        # 画像をBase64文字列に変換して送るのが最も確実です
        img_base64 = base64.b64encode(f.read())
        
        res = requests.post(
            "https://api.imgbb.com/1/upload",
            data={
                "key": IMGBB_API_KEY,
                "image": img_base64
            }
        )
    
    # 4. 結果判定
    res_json = res.json()
    if res.status_code == 200:
        image_url = res_json['data']['url']
        msg = "🎯 おめでとうございます！画像開通に成功しました。"
    else:
        image_url = None
        # エラーメッセージを詳細化
        error_msg = res_json.get('error', {}).get('message', 'Unknown Error')
        msg = f"❌ アップロード失敗: {error_msg}"

    # 5. LINEに送信
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }
    
    messages = [{"type": "text", "text": msg}]
    if image_url:
        messages.append({
            "type": "image",
            "originalContentUrl": image_url,
            "previewImageUrl": image_url
        })
    
    requests.post(url, headers=headers, data=json.dumps({"to": USER_ID, "messages": messages}))

if __name__ == "__main__":
    main()
