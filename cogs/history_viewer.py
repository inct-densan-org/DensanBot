import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import datetime
from typing import List, Dict

from .ui_components import PagedItemView, ConfirmView, ReportModal
from .utils import (
    load_json, save_json, REPORT_LOG_FILE, PLAN_LOG_FILE_NAME, WEEKDAYS
)

class ReportDetailView(discord.ui.View):
    def __init__(self, report: dict, bot: commands.Bot):
        super().__init__(timeout=60)
        self.report = report
        self.bot = bot

    @discord.ui.button(label="編集", style=discord.ButtonStyle.primary)
    async def edit_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        report_cog = self.bot.get_cog("ReportCog")
        if not report_cog:
            await interaction.response.send_message("エラー: ReportCogが見つかりません。", ephemeral=True)
            return
        modal = ReportModal(
            cog=report_cog,
            group=self.report["group"],
            location=self.report.get("location", "その他"),
            default_activity_time=f"{self.report.get('start_time') or ''} - {self.report.get('end_time') or ''}".strip(" -"),
            default_activity_date=self.report["date"]
        )
        modal.participants.default = str(self.report.get("participants", 0))
        modal.description.default = self.report.get("description", "")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="削除", style=discord.ButtonStyle.danger)
    async def delete_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        confirm_view = ConfirmView()
        await interaction.response.send_message(f"**確認:** {self.report['date']} の **{self.report['group']}** の報告を本当に削除しますか？", view=confirm_view, ephemeral=True)
        await confirm_view.wait()
        if confirm_view.value:
            date_str, group_name = self.report["date"], self.report["group"]
            report_log = load_json(REPORT_LOG_FILE)
            if date_str in report_log and group_name in report_log[date_str]["groups"]:
                del report_log[date_str]["groups"][group_name]
                if not report_log[date_str]["groups"]: del report_log[date_str]
                save_json(REPORT_LOG_FILE, report_log)
                await interaction.followup.send(f"✅ {date_str} の {group_name} の報告を削除しました。", ephemeral=True)
            else:
                await interaction.followup.send("エラー: 対象の報告が見つかりませんでした。", ephemeral=True)
        else:
            await interaction.followup.send("操作をキャンセルしました。", ephemeral=True)

