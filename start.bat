@echo off
echo Botを起動します...
echo このウィンドウを閉じるとBotが終了します。

:loop
rem main.pyを実行します。もしuvやvenvなどの仮想環境を使っている場合は、
rem ここの "python" の部分を適切な実行パスに書き換えてください。
rem 例: .venv\Scripts\python.exe main.py
python main.py

echo Botが終了しました。5秒後に自動で再起動します...
timeout /t 5
goto loop
