import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import datetime

from .ui_components import PaginationView, ConfirmView
from .utils import (
    load_json, save_json, REPORT_LOG_FILE, PLAN_LOG_FILE_NAME, WEEKDAYS
)

class ReportHistoryActionView(PaginationView):
    def __init__(self, embeds: list[discord.Embed], interaction: discord.Interaction, reports: list[dict]):
        super().__init__(embeds, interaction)
        self.reports = reports

    @discord.ui.button(label="削除", style=discord.ButtonStyle.danger, row=1)
    async def delete_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        report_to_delete = self.reports[self.current_page]
        confirm_view = ConfirmView()
        await interaction.response.send_message(f"**確認:** {report_to_delete['date']} の **{report_to_delete['group']}** の報告を本当に削除しますか？", view=confirm_view, ephemeral=True)
        await confirm_view.wait()
        if confirm_view.value:
            date_str, group_name = report_to_delete["date"], report_to_delete["group"]
            report_log = load_json(REPORT_LOG_FILE)
            if date_str in report_log and group_name in report_log[date_str]["groups"]:
                del report_log[date_str]["groups"][group_name]
                if not report_log[date_str]["groups"]: del report_log[date_str]
                save_json(REPORT_LOG_FILE, report_log)
                await interaction.followup.send(f"✅ {date_str} の {group_name} の報告を削除しました。", ephemeral=True)
                await interaction.message.delete()
            else:
                await interaction.followup.send("エラー: 対象の報告が見つかりませんでした。", ephemeral=True)
        else:
            await interaction.followup.send("操作をキャンセルしました。", ephemeral=True)

class UnreportedActionView(PaginationView):
    def __init__(self, embeds: list[discord.Embed], interaction: discord.Interaction, unreported_plans: list[dict]):
        super().__init__(embeds, interaction)
        self.unreported_plans = unreported_plans

    @discord.ui.button(label="「活動なし」として報告", style=discord.ButtonStyle.primary, row=1)
    async def report_as_no_activity(self, interaction: discord.Interaction, button: discord.ui.Button):
        plan = self.unreported_plans[self.current_page]
        date_str, group_name = plan["date"], plan["group"]
        report_log = load_json(REPORT_LOG_FILE)
        if date_str not in report_log: report_log[date_str] = {"groups": {}}
        report_log[date_str]["groups"][group_name] = {
            "start_time": None, "end_time": None, "location": plan.get("location", "未設定"),
            "participants": 0, "description": "活動なし", "reporter": interaction.user.display_name,
        }
        save_json(REPORT_LOG_FILE, report_log)
        await interaction.response.send_message(f"✅ {date_str} の {group_name} を「活動なし」として報告しました。", ephemeral=True)
        await interaction.message.delete()

class HistoryViewerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    history_group = app_commands.Group(name="history", description="各種履歴の表示・操作")

    @history_group.command(name="report", description="過去の活動報告の履歴を表示・削除します。")
    @app_commands.describe(group="グループ名で絞り込み", location="活動場所で絞り込み", limit="表示件数の上限")
    async def show_report_history(self, interaction: discord.Interaction, group: str = None, location: str = None, limit: int = None):
        await interaction.response.defer(ephemeral=True)
        report_log = load_json(REPORT_LOG_FILE)
        if not report_log:
            await interaction.followup.send("活動報告の履歴はありません。", ephemeral=True)
            return
        all_reports = []
        for date_str, daily_data in report_log.items():
            for group_name, report_data in daily_data.get("groups", {}).items():
                report_data["date"], report_data["group"] = date_str, group_name
                all_reports.append(report_data)
        filtered_reports = all_reports
        if group: filtered_reports = [r for r in filtered_reports if group.lower() in r.get('group', '').lower()]
        if location: filtered_reports = [r for r in filtered_reports if location.lower() in r.get('location', '').lower()]
        sorted_reports = sorted(filtered_reports, key=lambda r: r["date"], reverse=True)
        if limit and limit > 0: sorted_reports = sorted_reports[:limit]
        if not sorted_reports:
            await interaction.followup.send("指定された条件に一致する活動報告の履歴はありません。", ephemeral=True)
            return
        embeds = []
        for r in sorted_reports:
            try:
                date_obj = datetime.datetime.fromisoformat(r['date']).date()
                title = f"活動報告: {date_obj.isoformat()} ({WEEKDAYS[date_obj.weekday()]}) {r['group']}"
            except (ValueError, KeyError):
                title = f"活動報告: {r.get('date', '不明')} {r.get('group', '不明')}"
            embed = discord.Embed(title=title, color=discord.Color.blue())
            embed.add_field(name="時間", value=f"{r.get('start_time', '?')} - {r.get('end_time', '?')}", inline=False)
            embed.add_field(name="場所", value=r.get('location', '未設定'), inline=True)
            embed.add_field(name="人数", value=f"{r.get('participants', 0)}人", inline=True)
            if r.get("description"): embed.add_field(name="内容", value=r["description"], inline=False)
            embed.set_footer(text=f"報告者: {r.get('reporter', '不明')}")
            embeds.append(embed)
        view = ReportHistoryActionView(embeds, interaction, sorted_reports)
        await interaction.followup.send(embed=embeds[0], view=view, ephemeral=True)

    @history_group.command(name="unreported", description="報告されていない活動計画を表示します。")
    async def show_unreported_plans(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        plan_log, report_log = load_json(PLAN_LOG_FILE_NAME), load_json(REPORT_LOG_FILE)
        unreported = []
        today_str = datetime.date.today().isoformat()
        for date_str, daily_plan in plan_log.items():
            if date_str >= today_str: continue
            for group_name, plan_data in daily_plan.get("groups", {}).items():
                if not (date_str in report_log and group_name in report_log[date_str].get("groups", {})):
                    plan_data["date"], plan_data["group"] = date_str, group_name
                    unreported.append(plan_data)
        if not unreported:
            await interaction.followup.send("報告漏れの活動計画はありません。", ephemeral=True)
            return
        sorted_unreported = sorted(unreported, key=lambda p: p["date"])
        embeds = []
        for p in sorted_unreported:
            try:
                date_obj = datetime.datetime.fromisoformat(p['date']).date()
                title = f"未報告の計画: {date_obj.isoformat()} ({WEEKDAYS[date_obj.weekday()]}) {p['group']}"
            except (ValueError, KeyError):
                title = f"未報告の計画: {p.get('date', '不明')} {p.get('group', '不明')}"

            embed = discord.Embed(title=title, color=discord.Color.yellow())
            embed.add_field(name="予定時間", value=f"{p.get('start_time', '?')} - {p.get('end_time', '?')}", inline=False)
            embed.add_field(name="予定場所", value=p.get('location', '未設定'), inline=True)
            if p.get("plan_details"): embed.add_field(name="予定内容", value=p["plan_details"], inline=False)
            embeds.append(embed)
        view = UnreportedActionView(embeds, interaction, sorted_unreported)
        await interaction.followup.send(embed=embeds[0], view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HistoryViewerCog(bot))
