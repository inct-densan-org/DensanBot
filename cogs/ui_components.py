import discord
from typing import Dict, Any
import datetime

# 循環インポートを避けるため、モーダルはUIコンポーネントファイル内で定義
from .utils import get_group_options, PLAN_LOG_FILE_NAME, load_json

def get_todays_plan_defaults(group_name: str) -> Dict[str, Any]:
    """今日の活動計画ログを読み込み、指定されたグループのデフォルト値を取得する"""
    defaults = {"activity_time": None, "location": None}
    plan_log = load_json(PLAN_LOG_FILE_NAME)
    today_str = datetime.date.today().isoformat()
    if todays_plan := plan_log.get(today_str, {}).get("groups", {}).get(group_name):
        start, end = todays_plan.get("start_time"), todays_plan.get("end_time")
        if start and end: defaults["activity_time"] = f"{start} - {end}"
        defaults["location"] = todays_plan.get("location")
    return defaults

class PaginationView(discord.ui.View):
    """Embedのリストをページめくりで表示するための汎用View。"""
    def __init__(self, embeds: list[discord.Embed], interaction: discord.Interaction):
        super().__init__(timeout=300)
        self.embeds = embeds
        self.interaction = interaction
        self.current_page = 0
        self.total_pages = len(embeds)
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

class ReportModal(discord.ui.Modal, title="活動報告"):
    def __init__(self, cog, default_group: str | None = None, default_location: str | None = None, default_activity_time: str | None = None):
        super().__init__()
        self.cog = cog
        if default_group and default_group != "その他": self.group.default = default_group
        else: self.group.placeholder = "活動したグループ名を入力してください"
        if default_location and default_location != "その他": self.location.default = default_location
        else: self.location.placeholder = "活動した場所を入力してください"
        if default_activity_time: self.activity_time.default = default_activity_time

    participants = discord.ui.TextInput(label="活動人数", placeholder="半角数字で入力してください")
    description = discord.ui.TextInput(label="活動内容・備考", style=discord.TextStyle.paragraph, required=False)
    activity_time = discord.ui.TextInput(label="活動時間 (開始 - 終了) (ショートハンド: hhmmhhmm)", placeholder="例: 15:00 - 17:00")
    group = discord.ui.TextInput(label="グループ")
    location = discord.ui.TextInput(label="活動場所")

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_report_submission(interaction, self)

class ReportSelectView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog
        self.add_item(GroupSelect(cog=self.cog))

class GroupSelect(discord.ui.Select):
    def __init__(self, cog):
        self.cog = cog
        options = [discord.SelectOption(label=opt, value=opt) for opt in get_group_options()]
        super().__init__(placeholder="あなたの所属グループを選択してください", options=options)
    async def callback(self, interaction: discord.Interaction):
        selected_group = self.values[0]
        defaults = get_todays_plan_defaults(selected_group)
        modal = ReportModal(cog=self.cog, default_group=selected_group, default_location=defaults.get("location"), default_activity_time=defaults.get("activity_time"))
        await interaction.response.send_modal(modal)
        await interaction.edit_original_response(content="フォームを開きました。", view=None)

class ReminderView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="活動報告を行う", style=discord.ButtonStyle.primary, custom_id="report_button")
    async def open_report_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("まず、報告するグループを選択してください。", view=ReportSelectView(cog=self.cog), ephemeral=True)
