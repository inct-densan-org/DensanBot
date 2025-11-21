import discord
from discord import app_commands
from discord.ext import commands
import re
import datetime
import openpyxl
from openpyxl.utils.exceptions import InvalidFileException
import os

from .utils import (
    load_json, save_json, get_excel_filename_for_month, parse_time,
    REPORT_LOG_FILE, ZEN_TO_HAN, get_group_options, get_location_options
)
from .ui_components import ReportModal, ReminderView, get_todays_plan_defaults

REPORT_NOTICE_CHANNEL_ID = int(os.getenv("REPORT_NOTICE_CHANNEL_ID", 0))

class ReportCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(ReminderView(self))

    report = app_commands.Group(name="report", description="活動報告に関するコマンド")

    @report.command(name="open", description="活動報告モーダルを開きます。")
    @app_commands.choices(
        group=[app_commands.Choice(name=opt, value=opt) for opt in get_group_options()],
        location=[app_commands.Choice(name=opt, value=opt) for opt in get_location_options()]
    )
    async def open_modal(self, interaction: discord.Interaction, group: app_commands.Choice[str], location: app_commands.Choice[str]):
        defaults = get_todays_plan_defaults(group.value)
        await interaction.response.send_modal(
            ReportModal(
                cog=self, 
                group=group.value,
                location=location.value,
                default_activity_time=defaults.get("activity_time")
            )
        )

    async def handle_report_submission(self, interaction: discord.Interaction, modal: ReportModal):
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            today = datetime.date.today()
            target_excel_file = get_excel_filename_for_month(today.year, today.month)
            if not os.path.exists(target_excel_file):
                await interaction.followup.send(f"エラー: 今月({today.year}年{today.month}月)のExcelファイルが存在しません。`/plan add`で計画を立てると自動で作成されます。", ephemeral=True)
                return

            raw_time = modal.activity_time.value.translate(ZEN_TO_HAN)
            times = re.findall(r'(\d{1,2}:\d{2}|\d{3,4})', raw_time)
            start_str, end_str = (times[0], times[1]) if len(times) >= 2 else (None, None)
            start_time, end_time = parse_time(start_str), parse_time(end_str)
            if not start_time or not end_time:
                await interaction.followup.send("エラー: 活動時間の形式が正しくありません。(例: 15:00-17:00 or 1500-1700)", ephemeral=True)
                return

            try: participants_num = int(modal.participants.value.translate(ZEN_TO_HAN))
            except (ValueError, TypeError): participants_num = 0
            
            group_name = modal.group.value
            location_name = modal.location.value

            report_log = load_json(REPORT_LOG_FILE)
            today_str = today.isoformat()
            if today_str not in report_log: report_log[today_str] = {"groups": {}}
            report_log[today_str]["groups"][group_name] = {
                "start_time": start_time, "end_time": end_time, "location": location_name, 
                "participants": participants_num, "description": modal.description.value, "reporter": interaction.user.display_name,
            }
            save_json(REPORT_LOG_FILE, report_log)
            
            todays_reports = report_log[today_str]["groups"]
            final_start = min((v["start_time"] for v in todays_reports.values() if v["start_time"]), default="")
            final_end = max((v["end_time"] for v in todays_reports.values() if v["end_time"]), default="")
            total_participants = sum(v["participants"] for v in todays_reports.values())
            loc_parts = [f'{v["location"]}({k})' if k and k != "その他" else v["location"] for k, v in todays_reports.items()]
            final_loc = " | ".join(sorted(list(set(loc_parts))))
            desc_parts = [f'({k}) {v["description"]}' if v.get("description") and k and k != "その他" else (v.get("description") or "") for k, v in todays_reports.items()]
            final_desc = " | ".join(filter(None, desc_parts))

            try:
                workbook = openpyxl.load_workbook(target_excel_file)
                sheet = workbook["活動報告書"]
                target_row = today.day + 6
                sheet[f"C{target_row}"] = final_start; sheet[f"E{target_row}"] = final_end
                sheet[f"F{target_row}"] = final_loc; sheet[f"G{target_row}"] = total_participants if total_participants > 0 else None
                sheet[f"I{target_row}"] = final_desc
                workbook.save(target_excel_file)
                await interaction.followup.send("活動報告、お疲れ様でした！Excelファイルに記録しました。", ephemeral=True)
            except (FileNotFoundError, InvalidFileException, KeyError) as e:
                await interaction.followup.send(f"Excelエラー: {e}", ephemeral=True)
                return

            if REPORT_NOTICE_CHANNEL_ID != 0 and (notice_channel := interaction.guild.get_channel(REPORT_NOTICE_CHANNEL_ID)):
                embed = discord.Embed(title=f"📝 活動報告がありました ({group_name})", color=discord.Color.green(), timestamp=datetime.datetime.now())
                embed.add_field(name="活動時間", value=f"{start_time} - {end_time}", inline=False)
                embed.add_field(name="活動場所", value=location_name, inline=True)
                embed.add_field(name="活動人数", value=f"{participants_num}人", inline=True)
                if modal.description.value: embed.add_field(name="活動内容・備考", value=modal.description.value, inline=False)
                embed.set_footer(text=f"報告者: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
                await notice_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none(), silent=True)
        except Exception as e:
            print(f"An error occurred in handle_report_submission: {e}")
            await interaction.followup.send(f"申し訳ありません、エラーが発生しました。\n`{e}`", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ReportCog(bot))
