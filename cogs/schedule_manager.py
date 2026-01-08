import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import os
import uuid
from typing import List, Optional, Dict

from .ui_components import PagedItemView, ConfirmView, ReminderView
from .utils import (
    load_json, save_json, JST, WEEKDAYS, parse_time, parse_date,
    REGULAR_PLANS_FILE, OFF_PERIODS_FILE, PLAN_LOG_FILE_NAME,
    get_group_options, get_location_options, generate_monthly_schedule,
    group_autocomplete, location_autocomplete
)

WEEKDAY_CHOICES = [app_commands.Choice(name=day, value=i) for i, day in enumerate(WEEKDAYS)]
PLAN_NOTICE_CHANNEL_ID = int(os.getenv("PLAN_NOTICE_CHANNEL_ID", 0))
REMIND_BEFORE_MINUTES = 15

def get_channel_id_for_group(group_name: str) -> int:
    env_var_name = f"{group_name.upper().replace('･', '_')}_CHANNEL_ID"
    channel_id = os.getenv(env_var_name)
    return int(channel_id) if channel_id and channel_id.isdigit() else PLAN_NOTICE_CHANNEL_ID

class RegularPlanDetailView(discord.ui.View):
    def __init__(self, plan: dict):
        super().__init__(timeout=60)
        self.plan = plan

    @discord.ui.button(label="削除", style=discord.ButtonStyle.danger)
    async def delete_plan(self, interaction: discord.Interaction, button: discord.ui.Button):
        confirm_view = ConfirmView()
        await interaction.response.send_message(f"**確認:** 毎週{WEEKDAYS[self.plan['weekday']]}曜日の **{self.plan['group']}** の定期活動を本当に削除しますか？", view=confirm_view, ephemeral=True)
        await confirm_view.wait()
        if confirm_view.value:
            plan_id = self.plan.get("id")
            updated_plans = [p for p in load_json(REGULAR_PLANS_FILE) if p.get("id") != plan_id]
            save_json(REGULAR_PLANS_FILE, updated_plans)
            
            # 今月と来月のスケジュールを更新
            today = datetime.datetime.now(JST).date()
            generate_monthly_schedule(today.year, today.month, overwrite=False)
            next_month = today.replace(day=28) + datetime.timedelta(days=4)
            generate_monthly_schedule(next_month.year, next_month.month, overwrite=False)

            await interaction.followup.send(f"✅ 定期活動を削除し、スケジュールを更新しました。", ephemeral=True)
        else:
            await interaction.followup.send("操作をキャンセルしました。", ephemeral=True)

