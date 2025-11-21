import discord
from discord import app_commands
import json
import os
import datetime
import shutil
import calendar
import openpyxl
import re
import uuid
from typing import List

from .config_manager import load_config

# --- 定数 ---
JST = datetime.timezone(datetime.timedelta(hours=9))
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]
ZEN_TO_HAN = str.maketrans("０１２３４５６７８９：－", "0123456789:-")

# --- 動的な選択肢の生成 ---
def get_group_options() -> list[str]:
    config = load_config()
    editable_groups = config.get("editable_groups", [])
    return list(dict.fromkeys(editable_groups + ["全体", "その他"]))

def get_location_options() -> list[str]:
    config = load_config()
    editable_locations = config.get("editable_locations", [])
    return list(dict.fromkeys(editable_locations + ["その他"]))

# --- オートコンプリート用の関数 ---
async def group_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    groups = get_group_options()
    return [app_commands.Choice(name=group, value=group) for group in groups if current.lower() in group.lower()]

async def location_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    locations = get_location_options()
    return [app_commands.Choice(name=loc, value=loc) for loc in locations if current.lower() in loc.lower()]

# ファイルパス
REPORT_LOG_FILE = "bot_activity_log.json"
PLAN_LOG_FILE_NAME = "bot_plan_log.json"
REGULAR_PLANS_FILE = "regular_plans.json"
OFF_PERIODS_FILE = "off_periods.json"
REMINDERS_FILE = "reminders.json"

def parse_time(time_str: str) -> str | None:
    if not time_str: return None
    time_str = time_str.translate(ZEN_TO_HAN)
    digits = re.sub(r'\D', '', time_str)
    if len(digits) in [3, 4]:
        try:
            h_len = 1 if len(digits) == 3 else 2
            h, m = digits[:h_len], digits[h_len:]
            if 0 <= int(h) < 24 and 0 <= int(m) < 60:
                return f"{int(h):02}:{m}"
        except (ValueError, IndexError): pass
    match = re.search(r'(\d{1,2}):(\d{2})', time_str)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        if 0 <= h < 24 and 0 <= m < 60:
            return f"{h:02}:{m:02}"
    return None

def parse_date(date_str: str) -> str | None:
    if not date_str: return None
    date_str = date_str.translate(ZEN_TO_HAN)
    digits = re.sub(r'\D', '', date_str)
    if len(digits) == 8:
        try:
            dt = datetime.datetime.strptime(digits, "%Y%m%d").date()
            return dt.isoformat()
        except ValueError: pass
    try:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        return dt.isoformat()
    except ValueError: pass
    return None

def load_json(filename):
    if not os.path.exists(filename):
        return [] if any(s in filename for s in ["plans", "periods", "reminders"]) else {}
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return [] if any(s in filename for s in ["plans", "periods", "reminders"]) else {}

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_wareki(year: int) -> tuple[str, int]:
    if year >= 2019:
        reiwa_year = year - 2018
        return f"令和{reiwa_year}年", reiwa_year
    return f"西暦{year}年", year

def get_excel_filename_for_month(year: int, month: int) -> str:
    _, wareki_year = get_wareki(year)
    return f"[電子計算機部]R{wareki_year}年{month:02}月_活動計画書・活動報告書・活動延長願（複合書式）.xlsx"

