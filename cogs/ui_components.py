import discord
from typing import Dict, Any, List, Callable
import datetime

from .utils import get_group_options, get_location_options, PLAN_LOG_FILE_NAME, load_json

<<<<<<< HEAD
def get_plan_defaults(group_name: str, date_str: str | None = None) -> Dict[str, Any]:
    """活動計画ログを読み込み、指定日・グループのデフォルト値を取得する。"""
    target_date = date_str or datetime.date.today().isoformat()
    defaults = {"activity_time": None, "location": None, "activity_date": target_date}
    plan_log = load_json(PLAN_LOG_FILE_NAME)
    if target_plan := plan_log.get(target_date, {}).get("groups", {}).get(group_name):
        start, end = target_plan.get("start_time"), target_plan.get("end_time")
        if start and end:
            defaults["activity_time"] = f"{start} - {end}"
        defaults["location"] = target_plan.get("location")
=======
def get_todays_plan_defaults(group_name: str) -> Dict[str, Any]:
    """今日の活動計画ログを読み込み、指定されたグループのデフォルト値を取得する"""
    today_str = datetime.date.today().isoformat()
    defaults = {"activity_time": None, "location": None, "activity_date": today_str}
    plan_log = load_json(PLAN_LOG_FILE_NAME)
    if todays_plan := plan_log.get(today_str, {}).get("groups", {}).get(group_name):
        start, end = todays_plan.get("start_time"), todays_plan.get("end_time")
        if start and end: defaults["activity_time"] = f"{start} - {end}"
        defaults["location"] = todays_plan.get("location")
>>>>>>> main
    return defaults

def get_todays_plan_defaults(group_name: str) -> Dict[str, Any]:
    """今日の活動計画ログを読み込み、指定されたグループのデフォルト値を取得する。"""
    return get_plan_defaults(group_name)

class ConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None

    @discord.ui.button(label="はい", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True; self.stop(); await interaction.response.defer()

    @discord.ui.button(label="いいえ", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False; self.stop(); await interaction.response.defer()

class ActivityBaseModal(discord.ui.Modal):
    """計画・報告モーダルの共通初期化ロジック。"""
    def setup_common_defaults(self, group_field, location_field, group: str, location: str):
        group_field.default = group
        location_field.default = location
        if group == "その他":
            group_field.placeholder = "グループ名を入力してください"
        if location == "その他":
            location_field.placeholder = "活動場所を入力してください"

class PaginationView(discord.ui.View):
    """Embedのリストをページめくりで表示するための汎用View。"""
    def __init__(self, embeds: list[discord.Embed], interaction: discord.Interaction, ephemeral: bool = False):
        super().__init__(timeout=300)
        self.embeds = embeds
        self.interaction = interaction
        self.current_page = 0
        self.total_pages = len(embeds)
        self.ephemeral = ephemeral
        
        if self.ephemeral:
            self.remove_item(self.close_view)
            
        self._update_buttons()

    async def show_current_page(self):
        embed = self.embeds[self.current_page]
        embed.set_footer(text=f"ページ {self.current_page + 1}/{self.total_pages}")
        await self.interaction.edit_original_response(embed=embed, view=self)

    def _update_buttons(self):
        self.prev_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page >= self.total_pages - 1

    @discord.ui.button(label="<< 前へ", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self._update_buttons()
            await interaction.response.defer()
            await self.show_current_page()

    @discord.ui.button(label="次へ >>", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._update_buttons()
            await interaction.response.defer()
            await self.show_current_page()

    @discord.ui.button(label="閉じる", style=discord.ButtonStyle.danger, row=1)
    async def close_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

class PagedItemView(discord.ui.View):
    """
    アイテムリストをページング表示し、ドロップダウンで選択してアクションを行うための汎用View。
    """
    def __init__(self, items: List[Dict], interaction: discord.Interaction, 
                 embed_factory: Callable[[List[Dict], int, int], discord.Embed], 
                 select_options_factory: Callable[[List[Dict]], List[discord.SelectOption]],
                 on_select_callback: Callable[[discord.Interaction, str], Any],
                 items_per_page: int = 3,
                 ephemeral: bool = False):
        super().__init__(timeout=300)
        self.items = items
        self.interaction = interaction
        self.embed_factory = embed_factory
        self.select_options_factory = select_options_factory
        self.on_select_callback = on_select_callback
        self.items_per_page = items_per_page
        self.current_page = 0
        self.total_pages = (len(items) + items_per_page - 1) // items_per_page
        self.ephemeral = ephemeral
        
        self.update_components()

    def update_components(self):
        self.clear_items()
        
        # ページネーションボタン
        if self.total_pages > 1:
            prev_btn = discord.ui.Button(label="<< 前へ", style=discord.ButtonStyle.secondary, disabled=(self.current_page == 0))
            prev_btn.callback = self.prev_page
            self.add_item(prev_btn)

            next_btn = discord.ui.Button(label="次へ >>", style=discord.ButtonStyle.secondary, disabled=(self.current_page >= self.total_pages - 1))
            next_btn.callback = self.next_page
            self.add_item(next_btn)

        # 閉じるボタン (ephemeralでない場合のみ表示)
        if not self.ephemeral:
            close_btn = discord.ui.Button(label="閉じる", style=discord.ButtonStyle.danger, row=1)
            close_btn.callback = self.close_view
            self.add_item(close_btn)

        # ドロップダウンメニュー
        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        current_items = self.items[start_idx:end_idx]
        
        if current_items:
            options = self.select_options_factory(current_items)
            if options:
                select = discord.ui.Select(placeholder="操作する項目を選択してください", options=options, row=2)
                select.callback = self.on_select
                self.add_item(select)

    async def update_view(self):
        self.update_components()
        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        current_items = self.items[start_idx:end_idx]
        
        embed = self.embed_factory(current_items, self.current_page + 1, self.total_pages)
        await self.interaction.edit_original_response(embed=embed, view=self)

    async def prev_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.defer()
            await self.update_view()

    async def next_page(self, interaction: discord.Interaction):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await interaction.response.defer()
            await self.update_view()

    async def close_view(self, interaction: discord.Interaction):
        await interaction.message.delete()

    async def on_select(self, interaction: discord.Interaction):
        selected_value = interaction.data['values'][0]
        await self.on_select_callback(interaction, selected_value)


class ReportModal(ActivityBaseModal, title="活動報告"):
    activity_date = discord.ui.TextInput(label="活動日 (YYYY-MM-DD or YYYYMMDD)", placeholder="例: 2026-05-28")
    activity_time = discord.ui.TextInput(label="活動時間 (開始 - 終了)", placeholder="例: 15:00-17:00 or 1500-1700")
    participants = discord.ui.TextInput(label="活動人数", placeholder="半角数字で入力してください")
    description = discord.ui.TextInput(label="活動内容・備考", style=discord.TextStyle.paragraph, required=False)

<<<<<<< HEAD
    def __init__(self, cog, group: str, location: str, default_activity_time: str | None = None, default_activity_date: str | None = None, source_message: discord.Message | None = None):
=======
    def __init__(self, cog, group: str, location: str, default_activity_time: str | None = None, default_activity_date: str | None = None):
>>>>>>> main
        super().__init__()
        self.cog = cog
        self.group = group
        self.location = location
<<<<<<< HEAD
        self.source_message = source_message
=======
>>>>>>> main
        self.activity_date.default = default_activity_date or datetime.datetime.now().date().isoformat()
        if default_activity_time:
            self.activity_time.default = default_activity_time

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_report_submission(interaction, self)

class ReportTargetModal(ActivityBaseModal, title="活動報告（場所も入力）"):
    location = discord.ui.TextInput(label="活動場所", placeholder="例: PC教室")
    activity_date = discord.ui.TextInput(label="活動日 (YYYY-MM-DD or YYYYMMDD)", placeholder="例: 2026-05-28")
    activity_time = discord.ui.TextInput(label="活動時間 (開始 - 終了)", placeholder="例: 15:00-17:00 or 1500-1700")
    participants = discord.ui.TextInput(label="活動人数", placeholder="半角数字で入力してください")
    description = discord.ui.TextInput(label="活動内容・備考", style=discord.TextStyle.paragraph, required=False)

<<<<<<< HEAD
    def __init__(self, cog, group: str, location: str, default_activity_time: str | None = None, default_activity_date: str | None = None, source_message: discord.Message | None = None):
        super().__init__()
        self.cog = cog
        self.group = group
        self.source_message = source_message
=======
    def __init__(self, cog, group: str, location: str, default_activity_time: str | None = None, default_activity_date: str | None = None):
        super().__init__()
        self.cog = cog
        self.group = group
>>>>>>> main
        self.location.default = "" if location == "その他" else location
        if location == "その他":
            self.location.placeholder = "活動場所を入力してください"
        self.activity_date.default = default_activity_date or datetime.datetime.now().date().isoformat()
        if default_activity_time:
            self.activity_time.default = default_activity_time

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_report_submission(interaction, self)

class ReportCreationView(discord.ui.View):
    def __init__(self, cog, date_str: str | None = None, source_message: discord.Message | None = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.date_str = date_str
        self.source_message = source_message
        self.selected_group = None
        self.add_item(GroupSelect(self))

    async def update_view(self, interaction: discord.Interaction):
        for item in self.children:
            if isinstance(item, GroupSelect):
                item.disabled = True
        self.add_item(LocationSelect(self))
        embed = discord.Embed(
            title="活動報告 (2/2)",
            description="次に、活動場所を選択してください。",
            color=discord.Color.blue()
        ).add_field(name="選択済みグループ", value=self.selected_group)
        await interaction.edit_original_response(embed=embed, view=self)

class GroupSelect(discord.ui.Select):
    def __init__(self, parent_view: ReportCreationView):
        self.parent_view = parent_view
        options = [discord.SelectOption(label=opt, value=opt) for opt in get_group_options()]
        super().__init__(placeholder="あなたの所属グループを選択してください", options=options)

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.selected_group = self.values[0]
<<<<<<< HEAD
        defaults = get_plan_defaults(self.parent_view.selected_group, self.parent_view.date_str)
=======
        defaults = get_todays_plan_defaults(self.parent_view.selected_group)
>>>>>>> main
        if self.parent_view.selected_group != "その他" and defaults.get("location"):
            await interaction.response.send_modal(
                ReportModal(
                    cog=self.parent_view.cog,
                    group=self.parent_view.selected_group,
                    location=defaults["location"],
                    default_activity_time=defaults.get("activity_time"),
                    default_activity_date=defaults.get("activity_date"),
<<<<<<< HEAD
                    source_message=self.parent_view.source_message,
=======
>>>>>>> main
                )
            )
            return
        await interaction.response.defer()
        await self.parent_view.update_view(interaction)

class LocationSelect(discord.ui.Select):
    def __init__(self, parent_view: ReportCreationView):
        self.parent_view = parent_view
        options = [discord.SelectOption(label=opt, value=opt) for opt in get_location_options()]
        super().__init__(placeholder="活動場所を選択してください", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_location = self.values[0]
<<<<<<< HEAD
        defaults = get_plan_defaults(self.parent_view.selected_group, self.parent_view.date_str)
=======
        defaults = get_todays_plan_defaults(self.parent_view.selected_group)
>>>>>>> main
        modal_class = ReportTargetModal if selected_location == "その他" else ReportModal
        modal = modal_class(
            cog=self.parent_view.cog,
            group=self.parent_view.selected_group,
            location=selected_location,
            default_activity_time=defaults.get("activity_time"),
            default_activity_date=defaults.get("activity_date"),
<<<<<<< HEAD
            source_message=self.parent_view.source_message,
=======
>>>>>>> main
        )
        await interaction.response.send_modal(modal)

class ReminderView(discord.ui.View):
    def __init__(self, cog, group: str | None = None, date_str: str | None = None, plan: Dict[str, Any] | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.group = group
        self.date_str = date_str or datetime.date.today().isoformat()
        self.plan = plan or {}

    @discord.ui.button(label="活動報告を行う", style=discord.ButtonStyle.primary, custom_id="report_button")
    async def open_report_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.group:
            defaults = get_plan_defaults(self.group, self.date_str)
            location = defaults.get("location") or self.plan.get("location") or "その他"
            activity_time = defaults.get("activity_time")
            if not activity_time and self.plan.get("start_time") and self.plan.get("end_time"):
                activity_time = f"{self.plan['start_time']} - {self.plan['end_time']}"
            modal_class = ReportTargetModal if location == "その他" else ReportModal
            await interaction.response.send_modal(
                modal_class(
                    cog=self.cog,
                    group=self.group,
                    location=location,
                    default_activity_time=activity_time,
                    default_activity_date=self.date_str,
                    source_message=interaction.message,
                )
            )
            return

        embed = discord.Embed(
            title="活動報告 (1/2)",
            description="まず、報告するグループを選択してください。",
            color=discord.Color.blue()
        )
<<<<<<< HEAD
        await interaction.response.send_message(
            embed=embed,
            view=ReportCreationView(cog=self.cog, date_str=self.date_str, source_message=interaction.message),
            ephemeral=True,
        )

    @discord.ui.button(label="活動なしを報告", style=discord.ButtonStyle.secondary, custom_id="report_no_activity_button")
    async def report_no_activity(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.group:
            await self.cog.report_no_activity(
                interaction,
                self.group,
                report_date_str=self.date_str,
                source_message=interaction.message,
            )
            return

        plan_log = load_json(PLAN_LOG_FILE_NAME)
        groups = sorted(plan_log.get(self.date_str, {}).get("groups", {}).keys())
        if not groups:
            await interaction.response.send_message("対象日の活動計画がないため、活動なし報告の対象がありません。", ephemeral=True)
            return
        options = [discord.SelectOption(label=g, value=g) for g in groups[:25]]
        view = NoActivitySelectView(self.cog, options, self.date_str, interaction.message)
=======
        await interaction.response.send_message(embed=embed, view=ReportCreationView(cog=self.cog), ephemeral=True)

    @discord.ui.button(label="今日は活動なしを報告", style=discord.ButtonStyle.secondary, custom_id="report_no_activity_button")
    async def report_no_activity(self, interaction: discord.Interaction, button: discord.ui.Button):
        today_str = datetime.date.today().isoformat()
        plan_log = load_json(PLAN_LOG_FILE_NAME)
        todays_groups = sorted(plan_log.get(today_str, {}).get("groups", {}).keys())
        if not todays_groups:
            await interaction.response.send_message("本日の活動計画がないため、活動なし報告の対象がありません。", ephemeral=True)
            return
        options = [discord.SelectOption(label=g, value=g) for g in todays_groups[:25]]
        view = NoActivitySelectView(self.cog, options)
>>>>>>> main
        await interaction.response.send_message("活動なしとして記録するグループを選択してください。", view=view, ephemeral=True)


class NoActivitySelect(discord.ui.Select):
<<<<<<< HEAD
    def __init__(self, cog, options: List[discord.SelectOption], date_str: str, source_message: discord.Message | None = None):
        self.cog = cog
        self.date_str = date_str
        self.source_message = source_message
        super().__init__(placeholder="活動なしとして記録するグループを選択", options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.cog.report_no_activity(
            interaction,
            self.values[0],
            report_date_str=self.date_str,
            source_message=self.source_message,
        )


class NoActivitySelectView(discord.ui.View):
    def __init__(self, cog, options: List[discord.SelectOption], date_str: str, source_message: discord.Message | None = None):
        super().__init__(timeout=120)
        self.add_item(NoActivitySelect(cog, options, date_str, source_message))
=======
    def __init__(self, cog, options: List[discord.SelectOption]):
        self.cog = cog
        super().__init__(placeholder="活動なしとして記録するグループを選択", options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.cog.report_no_activity(interaction, self.values[0])


class NoActivitySelectView(discord.ui.View):
    def __init__(self, cog, options: List[discord.SelectOption]):
        super().__init__(timeout=120)
        self.add_item(NoActivitySelect(cog, options))
>>>>>>> main
