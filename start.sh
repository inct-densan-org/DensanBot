#!/bin/bash
echo "Botを起動します..."
echo "このターミナルを閉じるとBotが終了します。"

while true
do
    # main.pyを実行します。もしvenvなどの仮想環境を使っている場合は、
    # ここの "python" の部分を適切な実行パスに書き換えてください。
    # 例: .venv/bin/python main.py
#    python main.py
    uv run main.py

    echo "Botが終了しました。5秒後に自動で再起動します..."
    sleep 5
done
