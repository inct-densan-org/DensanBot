import discord
from discord import app_commands
from discord.ext import commands
import os
import sys
import subprocess

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    admin_group = app_commands.Group(name="admin", description="Botの管理者用コマンドです。")

    @admin_group.command(name="reload", description="全機能とコマンドを再読み込みし、Discordに即時反映させます。")
    @app_commands.default_permissions(administrator=True)
    async def reload_cogs(self, interaction: discord.Interaction):
        """すべてのCogをリロードし、コマンドツリーを同期する"""
        await interaction.response.defer(ephemeral=True, thinking=True)

        reloaded_cogs = []
        failed_cogs = []

        # main.pyで定義されている除外リストを再現
        exclude_files = ["ui_components.py", "utils.py"]
        
        # cogsディレクトリ内のすべての拡張機能を取得
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and filename not in exclude_files and not filename.startswith("_"):
                extension_name = f"cogs.{filename[:-3]}"
                try:
                    await self.bot.reload_extension(extension_name)
                    reloaded_cogs.append(extension_name)
                except Exception as e:
                    print(f"拡張機能のリロードに失敗: {extension_name}\n{e}")
                    failed_cogs.append(f"{extension_name}: {e}")

        # コマンドツリーを同期
        sync_status = "✅ コマンドの同期に成功しました。"
        try:
            await self.bot.tree.sync()
        except Exception as e:
            sync_status = f"❌ コマンドの同期に失敗しました: {e}"

        # 結果を報告
        embed = discord.Embed(title="リロード完了", color=discord.Color.green())
        if reloaded_cogs:
            embed.add_field(name="再読み込み成功", value="```\n" + "\n".join(reloaded_cogs) + "\n```", inline=False)
        if failed_cogs:
            embed.color = discord.Color.red()
            embed.add_field(name="再読み込み失敗", value="```\n" + "\n".join(failed_cogs) + "\n```", inline=False)
        
        embed.add_field(name="コマンド同期", value=sync_status, inline=False)
        embed.set_footer(text="失敗した拡張機能がある場合、コンソールで詳細なエラーを確認してください。")
        
        await interaction.followup.send(embed=embed, ephemeral=True)


    @admin_group.command(name="restart", description="Botを安全に再起動します。")
    @app_commands.default_permissions(administrator=True)
    async def restart_bot(self, interaction: discord.Interaction):
        """Botを再起動する"""
        await interaction.response.send_message("✅ Botを再起動します...", ephemeral=True)
        
        script = 'start.bat' if os.name == 'nt' else './start.sh'
        try:
            subprocess.Popen([script], shell=True)
            await self.bot.close()
        except Exception as e:
            print(f"再起動に失敗しました: {e}")
            await interaction.followup.send(f"エラー: 再起動に失敗しました。\n`{e}`", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