class OffPeriodDetailView(discord.ui.View):
    def __init__(self, period: dict):
        super().__init__(timeout=60)
        self.period = period

    @discord.ui.button(label="削除", style=discord.ButtonStyle.danger)
    async def delete_period(self, interaction: discord.Interaction, button: discord.ui.Button):
        confirm_view = ConfirmView()
        await interaction.response.send_message(f"**確認:** 休止期間「{self.period['name']}」を本当に削除しますか？", view=confirm_view, ephemeral=True)
        await confirm_view.wait()
        if confirm_view.value:
            period_id = self.period.get("id")
            updated_periods = [p for p in load_json(OFF_PERIODS_FILE) if p.get("id") != period_id]
            save_json(OFF_PERIODS_FILE, updated_periods)

            # 今月と来月のスケジュールを更新
            today = datetime.datetime.now(JST).date()
            generate_monthly_schedule(today.year, today.month, overwrite=False)
            next_month = today.replace(day=28) + datetime.timedelta(days=4)
            generate_monthly_schedule(next_month.year, next_month.month, overwrite=False)

            await interaction.followup.send(f"✅ 休止期間「{self.period['name']}」を削除し、スケジュールを更新しました。", ephemeral=True)
        else:
            await interaction.followup.send("操作をキャンセルしました。", ephemeral=True)

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

    @schedule.command(name="generate_sheet", description="指定した月の活動計画をExcelとJSONに生成・更新します。")
    @app_commands.describe(year="西暦年 (省略時は今年)", month="月 (省略時は今月)", overwrite="Trueにすると、既存の定期活動予定を洗い替えます。")
    async def generate_sheet(self, interaction: discord.Interaction, year: Optional[int] = None, month: Optional[int] = None, overwrite: bool = False):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        target_date = datetime.datetime.now(JST).date()
        target_year = year if year is not None else target_date.year
        target_month = month if month is not None else target_date.month

        _, error_msg = generate_monthly_schedule(target_year, target_month, overwrite)
        if error_msg:
            await interaction.followup.send(f"エラー: {error_msg}", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ {target_year}年{target_month}月の活動計画を生成・更新しました。", ephemeral=True)

    @schedule.command(name="send_reminder", description="テスト用にリマインドメッセージを送信します。")
    @app_commands.describe(group="リマインダーを送る対象のグループ")
    @app_commands.autocomplete(group=group_autocomplete)
    async def send_reminder(self, interaction: discord.Interaction, group: str):
        report_cog = self.bot.get_cog("ReportCog")
        if not report_cog:
            await interaction.response.send_message("エラー: ReportCogの読み込みに失敗しました。", ephemeral=True)
            return

        embed = discord.Embed(title=f"💡【{group}】活動終了時刻が近づいています", description=f"活動報告の準備をお願いします。", color=discord.Color.gold())
        view = ReminderView(report_cog)
        
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("リマインドメッセージを送信しました。", ephemeral=True)

    @regular.command(name="add", description="定期的な活動を登録します。")
    @app_commands.choices(weekday=WEEKDAY_CHOICES)
    @app_commands.autocomplete(group=group_autocomplete, location=location_autocomplete)
    @app_commands.describe(start_time="HH:MM or hhmm", end_time="HH:MM or hhmm")
    async def add_regular_plan(self, interaction: discord.Interaction, weekday: app_commands.Choice[int], group: str, location: str, start_time: str, end_time: str):
        s_time, e_time = parse_time(start_time), parse_time(end_time)
        if not s_time or not e_time:
            await interaction.response.send_message("エラー: 時間の形式が正しくありません。", ephemeral=True)
            return
        plans = load_json(REGULAR_PLANS_FILE)
        plans.append({"id": str(uuid.uuid4()), "weekday": weekday.value, "group": group, "location": location, "start_time": s_time, "end_time": e_time})
        save_json(REGULAR_PLANS_FILE, plans)
        
        # 今月と来月のスケジュールを更新
        today = datetime.datetime.now(JST).date()
        generate_monthly_schedule(today.year, today.month, overwrite=False)
        next_month = today.replace(day=28) + datetime.timedelta(days=4)
        generate_monthly_schedule(next_month.year, next_month.month, overwrite=False)

        await interaction.response.send_message(f"✅ 毎週{weekday.name}曜日の {group} の活動を登録し、スケジュールを更新しました。", ephemeral=True)

    @regular.command(name="list", description="登録済みの定期活動を一覧表示します。")
    async def list_regular_plans(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        plans = sorted(load_json(REGULAR_PLANS_FILE), key=lambda p: p["weekday"])
        if not plans:
            await interaction.followup.send("登録されている定期活動はありません。", ephemeral=True)
            return

        def embed_factory(items: List[Dict], current_page: int, total_pages: int) -> discord.Embed:
            embed = discord.Embed(title="定期活動一覧", color=discord.Color.purple())
            for p in items:
                title = f"毎週{WEEKDAYS[p['weekday']]}曜日 ({p['group']})"
                value = f"**時間:** {p['start_time']} - {p['end_time']}\n**場所:** {p['location']}"
                embed.add_field(name=title, value=value, inline=False)
            
            embed.set_footer(text=f"ページ {current_page}/{total_pages}")
            return embed

        def select_options_factory(items: List[Dict]) -> List[discord.SelectOption]:
            options = []
            for p in items:
                label = f"毎週{WEEKDAYS[p['weekday']]}曜日 - {p['group']}"
                if len(label) > 100: label = label[:97] + "..."
                
                value = p.get("id")
                
                description = f"{p['start_time']} - {p['end_time']} @ {p['location']}"
                if len(description) > 100: description = description[:97] + "..."

                options.append(discord.SelectOption(label=label, value=value, description=description))
            return options

        async def on_select_callback(interaction: discord.Interaction, selected_value: str):
            selected_plan = next((p for p in plans if p.get("id") == selected_value), None)
            if selected_plan:
                embed = discord.Embed(title=f"定期活動: 毎週{WEEKDAYS[selected_plan['weekday']]}曜日 ({selected_plan['group']})", color=discord.Color.purple())
                embed.add_field(name="時間", value=f"{selected_plan['start_time']} - {selected_plan['end_time']}", inline=False)
                embed.add_field(name="場所", value=selected_plan['location'], inline=False)
                
                view = RegularPlanDetailView(selected_plan)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.response.send_message("エラー: 選択された定期活動が見つかりませんでした。", ephemeral=True)

        view = PagedItemView(plans, interaction, embed_factory, select_options_factory, on_select_callback)
        await interaction.followup.send(embed=embed_factory(plans[:3], 1, view.total_pages), view=view, ephemeral=True)

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

        # 今月と来月のスケジュールを更新
        today = datetime.datetime.now(JST).date()
        generate_monthly_schedule(today.year, today.month, overwrite=False)
        next_month = today.replace(day=28) + datetime.timedelta(days=4)
        generate_monthly_schedule(next_month.year, next_month.month, overwrite=False)

        await interaction.response.send_message(f"✅ 活動休止期間「{name}」を登録し、スケジュールを更新しました。", ephemeral=True)

    @off_period.command(name="list", description="登録済みの活動休止期間を一覧表示します。")
    async def list_off_periods(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        periods = sorted(load_json(OFF_PERIODS_FILE), key=lambda p: p["start_date"])
        if not periods:
            await interaction.followup.send("登録されている活動休止期間はありません。", ephemeral=True)
            return

        def embed_factory(items: List[Dict], current_page: int, total_pages: int) -> discord.Embed:
            embed = discord.Embed(title="活動休止期間一覧", color=discord.Color.dark_grey())
            for p in items:
                title = f"{p['name']}"
                value = f"**期間:** {p['start_date']} ~ {p['end_date']}"
                if p["is_test_period"]:
                    value += "\n※テスト期間"
                embed.add_field(name=title, value=value, inline=False)
            
            embed.set_footer(text=f"ページ {current_page}/{total_pages}")
            return embed

        def select_options_factory(items: List[Dict]) -> List[discord.SelectOption]:
            options = []
            for p in items:
                label = f"{p['name']}"
                if len(label) > 100: label = label[:97] + "..."
                
                value = p.get("id")
                
                description = f"{p['start_date']} ~ {p['end_date']}"
                if len(description) > 100: description = description[:97] + "..."

                options.append(discord.SelectOption(label=label, value=value, description=description))
            return options

        async def on_select_callback(interaction: discord.Interaction, selected_value: str):
            selected_period = next((p for p in periods if p.get("id") == selected_value), None)
            if selected_period:
                embed = discord.Embed(title=f"休止期間: {selected_period['name']}", color=discord.Color.dark_grey())
                embed.add_field(name="期間", value=f"{selected_period['start_date']} ~ {selected_period['end_date']}", inline=False)
                if selected_period["is_test_period"]:
                    embed.set_footer(text="※テスト期間として設定済み（前後1週間も活動休止扱い）")
                
                view = OffPeriodDetailView(selected_period)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.response.send_message("エラー: 選択された休止期間が見つかりませんでした。", ephemeral=True)

        view = PagedItemView(periods, interaction, embed_factory, select_options_factory, on_select_callback)
        await interaction.followup.send(embed=embed_factory(periods[:3], 1, view.total_pages), view=view, ephemeral=True)

    @tasks.loop(time=datetime.time(hour=8, minute=0, tzinfo=JST))
    async def daily_schedule_notifier(self):
        self.reminders_sent_today.clear()
        print(f"[{datetime.datetime.now(JST)}] Reminders sent list has been reset.")
        
        # --- 月初の自動生成処理 ---
        today = datetime.datetime.now(JST).date()
        if today.day == 1:
            # 来月のスケジュールを生成
            next_month = today.replace(day=28) + datetime.timedelta(days=4)
            generate_monthly_schedule(next_month.year, next_month.month, overwrite=False)
            print(f"[{datetime.datetime.now(JST)}] Generated schedule for {next_month.year}-{next_month.month}")

        if PLAN_NOTICE_CHANNEL_ID == 0 or not (channel := self.bot.get_channel(PLAN_NOTICE_CHANNEL_ID)): return
        plan_log = load_json(PLAN_LOG_FILE_NAME)
        today_str = today.isoformat()
        if not (todays_plans := plan_log.get(today_str, {}).get("groups")): return
        embed = discord.Embed(title=f"📢 今日の活動予定 ({today.strftime('%m/%d')})", color=discord.Color.blue())
        for group, plan in sorted(todays_plans.items()):
            embed.add_field(name=f"【{group}】 {plan.get('start_time', '?')} - {plan.get('end_time', '?')}", value=f"**場所:** {plan.get('location', '?')}\n**予定:** {plan.get('plan_details', '特になし')}", inline=False)
        embed.set_footer(text="活動計画は /plan list コマンドで編集・削除できます。")
        await channel.send(embed=embed)

    @tasks.loop(minutes=1)
    async def reminder_task(self):
        try:
            plan_log = load_json(PLAN_LOG_FILE_NAME)
            today_str = datetime.datetime.now(JST).date().isoformat()
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
        today = datetime.datetime.now(JST).date()
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
