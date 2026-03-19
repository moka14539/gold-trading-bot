import yfinance as yf
import pandas as pd
import requests
import json
import os

# --- 【修正ポイント】GitHubのSecretsから安全に読み込む設定 ---
ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')

def send_line(text):
    # Secretsが正しく設定されていない場合のチェック
    if not ACCESS_TOKEN or not USER_ID:
        print("エラー: LINEのトークンまたはユーザーIDが設定されていません。")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }
    data = {
        "to": USER_ID, # ここがエラーの場所でした。変数をそのまま使えばOK！
        "messages": [{"type": "text", "text": text}]
    }
    res = requests.post(url, headers=headers, data=json.dumps(data))
    print(f"送信ステータス: {res.status_code}")

def analyze_gold():
    # データの取得
    df = yf.download("GLD", period="1y")
    
    # 簡単な判定ロジック（テスト用）
    latest_close = df['Close'].iloc[-1]
    
    # テストとして、実行されたら必ずLINEを送る設定にします
    send_line(f"🔔ゴールド監視システム稼働中\n現在の価格: ${latest_close:.2f}\nシステムは正常にリンクされました！")

if __name__ == "__main__":
    analyze_gold()
