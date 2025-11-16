import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import datetime
import uuid
from dateutil.relativedelta import relativedelta

from .ui_components import PaginationView
from .utils import load_json, save_json, parse_date, REMINDERS_FILE, JST

REPEAT_OPTIONS = [
    discord.SelectOption(label="なし", value="none", description="この日1回のみ通知します。"),
    discord.SelectOption(label="毎週", value="weekly", description="毎週同じ曜日に通知します。"),
    discord.SelectOption(label="毎月", value="monthly", description="毎月同じ日に通知します。"),
    discord.SelectOption(label="毎年", value="yearly", description="毎年同じ日付に通知します。"),
]

class ReminderModal(discord.ui.Modal, title="リマインダーの登録・編集"):
    def __init__(self, cog, reminder: dict = None):
        super().__init__()
        self.cog = cog
        self.reminder = reminder
        self.task_date.default = reminder.get("date") if reminder else None
        self.target.default = reminder.get("target") if reminder else None
        self.content.default = reminder.get("content") if reminder else None
        
        # --- デフォルト値設定のロジックを修正 ---
        current_repeat = reminder.get("repeat", "none") if reminder else "none"
        
        # 動的にデフォルト値を設定したオプションリストを作成
        options_with_default = []
        for option in REPEAT_OPTIONS:
            # 元のオプションをコピーして、default値を設定
            new_option = discord.SelectOption(
                label=option.label,
                value=option.value,
                description=option.description,
                default=(option.value == current_repeat) # ここが重要
            )
            options_with_default.append(new_option)

        self.repeat_select = discord.ui.Select(
            options=options_with_default, 
            placeholder="繰り返し設定を選択"
        )
        self.add_item(self.repeat_select)

    task_date = discord.ui.TextInput(label="日付 (YYYY-MM-DD or YYYYMMDD)", placeholder="例: 2025-04-01")
    target = discord.ui.TextInput(label="対象者", placeholder="例: 部長, 会計担当")
    content = discord.ui.TextInput(label="内容", style=discord.TextStyle.paragraph, placeholder="例: ドメイン更新")
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_reminder_submission(interaction, self)

class ReminderActionView(PaginationView):
    def __init__(self, embeds: list[discord.Embed], interaction: discord.Interaction, reminders: list[dict], cog):
        super().__init__(embeds, interaction)
        self.reminders = reminders
        self.cog = cog

    @discord.ui.button(label="編集", style=discord.ButtonStyle.secondary, row=1)
    async def edit_reminder(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReminderModal(cog=self.cog, reminder=self.reminders[self.current_page]))

    @discord.ui.button(label="削除", style=discord.ButtonStyle.danger, row=1)
    async def delete_reminder(self, interaction: discord.Interaction, button: discord.ui.Button):
        reminder_to_delete = self.reminders[self.current_page]
        rem_id = reminder_to_delete.get("id")
        updated_reminders = [r for r in load_json(REMINDERS_FILE) if r.get("id") != rem_id]
        save_json(REMINDERS_FILE, updated_reminders)
        await interaction.response.send_message(f"リマインダー「{reminder_to_delete['content'][:20]}...」を削除しました。", ephemeral=True)
        await self.interaction.message.delete()

class CustomRemindersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_reminders.start()

    def cog_unload(self): self.check_reminders.cancel()

    remind_group = app_commands.Group(name="remind", description="カスタムリマインダー機能")

    @remind_group.command(name="add", description="新しいリマインダーを登録します。")
    async def add_reminder(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ReminderModal(cog=self))

    @remind_group.command(name="list", description="登録済みのリマインダーを一覧表示します。")
    async def list_reminders(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        reminders = sorted(load_json(REMINDERS_FILE), key=lambda r: r.get("date", ""))
        if not reminders:
            await interaction.followup.send("登録されているリマインダーはありません。", ephemeral=True)
            return
        embeds = [self.create_reminder_embed(r) for r in reminders]
        view = ReminderActionView(embeds, interaction, reminders, self)
        await interaction.followup.send(embed=embeds[0], view=view, ephemeral=True)

    async def handle_reminder_submission(self, interaction: discord.Interaction, modal: ReminderModal):
        date_str = parse_date(modal.task_date.value)
        if not date_str:
            await interaction.response.send_message("エラー: 日付の形式が正しくありません。(例: 2025-09-20 or 20250920)", ephemeral=True)
            return
        
        reminders = load_json(REMINDERS_FILE)
        repeat_value = modal.repeat_select.values[0] if modal.repeat_select.values else "none"
        if modal.reminder:
            for r in reminders:
                if r.get("id") == modal.reminder["id"]:
                    r.update({"date": date_str, "target": modal.target.value, "content": modal.content.value, "repeat": repeat_value})
                    break
            await interaction.response.send_message("✅ リマインダーを更新しました。", ephemeral=True)
        else:
            new_reminder = {
                "id": str(uuid.uuid4()), "date": date_str, "target": modal.target.value,
                "content": modal.content.value, "repeat": repeat_value,
                "creator_name": interaction.user.display_name, "creator_avatar": str(interaction.user.display_avatar.url),
                "created_at": datetime.datetime.now(JST).isoformat()
            }
            reminders.append(new_reminder)
            await interaction.response.send_message("✅ 新しいリマインダーを登録しました。", ephemeral=True)
        save_json(REMINDERS_FILE, reminders)

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
