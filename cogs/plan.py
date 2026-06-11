import discord
from discord import app_commands
from discord.ext import commands
import datetime
import openpyxl
import uuid
import re
from typing import Optional, List, Dict

from .utils import (
    load_json, save_json, create_new_month_excel_if_needed, parse_date, parse_time,
    PLAN_LOG_FILE_NAME, get_group_options, get_location_options, WEEKDAYS, ZEN_TO_HAN,
    generate_monthly_schedule, group_autocomplete, JST
)
from .ui_components import PagedItemView, ConfirmView, ActivityBaseModal

class PlanModal(ActivityBaseModal, title="活動計画の入力"):
    group = discord.ui.TextInput(label="グループ")
    location = discord.ui.TextInput(label="活動場所")
    activity_date = discord.ui.TextInput(label="活動日 (YYYY-MM-DD or YYYYMMDD)", placeholder="例: 2025-09-20")
    activity_time = discord.ui.TextInput(label="活動予定時間 (開始 - 終了)", placeholder="例: 15:00-17:00 or 1500-1700")
    plan_details = discord.ui.TextInput(label="活動予定 (任意)", placeholder="具体的な活動内容があれば入力", required=False)
    
    def __init__(self, cog, group: str, location: str, plan_id: str = None, defaults: dict = None):
        super().__init__()
        self.cog = cog
        self.plan_id = plan_id or str(uuid.uuid4())
        
        self.setup_common_defaults(self.group, self.location, group, location)

        if defaults:
            self.activity_date.default = defaults.get("date")
            start = defaults.get("start_time")
            end = defaults.get("end_time")
            if start and end:
                self.activity_time.default = f"{start} - {end}"
            self.plan_details.default = defaults.get("plan_details")

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_plan_submission(interaction, self)

