import discord
from discord import app_commands
from discord.ext import commands
import datetime
import openpyxl
import uuid
import re

from .utils import (
    load_json, save_json, create_new_month_excel_if_needed, parse_date, parse_time,
    PLAN_LOG_FILE_NAME, get_group_options, get_location_options, WEEKDAYS, ZEN_TO_HAN
)
from .ui_components import PaginationView, ConfirmView

class PlanModal(discord.ui.Modal, title="活動計画の入力"):
    group = discord.ui.TextInput(label="グループ")
    location = discord.ui.TextInput(label="活動場所")
    activity_date = discord.ui.TextInput(label="活動日 (YYYY-MM-DD or YYYYMMDD)", placeholder="例: 2025-09-20")
    activity_time = discord.ui.TextInput(label="活動予定時間 (開始 - 終了)", placeholder="例: 15:00-17:00 or 1500-1700")
    plan_details = discord.ui.TextInput(label="活動予定 (任意)", placeholder="具体的な活動内容があれば入力", required=False)
    
    def __init__(self, cog, group: str, location: str, plan_id: str = None, defaults: dict = None):
        super().__init__()
        self.cog = cog
        self.plan_id = plan_id or str(uuid.uuid4())
        
        self.group.default = group
        self.location.default = location
        if group == "その他":
            self.group.placeholder = "活動するグループ名を入力してください"
        if location == "その他":
            self.location.placeholder = "活動する場所を入力してください"

        if defaults:
            self.activity_date.default = defaults.get("date")
            start = defaults.get("start_time")
            end = defaults.get("end_time")
            if start and end:
                self.activity_time.default = f"{start} - {end}"
            self.plan_details.default = defaults.get("plan_details")

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_plan_submission(interaction, self)

class PlanActionView(PaginationView):
    def __init__(self, embeds: list[discord.Embed], interaction: discord.Interaction, plans: list[dict], cog):
        super().__init__(embeds, interaction)
        self.plans = plans
        self.cog = cog

    @discord.ui.button(label="編集", style=discord.ButtonStyle.secondary, row=1)
    async def edit_plan(self, interaction: discord.Interaction, button: discord.ui.Button):
        plan_to_edit = self.plans[self.current_page]
        modal = PlanModal(
            cog=self.cog,
            group=plan_to_edit["group"],
            location=plan_to_edit["location"],
            plan_id=plan_to_edit["id"],
            defaults=plan_to_edit
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="削除", style=discord.ButtonStyle.danger, row=1)
    async def delete_plan(self, interaction: discord.Interaction, button: discord.ui.Button):
        plan_to_delete = self.plans[self.current_page]
        confirm_view = ConfirmView()
        await interaction.response.send_message(f"**確認:** {plan_to_delete['date']} の **{plan_to_delete['group']}** の計画を本当に削除しますか？", view=confirm_view, ephemeral=True)
        await confirm_view.wait()
        if confirm_view.value:
            date_str, plan_id = plan_to_delete["date"], plan_to_delete["id"]
            plan_log = load_json(PLAN_LOG_FILE_NAME)
            if date_str in plan_log:
                group_to_delete = None
                for group, plan_data in plan_log[date_str]["groups"].items():
                    if plan_data.get("id") == plan_id:
                        group_to_delete = group
                        break
                
                if group_to_delete:
                    del plan_log[date_str]["groups"][group_to_delete]
                    if not plan_log[date_str]["groups"]:
                        del plan_log[date_str]
                    save_json(PLAN_LOG_FILE_NAME, plan_log)
                    await interaction.followup.send(f"✅ {date_str} の {group_to_delete} の計画を削除しました。", ephemeral=True)
                    await self.interaction.message.delete()
                    return

            await interaction.followup.send("エラー: 対象の計画が見つかりませんでした。", ephemeral=True)
        else:
            await interaction.followup.send("操作をキャンセルしました。", ephemeral=True)


class PlanCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    plan = app_commands.Group(name="plan", description="活動計画に関するコマンド")

    @plan.command(name="add", description="活動計画を入力します。")
    @app_commands.choices(
        group=[app_commands.Choice(name=opt, value=opt) for opt in get_group_options()],
        location=[app_commands.Choice(name=opt, value=opt) for opt in get_location_options()]
    )
    async def add_plan(self, interaction: discord.Interaction, group: app_commands.Choice[str], location: app_commands.Choice[str]):
        await interaction.response.send_modal(PlanModal(cog=self, group=group.value, location=location.value))

    @plan.command(name="list", description="今後の活動計画を一覧表示・編集・削除します。")
    async def list_plans(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        plan_log = load_json(PLAN_LOG_FILE_NAME)
        if not plan_log:
            await interaction.followup.send("登録されている活動計画はありません。", ephemeral=True)
            return

        future_plans = []
        today_str = datetime.date.today().isoformat()
        for date_str, daily_data in plan_log.items():
            if date_str >= today_str:
                for group_name, plan_data in daily_data.get("groups", {}).items():
                    if "id" not in plan_data:
                        plan_data["id"] = str(uuid.uuid4())
                    plan_data["date"] = date_str
                    plan_data["group"] = group_name
                    future_plans.append(plan_data)
        
        save_json(PLAN_LOG_FILE_NAME, plan_log)

        sorted_plans = sorted(future_plans, key=lambda p: (p["date"], p.get("start_time", "")))
        if not sorted_plans:
            await interaction.followup.send("今後の活動計画はありません。", ephemeral=True)
            return

        embeds = []
        for p in sorted_plans:
            try:
                date_obj = datetime.datetime.fromisoformat(p['date']).date()
                title = f"{date_obj.year}年{date_obj.month}月{date_obj.day}日({WEEKDAYS[date_obj.weekday()]})  {p['group']}"
            except (ValueError, KeyError):
                title = f"活動計画: {p.get('date', '不明')} ({p.get('group', '不明')})"
            
            embed = discord.Embed(title=title, color=discord.Color.blue())
            embed.add_field(name="予定時間", value=f"{p.get('start_time', '?')} - {p.get('end_time', '?')}", inline=False)
            embed.add_field(name="予定場所", value=p.get('location', '未設定'), inline=True)
            if p.get("plan_details"):
                embed.add_field(name="予定内容", value=p["plan_details"], inline=False)
            embeds.append(embed)

        view = PlanActionView(embeds, interaction, sorted_plans, self)
        await interaction.followup.send(embed=embeds[0], view=view, ephemeral=True)


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

            raw_time = modal.activity_time.value.translate(ZEN_TO_HAN)
            times = re.findall(r'(\d{1,2}:\d{2}|\d{3,4})', raw_time)
            start_str, end_str = (times[0], times[1]) if len(times) >= 2 else (None, None)
            formatted_start, formatted_end = parse_time(start_str), parse_time(end_str)
            if not formatted_start or not formatted_end:
                await interaction.followup.send("エラー: 活動時間の形式が正しくありません。(例: 15:00-17:00 or 1500-1700)", ephemeral=True)
                return

            group_name = modal.group.value
            location_name = modal.location.value

            plan_log = load_json(PLAN_LOG_FILE_NAME)
            
            for date_key in list(plan_log.keys()):
                for group_key in list(plan_log[date_key].get("groups", {}).keys()):
                    if plan_log[date_key]["groups"][group_key].get("id") == modal.plan_id:
                        del plan_log[date_key]["groups"][group_key]
                        if not plan_log[date_key]["groups"]:
                            del plan_log[date_key]
                        break

            if plan_date_str not in plan_log:
                plan_log[plan_date_str] = {"groups": {}}
            
            plan_log[plan_date_str].setdefault("groups", {})[group_name] = {
                "id": modal.plan_id,
                "start_time": formatted_start, "end_time": formatted_end,
                "location": location_name, "plan_details": modal.plan_details.value,
            }
            save_json(PLAN_LOG_FILE_NAME, plan_log)

            todays_plans = plan_log[plan_date_str]["groups"]
            final_start = min(v["start_time"] for v in todays_plans.values() if v["start_time"])
            final_end = max(v["end_time"] for v in todays_plans.values() if v["end_time"])
            location_parts = [f'{v["location"]}({k})' if k and k != "その他" else v["location"] for k, v in todays_plans.items()]
            final_location = " | ".join(sorted(list(set(location_parts))))
            plan_detail_parts = []
            for gn, plan_info in todays_plans.items():
                detail = plan_info.get('plan_details')
                if detail:
                    plan_detail_parts.append(f"{detail}({gn})" if gn and gn != "その他" else detail)
            final_plan_details = "、".join(sorted(list(set(plan_detail_parts))))

            try:
                workbook = openpyxl.load_workbook(target_filename)
                sheet = workbook["活動計画書"]
                target_row = plan_date.day + 6
                sheet[f"C{target_row}"] = final_start
                sheet[f"E{target_row}"] = final_end
                sheet[f"F{target_row}"] = final_location
                sheet[f"G{target_row}"] = final_plan_details
                workbook.save(target_filename)
                await interaction.followup.send(f"{plan_date_str} の活動計画を記録・更新しました。", ephemeral=True)
            except (FileNotFoundError, KeyError) as e:
                await interaction.followup.send(f"Excelエラー: {e}", ephemeral=True)

        except Exception as e:
            print(f"An error occurred in handle_plan_submission: {e}")
            await interaction.followup.send(f"申し訳ありません、エラーが発生しました: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(PlanCog(bot))
