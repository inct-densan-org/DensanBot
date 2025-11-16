import json
import os
import datetime
import shutil
import calendar
import openpyxl
import re

from .config_manager import load_config

# --- 定数 ---
JST = datetime.timezone(datetime.timedelta(hours=9))
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]
ZEN_TO_HAN = str.maketrans("０１２３４５６７８９：－", "0123456789:-")

# --- 動的な選択肢の生成 ---
def get_group_options() -> list[str]:
    config = load_config()
    editable_groups = config.get("editable_groups", [])
    # 順序を維持しつつ重複を削除
    return list(dict.fromkeys(editable_groups + ["全体", "その他"]))

def get_location_options() -> list[str]:
    config = load_config()
    editable_locations = config.get("editable_locations", [])
    return list(dict.fromkeys(editable_locations + ["その他"]))

# ファイルパス
REPORT_LOG_FILE = "bot_activity_log.json"
PLAN_LOG_FILE_NAME = "bot_plan_log.json"
REGULAR_PLANS_FILE = "regular_plans.json"
OFF_PERIODS_FILE = "off_periods.json"
REMINDERS_FILE = "reminders.json"

# (これ以降のヘルパー関数は変更なし)
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
        return [] if "plans" in filename or "periods" in filename or "reminders" in filename else {}
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return [] if "plans" in filename or "periods" in filename or "reminders" in filename else {}

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

async def create_new_month_excel_if_needed(year: int, month: int) -> tuple[str | None, str | None]:
    filename = get_excel_filename_for_month(year, month)
    if os.path.exists(filename):
        return filename, None
    try:
        config = load_config()
        template_file = config.get("template_file_name")
        if not template_file or not os.path.exists(template_file):
            return None, f"テンプレートファイル '{template_file}' が見つかりません。"
        shutil.copy(template_file, filename)
        workbook = openpyxl.load_workbook(filename)
        advisor = config.get("advisor_name")
        student_rep = config.get("student_rep_name")
        if "活動計画書" in workbook.sheetnames:
            sheet_plan = workbook["活動計画書"]
            sheet_plan["J9"] = year; sheet_plan["J10"] = month
            sheet_plan["H5"] = advisor; sheet_plan["F5"] = student_rep
        if "活動報告書" in workbook.sheetnames:
            sheet_report = workbook["活動報告書"]
            sheet_report["I5"] = f"（顧問）{advisor}"; sheet_report["I4"] = f"（学生）{student_rep}"
        regular_plans = load_json(REGULAR_PLANS_FILE)
        off_periods = load_json(OFF_PERIODS_FILE)
        if "活動計画書" in workbook.sheetnames:
            sheet = workbook["活動計画書"]
            num_days = calendar.monthrange(year, month)[1]
            for day in range(1, num_days + 1):
                current_date = datetime.date(year, month, day)
                is_off = False
                for period in off_periods:
                    start_d = datetime.datetime.fromisoformat(period["start_date"]).date()
                    end_d = datetime.datetime.fromisoformat(period["end_date"]).date()
                    if period["is_test_period"]:
                        start_d -= datetime.timedelta(days=7)
                        end_d += datetime.timedelta(days=7)
                    if start_d <= current_date <= end_d:
                        is_off = True
                        break
                if not is_off:
                    weekday = current_date.weekday()
                    day_plans = [p for p in regular_plans if p["weekday"] == weekday]
                    if day_plans:
                        target_row = day + 6
                        sheet[f"C{target_row}"] = min(p["start_time"] for p in day_plans)
                        sheet[f"E{target_row}"] = max(p["end_time"] for p in day_plans)
                        sheet[f"F{target_row}"] = " | ".join([f"{p['location']}({p['group']})" for p in day_plans])
                        sheet[f"G{target_row}"] = "、".join([p["group"] for p in day_plans])
        workbook.save(filename)
        return filename, None
    except Exception as e:
        print(f"Excelファイル作成中にエラー: {e}")
        return None, f"Excelファイル作成中にエラーが発生しました: {e}"
