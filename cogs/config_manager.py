import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from typing import List

from .utils import group_autocomplete, location_autocomplete

CONFIG_FILE_NAME = "config.json"
DEFAULT_CONFIG = {
    "advisor_name": "（顧問名未設定）",
    "student_rep_name": "（代表学生名未設定）",
    "template_file_name": "[電子計算機部]R0年xx月_活動計画書・活動報告書・活動延長願（複合書式）.xlsx",
    "editable_groups": ["AI", "CG･DTM", "Web", "Game", "Network", "Procon"],
    "editable_locations": ["旧CAD室", "コンピューター室", "FPラボ", "村上先生教員室前"]
}

def load_config():
    if not os.path.exists(CONFIG_FILE_NAME):
        with open(CONFIG_FILE_NAME, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE_NAME, "r", encoding="utf-8") as f:
            config = json.load(f)
            if "template_file_name" not in config:
                config["template_file_name"] = DEFAULT_CONFIG["template_file_name"]
            return config
    except (json.JSONDecodeError, FileNotFoundError):
        return DEFAULT_CONFIG

def save_config(data):
    with open(CONFIG_FILE_NAME, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

class ConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    config_group = app_commands.Group(name="config", description="Botの各種設定を行います。")
    set_group = app_commands.Group(name="set", parent=config_group, description="設定値を変更します。")
    group_config_group = app_commands.Group(name="group", parent=config_group, description="グループ選択肢の管理")
    location_config_group = app_commands.Group(name="location", parent=config_group, description="場所選択肢の管理")

    @config_group.command(name="show", description="現在の設定値を表示します。")
    async def show_config(self, interaction: discord.Interaction):
        config = load_config()
        embed = discord.Embed(title="現在のBot設定", color=discord.Color.blue())
        embed.add_field(name="顧問名", value=config.get("advisor_name", "未設定"), inline=False)
        embed.add_field(name="代表学生名", value=config.get("student_rep_name", "未設定"), inline=False)
        embed.add_field(name="編集可能なグループ", value="、".join(config.get("editable_groups", [])), inline=False)
        embed.add_field(name="編集可能な場所", value="、".join(config.get("editable_locations", [])), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @set_group.command(name="advisor", description="顧問名を設定します。")
    async def set_advisor(self, interaction: discord.Interaction, name: str):
        config = load_config(); config["advisor_name"] = name; save_config(config)
        await interaction.response.send_message(f"✅ 顧問名を「{name}」に設定しました。", ephemeral=True)

    @set_group.command(name="student_rep", description="代表学生名を設定します。")
    async def set_student_rep(self, interaction: discord.Interaction, name: str):
        config = load_config(); config["student_rep_name"] = name; save_config(config)
        await interaction.response.send_message(f"✅ 代表学生名を「{name}」に設定しました。", ephemeral=True)

    @group_config_group.command(name="add", description="グループの選択肢を追加します。")
    async def add_group(self, interaction: discord.Interaction, name: str):
        config = load_config()
        if name in config.get("editable_groups", []) or name in ["全体", "その他"]:
            await interaction.response.send_message(f"エラー: グループ「{name}」は既に存在します。", ephemeral=True)
            return
        config.setdefault("editable_groups", []).append(name)
        save_config(config)
        await interaction.response.send_message(f"✅ グループ「{name}」を追加しました。\n**【重要】Botを再起動すると、コマンドの選択肢に反映されます。**", ephemeral=True)

    @group_config_group.command(name="remove", description="グループの選択肢を削除します。")
    @app_commands.autocomplete(name=group_autocomplete)
    async def remove_group(self, interaction: discord.Interaction, name: str):
        config = load_config()
        if name not in config.get("editable_groups", []):
            await interaction.response.send_message(f"エラー: グループ「{name}」は編集可能なリストに存在しません。", ephemeral=True)
            return
        config["editable_groups"].remove(name)
        save_config(config)
        await interaction.response.send_message(f"✅ グループ「{name}」を削除しました。\n**【重要】Botを再起動すると、コマンドの選択肢に反映されます。**", ephemeral=True)

    @location_config_group.command(name="add", description="場所の選択肢を追加します。")
    async def add_location(self, interaction: discord.Interaction, name: str):
        config = load_config()
        if name in config.get("editable_locations", []) or name == "その他":
            await interaction.response.send_message(f"エラー: 場所「{name}」は既に存在します。", ephemeral=True)
            return
        config.setdefault("editable_locations", []).append(name)
        save_config(config)
        await interaction.response.send_message(f"✅ 場所「{name}」を追加しました。\n**【重要】Botを再起動すると、コマンドの選択肢に反映されます。**", ephemeral=True)

    @location_config_group.command(name="remove", description="場所の選択肢を削除します。")
    @app_commands.autocomplete(name=location_autocomplete)
    async def remove_location(self, interaction: discord.Interaction, name: str):
        config = load_config()
        if name not in config.get("editable_locations", []):
            await interaction.response.send_message(f"エラー: 場所「{name}」は編集可能なリストに存在しません。", ephemeral=True)
            return
        config["editable_locations"].remove(name)
        save_config(config)
        await interaction.response.send_message(f"✅ 場所「{name}」を削除しました。\n**【重要】Botを再起動すると、コマンドの選択肢に反映されます。**", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ConfigCog(bot))