class UnreportedDetailView(discord.ui.View):
    def __init__(self, plan: dict):
        super().__init__(timeout=60)
        self.plan = plan

    @discord.ui.button(label="「活動なし」として報告", style=discord.ButtonStyle.primary)
    async def report_as_no_activity(self, interaction: discord.Interaction, button: discord.ui.Button):
        date_str, group_name = self.plan["date"], self.plan["group"]
        report_log = load_json(REPORT_LOG_FILE)
        if date_str not in report_log: report_log[date_str] = {"groups": {}}
        report_log[date_str]["groups"][group_name] = {
            "start_time": None, "end_time": None, "location": self.plan.get("location", "未設定"),
            "participants": 0, "description": "活動なし", "reporter": interaction.user.display_name,
        }
        save_json(REPORT_LOG_FILE, report_log)
        await interaction.response.send_message(f"✅ {date_str} の {group_name} を「活動なし」として報告しました。", ephemeral=True)

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

        def embed_factory(items: List[Dict], current_page: int, total_pages: int) -> discord.Embed:
            embed = discord.Embed(title="活動報告履歴", color=discord.Color.blue())
            for r in items:
                try:
                    date_obj = datetime.datetime.fromisoformat(r['date']).date()
                    title = f"{date_obj.isoformat()} ({WEEKDAYS[date_obj.weekday()]}) {r['group']}"
                except (ValueError, KeyError):
                    title = f"{r.get('date', '不明')} {r.get('group', '不明')}"
                
                value = f"**時間:** {r.get('start_time', '?')} - {r.get('end_time', '?')}\n**場所:** {r.get('location', '未設定')}\n**人数:** {r.get('participants', 0)}人"
                if r.get("description"):
                    value += f"\n**内容:** {r['description']}"
                embed.add_field(name=title, value=value, inline=False)
            
            embed.set_footer(text=f"ページ {current_page}/{total_pages}")
            return embed

        def select_options_factory(items: List[Dict]) -> List[discord.SelectOption]:
            options = []
            for i, r in enumerate(items):
                try:
                    date_obj = datetime.datetime.fromisoformat(r['date']).date()
                    label = f"{date_obj.month}/{date_obj.day} {r['group']}"
                except:
                    label = f"{r.get('date')} {r.get('group')}"
                
                if len(label) > 100: label = label[:97] + "..."
                
                # ユニークなIDがないため、インデックスと日付・グループを組み合わせて識別子とする
                value = f"{i}_{r['date']}_{r['group']}"
                if len(value) > 100: value = value[:100]

                description = f"{r.get('start_time')} - {r.get('end_time')} @ {r.get('location')}"
                if len(description) > 100: description = description[:97] + "..."

                options.append(discord.SelectOption(label=label, value=value, description=description))
            return options

        async def on_select_callback(interaction: discord.Interaction, selected_value: str):
            # valueからインデックスと日付・グループを復元して対象を特定
            # 簡易的な実装として、現在のページ内のアイテムから探す
            # PagedItemViewは現在のページのアイテムしか渡してこないはずだが、念のため
            
            # selected_value format: "{index}_{date}_{group}"
            parts = selected_value.split('_', 1)
            if len(parts) < 2:
                 await interaction.response.send_message("エラー: 選択された項目の特定に失敗しました。", ephemeral=True)
                 return
            
            target_date_group = parts[1]
            
            selected_report = None
            for r in sorted_reports:
                 if f"{r['date']}_{r['group']}" == target_date_group:
                     selected_report = r
                     break
            
            if selected_report:
                try:
                    date_obj = datetime.datetime.fromisoformat(selected_report['date']).date()
                    title = f"活動報告: {date_obj.isoformat()} ({WEEKDAYS[date_obj.weekday()]}) {selected_report['group']}"
                except:
                    title = f"活動報告: {selected_report.get('date')} {selected_report.get('group')}"

                embed = discord.Embed(title=title, color=discord.Color.green())
                embed.add_field(name="時間", value=f"{selected_report.get('start_time', '?')} - {selected_report.get('end_time', '?')}", inline=False)
                embed.add_field(name="場所", value=selected_report.get('location', '未設定'), inline=True)
                embed.add_field(name="人数", value=f"{selected_report.get('participants', 0)}人", inline=True)
                if selected_report.get("description"):
                    embed.add_field(name="内容", value=selected_report["description"], inline=False)
                embed.set_footer(text=f"報告者: {selected_report.get('reporter', '不明')}")

                view = ReportDetailView(selected_report, self.bot)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.response.send_message("エラー: 選択された報告が見つかりませんでした。", ephemeral=True)

        view = PagedItemView(sorted_reports, interaction, embed_factory, select_options_factory, on_select_callback)
        await interaction.followup.send(embed=embed_factory(sorted_reports[:3], 1, view.total_pages), view=view, ephemeral=True)

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

        def embed_factory(items: List[Dict], current_page: int, total_pages: int) -> discord.Embed:
            embed = discord.Embed(title="未報告の活動計画", color=discord.Color.yellow())
            for p in items:
                try:
                    date_obj = datetime.datetime.fromisoformat(p['date']).date()
                    title = f"{date_obj.isoformat()} ({WEEKDAYS[date_obj.weekday()]}) {p['group']}"
                except (ValueError, KeyError):
                    title = f"{p.get('date', '不明')} {p.get('group', '不明')}"
                
                value = f"**予定時間:** {p.get('start_time', '?')} - {p.get('end_time', '?')}\n**予定場所:** {p.get('location', '未設定')}"
                if p.get("plan_details"):
                    value += f"\n**予定内容:** {p['plan_details']}"
                embed.add_field(name=title, value=value, inline=False)
            
            embed.set_footer(text=f"ページ {current_page}/{total_pages}")
            return embed

        def select_options_factory(items: List[Dict]) -> List[discord.SelectOption]:
            options = []
            for i, p in enumerate(items):
                try:
                    date_obj = datetime.datetime.fromisoformat(p['date']).date()
                    label = f"{date_obj.month}/{date_obj.day} {p['group']}"
                except:
                    label = f"{p.get('date')} {p.get('group')}"
                
                if len(label) > 100: label = label[:97] + "..."
                
                # ユニークなIDがないため、インデックスと日付・グループを組み合わせて識別子とする
                value = f"{i}_{p['date']}_{p['group']}"
                if len(value) > 100: value = value[:100]

                description = f"{p.get('start_time')} - {p.get('end_time')} @ {p.get('location')}"
                if len(description) > 100: description = description[:97] + "..."

                options.append(discord.SelectOption(label=label, value=value, description=description))
            return options

        async def on_select_callback(interaction: discord.Interaction, selected_value: str):
            parts = selected_value.split('_', 1)
            if len(parts) < 2:
                 await interaction.response.send_message("エラー: 選択された項目の特定に失敗しました。", ephemeral=True)
                 return
            
            target_date_group = parts[1]
            
            selected_plan = None
            for p in sorted_unreported:
                 if f"{p['date']}_{p['group']}" == target_date_group:
                     selected_plan = p
                     break
            
            if selected_plan:
                try:
                    date_obj = datetime.datetime.fromisoformat(selected_plan['date']).date()
                    title = f"未報告の計画: {date_obj.isoformat()} ({WEEKDAYS[date_obj.weekday()]}) {selected_plan['group']}"
                except:
                    title = f"未報告の計画: {selected_plan.get('date')} {selected_plan.get('group')}"

                embed = discord.Embed(title=title, color=discord.Color.yellow())
                embed.add_field(name="予定時間", value=f"{selected_plan.get('start_time', '?')} - {selected_plan.get('end_time', '?')}", inline=False)
                embed.add_field(name="予定場所", value=selected_plan.get('location', '未設定'), inline=True)
                if selected_plan.get("plan_details"):
                    embed.add_field(name="予定内容", value=selected_plan["plan_details"], inline=False)
                
                view = UnreportedDetailView(selected_plan)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.response.send_message("エラー: 選択された計画が見つかりませんでした。", ephemeral=True)

        view = PagedItemView(sorted_unreported, interaction, embed_factory, select_options_factory, on_select_callback)
        await interaction.followup.send(embed=embed_factory(sorted_unreported[:3], 1, view.total_pages), view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HistoryViewerCog(bot))