class PlanDetailView(discord.ui.View):
    def __init__(self, plan: dict, cog):
        super().__init__(timeout=60)
        self.plan = plan
        self.cog = cog

    @discord.ui.button(label="編集", style=discord.ButtonStyle.secondary)
    async def edit_plan(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PlanModal(
            cog=self.cog,
            group=self.plan["group"],
            location=self.plan["location"],
            plan_id=self.plan["id"],
            defaults=self.plan
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="削除", style=discord.ButtonStyle.danger)
    async def delete_plan(self, interaction: discord.Interaction, button: discord.ui.Button):
        confirm_view = ConfirmView()
        await interaction.response.send_message(f"**確認:** {self.plan['date']} の **{self.plan['group']}** の計画を本当に削除しますか？", view=confirm_view, ephemeral=True)
        await confirm_view.wait()
        if confirm_view.value:
            date_str, plan_id = self.plan["date"], self.plan["id"]
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
                    return

            await interaction.followup.send("エラー: 対象の計画が見つかりませんでした。", ephemeral=True)
        else:
            await interaction.followup.send("操作をキャンセルしました。", ephemeral=True)

class PlanCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    plan = app_commands.Group(name="plan", description="活動計画に関するコマンド")

    @plan.command(name="add", description="活動計画を入力します。日付・時間・内容をモーダルで登録します。")
    @app_commands.choices(
        group=[app_commands.Choice(name=opt, value=opt) for opt in get_group_options()],
        location=[app_commands.Choice(name=opt, value=opt) for opt in get_location_options()]
    )
    async def add_plan(self, interaction: discord.Interaction, group: app_commands.Choice[str], location: app_commands.Choice[str]):
        await interaction.response.send_modal(PlanModal(cog=self, group=group.value, location=location.value))

    @plan.command(name="list", description="今後の活動計画を一覧表示し、選択した項目を編集/削除できます。")
    @app_commands.describe(group="表示するグループを絞り込みます。")
    @app_commands.autocomplete(group=group_autocomplete)
    async def list_plans(self, interaction: discord.Interaction, group: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        plan_log = load_json(PLAN_LOG_FILE_NAME)
        if not plan_log:
            await interaction.followup.send("登録されている活動計画はありません。", ephemeral=True)
            return

        future_plans = []
        today_str = datetime.datetime.now(JST).date().isoformat()
        for date_str, daily_data in plan_log.items():
            if date_str >= today_str:
                for group_name, plan_data in daily_data.get("groups", {}).items():
                    if group and group.lower() not in group_name.lower():
                        continue
                    if "id" not in plan_data:
                        plan_data["id"] = str(uuid.uuid4())
                    plan_data["date"] = date_str
                    plan_data["group"] = group_name
                    future_plans.append(plan_data)
        
        save_json(PLAN_LOG_FILE_NAME, plan_log)

        sorted_plans = sorted(future_plans, key=lambda p: (p["date"], p.get("start_time", "")))
        if not sorted_plans:
            await interaction.followup.send("指定された条件に一致する今後の活動計画はありません。", ephemeral=True)
            return

        def embed_factory(items: List[Dict], current_page: int, total_pages: int) -> discord.Embed:
            embed = discord.Embed(title="今後の活動計画", color=discord.Color.blue())
            for p in items:
                try:
                    date_obj = datetime.datetime.fromisoformat(p['date']).date()
                    title = f"{date_obj.year}年{date_obj.month}月{date_obj.day}日({WEEKDAYS[date_obj.weekday()]})  {p['group']}"
                except (ValueError, KeyError):
                    title = f"{p.get('date', '不明')} {p.get('group', '不明')}"
                
                value = f"**時間:** {p.get('start_time', '?')} - {p.get('end_time', '?')}\n**場所:** {p.get('location', '未設定')}"
                if p.get("plan_details"):
                    value += f"\n**内容:** {p['plan_details']}"
                embed.add_field(name=title, value=value, inline=False)
            
            embed.set_footer(text=f"ページ {current_page}/{total_pages}")
            return embed

        def select_options_factory(items: List[Dict]) -> List[discord.SelectOption]:
            options = []
            for p in items:
                try:
                    date_obj = datetime.datetime.fromisoformat(p['date']).date()
                    label = f"{date_obj.month}/{date_obj.day} {p['group']}"
                except:
                    label = f"{p.get('date')} {p.get('group')}"
                
                # ラベルが長すぎる場合は切り詰める
                if len(label) > 100:
                    label = label[:97] + "..."
                
                description = f"{p.get('start_time')} - {p.get('end_time')} @ {p.get('location')}"
                if len(description) > 100:
                    description = description[:97] + "..."

                options.append(discord.SelectOption(label=label, value=p["id"], description=description))
            return options

        async def on_select_callback(interaction: discord.Interaction, selected_value: str):
            selected_plan = next((p for p in sorted_plans if p["id"] == selected_value), None)
            if selected_plan:
                try:
                    date_obj = datetime.datetime.fromisoformat(selected_plan['date']).date()
                    title = f"{date_obj.year}年{date_obj.month}月{date_obj.day}日({WEEKDAYS[date_obj.weekday()]})  {selected_plan['group']}"
                except:
                    title = f"{selected_plan.get('date')} {selected_plan.get('group')}"

                embed = discord.Embed(title=title, color=discord.Color.green())
                embed.add_field(name="予定時間", value=f"{selected_plan.get('start_time', '?')} - {selected_plan.get('end_time', '?')}", inline=False)
                embed.add_field(name="予定場所", value=selected_plan.get('location', '未設定'), inline=True)
                if selected_plan.get("plan_details"):
                    embed.add_field(name="予定内容", value=selected_plan["plan_details"], inline=False)
                
                view = PlanDetailView(selected_plan, self)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.response.send_message("エラー: 選択された計画が見つかりませんでした。", ephemeral=True)

        view = PagedItemView(sorted_plans, interaction, embed_factory, select_options_factory, on_select_callback)
        await interaction.followup.send(embed=embed_factory(sorted_plans[:3], 1, view.total_pages), view=view, ephemeral=True)


    async def handle_plan_submission(self, interaction: discord.Interaction, modal: PlanModal):
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            
            plan_date_str = parse_date(modal.activity_date.value)
            if not plan_date_str:
                await interaction.followup.send("エラー: 日付の形式が正しくありません。(例: 2025-09-20 or 20250920)", ephemeral=True)
                return
            plan_date = datetime.date.fromisoformat(plan_date_str)

            excel_filename, error_msg = await create_new_month_excel_if_needed(plan_date.year, plan_date.month)
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
            
            is_regular_flag = False
            for date_key in list(plan_log.keys()):
                for group_key in list(plan_log[date_key].get("groups", {}).keys()):
                    if plan_log[date_key]["groups"][group_key].get("id") == modal.plan_id:
                        is_regular_flag = plan_log[date_key]["groups"][group_key].get("is_regular", False)
                        del plan_log[date_key]["groups"][group_key]
                        if not plan_log[date_key]["groups"]:
                            del plan_log[date_key]
                        break
                else:
                    continue
                break

            if plan_date_str not in plan_log:
                plan_log[plan_date_str] = {"groups": {}}
            
            plan_log[plan_date_str].setdefault("groups", {})[group_name] = {
                "id": modal.plan_id,
                "start_time": formatted_start, "end_time": formatted_end,
                "location": location_name, "plan_details": modal.plan_details.value,
                "is_regular": is_regular_flag
            }
            save_json(PLAN_LOG_FILE_NAME, plan_log)

            _, error_msg = generate_monthly_schedule(plan_date.year, plan_date.month, overwrite=False)
            if error_msg:
                await interaction.followup.send(f"警告: Excelファイルの更新中にエラーが発生しました: {error_msg}", ephemeral=True)

            await interaction.followup.send(f"{plan_date_str} の活動計画を記録・更新しました。", ephemeral=True)

        except Exception as e:
            import traceback
            print(f"An error occurred in handle_plan_submission: {e}\n{traceback.format_exc()}")
            await interaction.followup.send(f"申し訳ありません、エラーが発生しました: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(PlanCog(bot))
