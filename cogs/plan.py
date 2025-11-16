import discord
from discord import app_commands
from discord.ext import commands
import datetime
import openpyxl

from .utils import (
    load_json, save_json, create_new_month_excel_if_needed, parse_date, parse_time,
    PLAN_LOG_FILE_NAME, get_group_options, get_location_options
)

class PlanModal(discord.ui.Modal, title="活動計画の入力"):
    activity_date = discord.ui.TextInput(label="活動日 (YYYY-MM-DD or YYYYMMDD)", placeholder="例: 2025-09-20")
    start_time = discord.ui.TextInput(label="活動予定時間 (開始)", placeholder="HH:MM または hhmm")
    end_time = discord.ui.TextInput(label="活動予定時間 (終了)", placeholder="HH:MM または hhmm")
    plan_details = discord.ui.TextInput(label="活動予定 (任意)", placeholder="具体的な活動内容があれば入力", required=False)
    
    def __init__(self, group: str, location: str, cog):
        super().__init__()
        self.group = group
        self.location = location
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_plan_submission(interaction, self)

class PlanCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    plan = app_commands.Group(name="plan", description="活動計画に関するコマンド")

    @plan.command(name="add", description="活動計画を入力します。")
    @app_commands.choices(
        group=[app_commands.Choice(name=opt, value=opt) for opt in get_group_options() if opt != "その他"],
        location=[app_commands.Choice(name=opt, value=opt) for opt in get_location_options() if opt != "その他"]
    )
    async def add_plan(self, interaction: discord.Interaction, group: app_commands.Choice[str], location: app_commands.Choice[str]):
        await interaction.response.send_modal(PlanModal(group=group.value, location=location.value, cog=self))

    async def handle_plan_submission(self, interaction: discord.Interaction, modal: PlanModal):
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            
            plan_date_str = parse_date(modal.activity_date.value)
            if not plan_date_str:
                await interaction.followup.send("エラー: 日付の形式が正しくありません。(例: 2025-09-20 or 20250920)", ephemeral=True)
                return
            plan_date = datetime.date.fromisoformat(plan_date_str)

            target_filename, error_msg = await create_new_month_excel_if_needed(plan_date.year, plan_date.month)
            if error_msg:
                await interaction.followup.send(f"エラー: {error_msg}", ephemeral=True)
                return

            formatted_start, formatted_end = parse_time(modal.start_time.value), parse_time(modal.end_time.value)
            if not formatted_start or not formatted_end:
                await interaction.followup.send("エラー: 時間の形式が正しくありません。「HH:MM」または「hhmm」形式で入力してください。", ephemeral=True)
                return

            plan_log = load_json(PLAN_LOG_FILE_NAME)
            if plan_date_str not in plan_log: plan_log[plan_date_str] = {"groups": {}}
            plan_log[plan_date_str]["groups"][modal.group] = {
                "start_time": formatted_start, "end_time": formatted_end,
                "location": modal.location, "plan_details": modal.plan_details.value,
            }
            save_json(PLAN_LOG_FILE_NAME, plan_log)

            todays_plans = plan_log[plan_date_str]["groups"]
            final_start = min(v["start_time"] for v in todays_plans.values() if v["start_time"])
            final_end = max(v["end_time"] for v in todays_plans.values() if v["end_time"])
            location_parts = [f'{v["location"]}({k})' if k and k != "その他" else v["location"] for k, v in todays_plans.items()]
            final_location = " | ".join(location_parts)
            plan_detail_parts = [f"{plan_info.get('plan_details') or ''}({gn})" if (gn and gn != "その他" and plan_info.get('plan_details')) else (plan_info.get('plan_details') or gn) for gn, plan_info in todays_plans.items()]
            final_plan_details = "、".join(plan_detail_parts)

            try:
                workbook = openpyxl.load_workbook(target_filename)
                sheet = workbook["活動計画書"]
                target_row = plan_date.day + 6
                sheet[f"C{target_row}"] = final_start; sheet[f"E{target_row}"] = final_end
                sheet[f"F{target_row}"] = final_location; sheet[f"G{target_row}"] = final_plan_details
                workbook.save(target_filename)
                await interaction.followup.send(f"{plan_date_str} の活動計画を記録しました。", ephemeral=True)
            except (FileNotFoundError, KeyError) as e:
                await interaction.followup.send(f"Excelエラー: {e}", ephemeral=True)
        except Exception as e:
            print(f"An error occurred in handle_plan_submission: {e}")
            await interaction.followup.send(f"申し訳ありません、エラーが発生しました: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(PlanCog(bot))
