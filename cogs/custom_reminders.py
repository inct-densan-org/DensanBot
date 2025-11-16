import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import datetime
import uuid
from dateutil.relativedelta import relativedelta
from typing import List

from .ui_components import PaginationView
from .utils import load_json, save_json, parse_date, REMINDERS_FILE, JST

# --- オートコンプリート用の関数 ---
async def reminder_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    reminders = load_json(REMINDERS_FILE)
    return [
        app_commands.Choice(name=f"{r.get('date')} - {r.get('content', '')[:50]}", value=r.get("id"))
        for r in reminders if current.lower() in r.get('content', '').lower() or current in r.get('date', '')
    ][:25]


class ReminderActionView(PaginationView):
    def __init__(self, embeds: list[discord.Embed], interaction: discord.Interaction, reminders: list[dict]):
        super().__init__(embeds, interaction)
        self.reminders = reminders

    @discord.ui.button(label="編集", style=discord.ButtonStyle.secondary, row=1)
    async def edit_reminder(self, interaction: discord.Interaction, button: discord.ui.Button):
        reminder = self.reminders[self.current_page]
        # /remind edit コマンドをチャット欄に挿入する
        command_str = f"/remind edit id:{reminder['id']} "
        await interaction.response.send_message(
            f"以下のコマンドを編集して実行してください:\n`{command_str}`",
            ephemeral=True
        )

    @discord.ui.button(label="削除", style=discord.ButtonStyle.danger, row=1)
    async def delete_reminder(self, interaction: discord.Interaction, button: discord.ui.Button):
        reminder = self.reminders[self.current_page]
        rem_id = reminder.get("id")
        updated_reminders = [r for r in load_json(REMINDERS_FILE) if r.get("id") != rem_id]
        save_json(REMINDERS_FILE, updated_reminders)
        await interaction.response.send_message(f"リマインダー「{reminder['content'][:20]}...」を削除しました。", ephemeral=True)
        await self.interaction.message.delete()


class CustomRemindersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_reminders.start()

    def cog_unload(self): self.check_reminders.cancel()

    remind_group = app_commands.Group(name="remind", description="カスタムリマインダー機能")

    @remind_group.command(name="add", description="新しいリマインダーを登録します。")
    @app_commands.describe(
        date="日付 (YYYY-MM-DD or YYYYMMDD)",
        target="対象者 (例: 部長, 会計担当)",
        content="内容 (例: ドメイン更新)",
        repeat="繰り返しの設定"
    )
    @app_commands.choices(repeat=[
        app_commands.Choice(name="なし", value="none"),
        app_commands.Choice(name="毎週", value="weekly"),
        app_commands.Choice(name="毎月", value="monthly"),
        app_commands.Choice(name="毎年", value="yearly"),
    ])
    async def add_reminder(self, interaction: discord.Interaction, date: str, target: str, content: str, repeat: app_commands.Choice[str]):
        date_str = parse_date(date)
        if not date_str:
            await interaction.response.send_message("エラー: 日付の形式が正しくありません。", ephemeral=True)
            return
        
        reminders = load_json(REMINDERS_FILE)
        new_reminder = {
            "id": str(uuid.uuid4()), "date": date_str, "target": target, "content": content,
            "repeat": repeat.value, "creator_name": interaction.user.display_name,
            "creator_avatar": str(interaction.user.display_avatar.url),
            "created_at": datetime.datetime.now(JST).isoformat()
        }
        reminders.append(new_reminder)
        save_json(REMINDERS_FILE, reminders)
        await interaction.response.send_message("✅ 新しいリマインダーを登録しました。", ephemeral=True)

    @remind_group.command(name="edit", description="既存のリマインダーを編集します。")
    @app_commands.autocomplete(id=reminder_autocomplete)
    @app_commands.describe(
        id="編集したいリマインダーのID",
        date="新しい日付 (YYYY-MM-DD or YYYYMMDD)",
        target="新しい対象者",
        content="新しい内容",
        repeat="新しい繰り返しの設定"
    )
    @app_commands.choices(repeat=[
        app_commands.Choice(name="なし", value="none"), app_commands.Choice(name="毎週", value="weekly"),
        app_commands.Choice(name="毎月", value="monthly"), app_commands.Choice(name="毎年", value="yearly"),
    ])
    async def edit_reminder(self, interaction: discord.Interaction, id: str, date: str = None, target: str = None, content: str = None, repeat: app_commands.Choice[str] = None):
        reminders = load_json(REMINDERS_FILE)
        target_reminder = next((r for r in reminders if r.get("id") == id), None)
        if not target_reminder:
            await interaction.response.send_message("エラー: 指定されたIDのリマインダーが見つかりません。", ephemeral=True)
            return

        if date and (parsed_date := parse_date(date)):
            target_reminder["date"] = parsed_date
        if target: target_reminder["target"] = target
        if content: target_reminder["content"] = content
        if repeat: target_reminder["repeat"] = repeat.value
        
        save_json(REMINDERS_FILE, reminders)
        await interaction.response.send_message("✅ リマインダーを更新しました。", ephemeral=True)

    @remind_group.command(name="list", description="登録済みのリマインダーを一覧表示します。")
    async def list_reminders(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        reminders = sorted(load_json(REMINDERS_FILE), key=lambda r: r.get("date", ""))
        if not reminders:
            await interaction.followup.send("登録されているリマインダーはありません。", ephemeral=True)
            return
        embeds = [self.create_reminder_embed(r) for r in reminders]
        view = ReminderActionView(embeds, interaction, reminders)
        await interaction.followup.send(embed=embeds[0], view=view, ephemeral=True)

    def create_reminder_embed(self, reminder: dict) -> discord.Embed:
        embed = discord.Embed(title=f"{reminder['content']}", color=discord.Color.orange())
        embed.add_field(name="期日", value=reminder.get("date", "未設定"), inline=True)
        embed.add_field(name="対象", value=reminder.get("target", "未設定"), inline=True)
        embed.add_field(name="繰り返し", value=reminder.get("repeat", "なし"), inline=True)
        embed.set_footer(text=f"登録者: {reminder.get('creator_name', '不明')}", icon_url=reminder.get('creator_avatar'))
        return embed

    @tasks.loop(time=datetime.time(hour=9, minute=0, tzinfo=JST))
    async def check_reminders(self):
        today = datetime.date.today()
        reminders = load_json(REMINDERS_FILE)
        reminders_updated = False
        for r in reminders:
            try:
                task_date = datetime.datetime.fromisoformat(r.get("date")).date()
            except (ValueError, TypeError): continue
            if task_date == today:
                channel_id = int(os.getenv("PLAN_NOTICE_CHANNEL_ID", 0))
                if channel_id != 0 and (channel := self.bot.get_channel(channel_id)):
                    embed = discord.Embed(title=f"🚨 タスクリマインダー: {r['content']}", color=discord.Color.red(), description=f"対象: **{r.get('target')}**")
                    await channel.send(embed=embed)
                
                repeat_rule = r.get("repeat")
                if repeat_rule == "weekly": r["date"] = (task_date + relativedelta(weeks=1)).isoformat(); reminders_updated = True
                elif repeat_rule == "monthly": r["date"] = (task_date + relativedelta(months=1)).isoformat(); reminders_updated = True
                elif repeat_rule == "yearly": r["date"] = (task_date + relativedelta(years=1)).isoformat(); reminders_updated = True
        
        if reminders_updated: save_json(REMINDERS_FILE, reminders)

    @check_reminders.before_loop
    async def before_check_reminders(self): await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(CustomRemindersCog(bot))