def generate_monthly_schedule(year: int, month: int, overwrite: bool = False) -> tuple[str | None, str | None]:
    excel_filename = get_excel_filename_for_month(year, month)
    config = load_config()
    
    if not os.path.exists(excel_filename) or overwrite:
        try:
            template_file = config.get("template_file_name")
            if not template_file or not os.path.exists(template_file):
                return None, f"テンプレートファイル '{template_file}' が見つかりません。"
            shutil.copy(template_file, excel_filename)
        except Exception as e:
            return None, f"Excelファイルのコピー中にエラーが発生しました: {e}"
    
    try:
        workbook = openpyxl.load_workbook(excel_filename)
        plan_log = load_json(PLAN_LOG_FILE_NAME)
        regular_plans = load_json(REGULAR_PLANS_FILE)
        off_periods = load_json(OFF_PERIODS_FILE)

        if overwrite:
            for date_str in list(plan_log.keys()):
                if f"{year}-{month:02}" in date_str:
                    for group, plan_data in list(plan_log[date_str]["groups"].items()):
                        if plan_data.get("is_regular", False):
                            del plan_log[date_str]["groups"][group]
                    if not plan_log[date_str]["groups"]:
                        del plan_log[date_str]

        num_days = calendar.monthrange(year, month)[1]
        for day in range(1, num_days + 1):
            current_date = datetime.date(year, month, day)
            date_str = current_date.isoformat()
            
            is_off = any(
                (datetime.datetime.fromisoformat(p["start_date"]).date() - datetime.timedelta(days=7 if p["is_test_period"] else 0))
                <= current_date <=
                (datetime.datetime.fromisoformat(p["end_date"]).date() + datetime.timedelta(days=7 if p["is_test_period"] else 0))
                for p in off_periods
            )
            if is_off: continue

            day_plans = [p for p in regular_plans if p["weekday"] == current_date.weekday()]
            if not day_plans: continue

            if date_str not in plan_log: plan_log[date_str] = {"groups": {}}

            for plan in day_plans:
                group_name = plan["group"]
                if group_name in plan_log[date_str]["groups"] and not plan_log[date_str]["groups"][group_name].get("is_regular", False):
                    continue
                
                plan_log[date_str]["groups"][group_name] = {
                    "id": str(uuid.uuid4()),
                    "start_time": plan["start_time"],
                    "end_time": plan["end_time"],
                    "location": plan["location"],
                    "plan_details": "定期活動",
                    "is_regular": True
                }

        save_json(PLAN_LOG_FILE_NAME, plan_log)

        sheet = workbook["活動計画書"]
        sheet["J9"] = year; sheet["J10"] = month
        sheet["H5"] = config.get("advisor_name"); sheet["F5"] = config.get("student_rep_name")
        
        for day in range(1, num_days + 1):
            date_str = datetime.date(year, month, day).isoformat()
            target_row = day + 6
            
            for col in ["C", "E", "F", "G"]:
                sheet[f"{col}{target_row}"] = None

            if date_str in plan_log and plan_log[date_str]["groups"]:
                todays_plans = plan_log[date_str]["groups"]
                final_start = min(v["start_time"] for v in todays_plans.values() if v.get("start_time"))
                final_end = max(v["end_time"] for v in todays_plans.values() if v.get("end_time"))
                
                location_parts = [f'{v["location"]}({k})' if k and k != "その他" else v["location"] for k, v in todays_plans.items()]
                final_location = " | ".join(sorted(list(set(location_parts))))

                plan_detail_parts = []
                for gn, p_info in todays_plans.items():
                    detail = p_info.get('plan_details')
                    if detail:
                        plan_detail_parts.append(f"{detail}({gn})" if gn and gn != "その他" else detail)
                final_plan_details = "、".join(sorted(list(set(plan_detail_parts))))

                sheet[f"C{target_row}"] = final_start
                sheet[f"E{target_row}"] = final_end
                sheet[f"F{target_row}"] = final_location
                sheet[f"G{target_row}"] = final_plan_details

        workbook.save(excel_filename)
        return excel_filename, None

    except Exception as e:
        import traceback
        print(f"スケジュール生成中にエラー: {e}\n{traceback.format_exc()}")
        return None, f"スケジュール生成中にエラーが発生しました: {e}"

async def create_new_month_excel_if_needed(year: int, month: int) -> tuple[str | None, str | None]:
    excel_filename = get_excel_filename_for_month(year, month)
    if os.path.exists(excel_filename):
        return excel_filename, None
    return generate_monthly_schedule(year, month, overwrite=False)
