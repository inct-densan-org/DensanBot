import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import os
import uuid
from typing import List

from .ui_components import PaginationView, ReminderView
from .utils import (
    load_json, save_json, JST, WEEKDAYS, parse_time, parse_date,
    REGULAR_PLANS_FILE, OFF_PERIODS_FILE, PLAN_LOG_FILE_NAME,
    get_group_options, get_location_options # 選択肢取得関数をインポート
)

WEEKDAY_CHOICES = [app_commands.Choice(name=day, value=i) for i, day in enumerate(WEEKDAYS)]
PLAN_NOTICE_CHANNEL_ID = int(os.getenv("PLAN_NOTICE_CHANNEL_ID", 0))
REMIND_BEFORE_MINUTES = 15

# --- オートコンプリート用の関数 ---
async def group_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    groups = get_group_options()
    return [app_commands.Choice(name=group, value=group) for group in groups if current.lower() in group.lower()]

async def location_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    locations = get_location_options()
    return [app_commands.Choice(name=loc, value=loc) for loc in locations if current.lower() in loc.lower()]

def get_channel_id_for_group(group_name: str) -> int:
    env_var_name = f"{group_name.upper().replace('･', '_')}_CHANNEL_ID"
    channel_id = os.getenv(env_var_name)
    return int(channel_id) if channel_id and channel_id.isdigit() else PLAN_NOTICE_CHANNEL_ID

class ScheduleManagerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminders_sent_today = set()
        self.daily_schedule_notifier.start()
        self.reminder_task.start()
        self.annual_reminder.start()

    def cog_unload(self):
        self.daily_schedule_notifier.cancel()
        self.reminder_task.cancel()
        self.annual_reminder.cancel()

    schedule = app_commands.Group(name="schedule", description="スケジュール関連の全コマンド")
    regular = app_commands.Group(name="regular", parent=schedule, description="定期活動の管理")
    off_period = app_commands.Group(name="off-period", parent=schedule, description="活動休止期間の管理")

    @schedule.command(name="send_reminder", description="テスト用にリマインドメッセージを送信します。")
    async def send_reminder(self, interaction: discord.Interaction):
        embed = discord.Embed(title="💡 活動終了時刻が近づいています", description="活動報告の準備をお願いします。\n下のボタンを押して報告フォームを開くことができます。", color=discord.Color.gold(), timestamp=datetime.datetime.now())
        embed.set_footer(text="電算部Bot")
        report_cog = self.bot.get_cog("ReportCog")
        if report_cog:
            await interaction.channel.send(embed=embed, view=ReminderView(report_cog))
            await interaction.response.send_message("リマインドメッセージを送信しました。", ephemeral=True)
        else:
            await interaction.response.send_message("エラー: ReportCogの読み込みに失敗しました。", ephemeral=True)

    @regular.command(name="add", description="定期的な活動を登録します。")
    @app_commands.choices(weekday=WEEKDAY_CHOICES)
    @app_commands.autocomplete(group=group_autocomplete, location=location_autocomplete) # オートコンプリートを適用
    @app_commands.describe(start_time="HH:MM or hhmm", end_time="HH:MM or hhmm")
    async def add_regular_plan(self, interaction: discord.Interaction, weekday: app_commands.Choice[int], group: str, location: str, start_time: str, end_time: str):
        s_time, e_time = parse_time(start_time), parse_time(end_time)
        if not s_time or not e_time:
            await interaction.response.send_message("エラー: 時間の形式が正しくありません。", ephemeral=True)
            return
        plans = load_json(REGULAR_PLANS_FILE)
        plans.append({"id": str(uuid.uuid4()), "weekday": weekday.value, "group": group, "location": location, "start_time": s_time, "end_time": e_time})
        save_json(REGULAR_PLANS_FILE, plans)
        await interaction.response.send_message(f"✅ 毎週{weekday.name}曜日の {group} の活動を登録しました。", ephemeral=True)

    @regular.command(name="list", description="登録済みの定期活動を一覧表示します。")
    async def list_regular_plans(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        plans = sorted(load_json(REGULAR_PLANS_FILE), key=lambda p: p["weekday"])
        if not plans:
            await interaction.followup.send("登録されている定期活動はありません。", ephemeral=True)
            return
        embeds = [self.create_regular_plan_embed(p) for p in plans]
        view = PaginationView(embeds, interaction)
        await interaction.followup.send(embed=embeds[0], view=view, ephemeral=True)

    def create_regular_plan_embed(self, plan: dict) -> discord.Embed:
        embed = discord.Embed(title=f"定期活動: 毎週{WEEKDAYS[plan['weekday']]}曜日 ({plan['group']})", color=discord.Color.purple())
        embed.add_field(name="時間", value=f"{plan['start_time']} - {plan['end_time']}", inline=False)
        embed.add_field(name="場所", value=plan['location'], inline=False)
        return embed

    @off_period.command(name="add", description="活動休止期間を登録します。")
    @app_commands.describe(name="期間の名称 (例: 前期中間テスト)", start_date="YYYY-MM-DD or YYYYMMDD", end_date="YYYY-MM-DD or YYYYMMDD")
    @app_commands.choices(is_test_period=[app_commands.Choice(name="はい", value=1), app_commands.Choice(name="いいえ", value=0)])
    async def add_off_period(self, interaction: discord.Interaction, name: str, start_date: str, end_date: str, is_test_period: app_commands.Choice[int]):
        s_date, e_date = parse_date(start_date), parse_date(end_date)
        if not s_date or not e_date:
            await interaction.response.send_message("エラー: 日付の形式が正しくありません。", ephemeral=True)
            return
        periods = load_json(OFF_PERIODS_FILE)
        periods.append({"id": str(uuid.uuid4()), "name": name, "start_date": s_date, "end_date": e_date, "is_test_period": bool(is_test_period.value)})
        save_json(OFF_PERIODS_FILE, periods)
        await interaction.response.send_message(f"✅ 活動休止期間「{name}」を登録しました。", ephemeral=True)

    @off_period.command(name="list", description="登録済みの活動休止期間を一覧表示します。")
    async def list_off_periods(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        periods = sorted(load_json(OFF_PERIODS_FILE), key=lambda p: p["start_date"])
        if not periods:
            await interaction.followup.send("登録されている活動休止期間はありません。", ephemeral=True)
            return
        embeds = [self.create_off_period_embed(p) for p in periods]
        view = PaginationView(embeds, interaction)
        await interaction.followup.send(embed=embeds[0], view=view, ephemeral=True)

    def create_off_period_embed(self, period: dict) -> discord.Embed:
        embed = discord.Embed(title=f"休止期間: {period['name']}", color=discord.Color.dark_grey())
        embed.add_field(name="期間", value=f"{period['start_date']} ~ {period['end_date']}", inline=False)
        if period["is_test_period"]:
            embed.set_footer(text="※テスト期間として設定済み（前後1週間も活動休止扱い）")
        return embed

    @tasks.loop(time=datetime.time(hour=8, minute=0, tzinfo=JST))
    async def daily_schedule_notifier(self):
        self.reminders_sent_today.clear()
        print(f"[{datetime.datetime.now(JST)}] Reminders sent list has been reset.")
        if PLAN_NOTICE_CHANNEL_ID == 0 or not (channel := self.bot.get_channel(PLAN_NOTICE_CHANNEL_ID)): return
        plan_log = load_json(PLAN_LOG_FILE_NAME)
        today_str = datetime.date.today().isoformat()
        if not (todays_plans := plan_log.get(today_str, {}).get("groups")): return
        embed = discord.Embed(title=f"📢 今日の活動予定 ({datetime.date.today().strftime('%m/%d')})", color=discord.Color.blue())
        for group, plan in todays_plans.items():
            embed.add_field(name=f"【{group}】 {plan.get('start_time', '?')} - {plan.get('end_time', '?')}", value=f"**場所:** {plan.get('location', '?')}\n**予定:** {plan.get('plan_details', '特になし')}", inline=False)
        embed.set_footer(text="活動計画は /plan add コマンドで追加・更新できます。")
        await channel.send(embed=embed)

    @tasks.loop(minutes=1)
    async def reminder_task(self):
        try:
            plan_log = load_json(PLAN_LOG_FILE_NAME)
            today_str = datetime.date.today().isoformat()
            if not (todays_plans := plan_log.get(today_str, {}).get("groups")): return
            now_time = datetime.datetime.now(JST).time()
            for group_name, plan in todays_plans.items():
                if group_name in self.reminders_sent_today or not (end_time_str := plan.get("end_time")): continue
                try:
                    end_time = datetime.datetime.strptime(end_time_str, "%H:%M").time()
                    remind_time = (datetime.datetime.combine(datetime.date.today(), end_time) - datetime.timedelta(minutes=REMIND_BEFORE_MINUTES)).time()
                except ValueError: continue
                if remind_time <= now_time < end_time:
                    if (channel_id := get_channel_id_for_group(group_name)) == 0 or not (channel := self.bot.get_channel(channel_id)): continue
                    report_cog = self.bot.get_cog("ReportCog")
                    if report_cog:
                        embed = discord.Embed(title=f"💡【{group_name}】活動終了時刻が近づいています", description=f"終了時刻: **{end_time_str}**\n活動報告の準備をお願いします。", color=discord.Color.gold())
                        await channel.send(embed=embed, view=ReminderView(report_cog))
                        self.reminders_sent_today.add(group_name)
                        print(f"Sent reminder to {group_name} in channel {channel_id}")
        except Exception as e: print(f"An error occurred in reminder_task: {e}")

    @tasks.loop(time=datetime.time(hour=9, minute=0, tzinfo=JST))
    async def annual_reminder(self):
        today = datetime.date.today()
        if today.month == 4 and today.day == 1:
            if (channel_id := PLAN_NOTICE_CHANNEL_ID) != 0 and (channel := self.bot.get_channel(channel_id)):
                await channel.send("新年度です！今年度の長期休業やテスト期間を `/schedule off-period add` コマンドで登録してください。")

    @daily_schedule_notifier.before_loop
    @reminder_task.before_loop
    @annual_reminder.before_loop
    async def before_tasks(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(ScheduleManagerCog(bot))
