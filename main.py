import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

# .envファイルから環境変数を読み込む
load_dotenv()
TOKEN = os.getenv("TOKEN")

# Botのインスタンスを作成
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            # Privileged Intentsを有効にする
            intents=discord.Intents.all(),
        )

    async def setup_hook(self):
        # 除外するユーティリティファイルのリスト
        exclude_files = ["ui_components.py", "utils.py", "schedule.py"]

        # cogsフォルダ内のPythonファイルを読み込む
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and not filename.startswith("_") and filename not in exclude_files:
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    print(f"Loaded extension: {filename}")
                except Exception as e:
                    print(f"Failed to load extension {filename}: {e}")
        
        # スラッシュコマンドを同期する
        await self.tree.sync()

    async def on_ready(self):
        print(f"{self.user}としてログインしました")

# Botを起動
if __name__ == "__main__":
    bot = MyBot()
    bot.run(TOKEN)
