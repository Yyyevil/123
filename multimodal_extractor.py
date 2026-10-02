"""通用表格/结构化数据提取器（多模态）。

流程：PDF / 图片  →  每页渲染成 PNG  →  DeepSeek 视觉模型（deepseek-flash）
      →  动态 JSON（表名 + 表头 + 数据行）  →  pandas DataFrame（列完全由模型决定）

设计要点：
- 不写死任何字段，列名/列数完全来自模型返回的"表头"。
- 单文件多表：同一个表名跨文件/跨页自动合并行；不同表名各出一张 sheet。
- 防崩溃：解析失败或模型认为"无结构化数据"时返回空结果，绝不抛异常。
"""

from __future__ import annotations

import base64
import io
import json
import re
from pathlib import Path

try:
    import pypdfium2 as pdfium
except ImportError:  # pragma: no cover
    raise SystemExit("缺少 pypdfium2，请先执行：python -m pip install -r requirements.txt")

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    raise SystemExit("缺少 Pillow，请先执行：python -m pip install -r requirements.txt")

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    raise SystemExit("缺少 pandas，请先执行：python -m pip install -r requirements.txt")

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    raise SystemExit("缺少 openai，请先执行：python -m pip install -r requirements.txt")

import info_extractor as ie

PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
SUPPORTED_SUFFIXES = PDF_SUFFIXES | IMAGE_SUFFIXES

NO_DATA = ie.NO_DATA_PLACEHOLDER
SOURCE_COL = "来源文件"
PLACEHOLDERS = {"", "null", "none", "n/a", "na", "-", "无", "无结构化数据", "无数据", "无表格"}

# 常见同义列名 → 规范列名。只做显式、可测试的映射，不做模糊匹配，避免把不同字段错误合并。
# 想关掉这层规范化，运行时加 --no-normalize-headers。
HEADER_ALIASES = {
    "商品": "商品名称",
    "品名": "商品名称",
    "货物名称": "商品名称",
    "产品": "商品名称",
    "产品名称": "商品名称",
    "手机号码": "电话",
    "联系电话": "电话",
    "联系方式": "电话",
    "手机号": "电话",
    "电话号码": "电话",
    "座机": "电话",
    "电子邮件": "邮箱",
    "电子邮箱": "邮箱",
    "邮件": "邮箱",
    "日期时间": "日期",
    "销售日期": "日期",
    "交易日期": "日期",
    "单价(元)": "单价",
    "金额(元)": "金额",
    "数量(件)": "数量",
    "工号": "工号",
}


def normalize_headers(name: str) -> str:
    """把列名统一成规范写法，便于跨文件合并同类表。"""
    cleaned = str(name).strip()
    return HEADER_ALIASES.get(cleaned, cleaned)


# --------------------------------------------------------------------------- 渲染
def render_pdf_pages(pdf_path: str | Path, scale: float = 2.0) -> list[Image.Image]:
    """把 PDF 每页渲染成 PIL 图片（scale=2 约等于 144 DPI）。"""
    pdf = pdfium.PdfDocument(str(pdf_path))
    images: list[Image.Image] = []
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                bitmap = page.render(scale=scale)
                image = bitmap.to_pil()
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                images.append(image)
            finally:
                try:
                    page.close()
                except Exception:
                    pass
    finally:
        try:
            pdf.close()
        except Exception:
            pass
    return images


def load_image(path: str | Path) -> list[Image.Image]:
    """读入一张图片文件，统一转成 RGB。"""
    with Image.open(str(path)) as img:
        return [img.convert("RGB")]


def file_to_images(path: str | Path, scale: float = 2.0) -> list[Image.Image]:
    """把任意支持的输入文件转成图片列表。"""
    suffix = Path(path).suffix.lower()
    if suffix in PDF_SUFFIXES:
        return render_pdf_pages(path, scale=scale)
    if suffix in IMAGE_SUFFIXES:
        return load_image(path)
    raise ValueError(f"不支持的文件类型：{suffix}")


def image_to_data_url(image: Image.Image, max_side: int = 2000) -> str:
    """PIL 图片 → data URL（按需等比缩小，避免请求体过大）。"""
    if max(image.size) > max_side:
        ratio = max_side / max(image.size)
        new_size = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
        image = image.resize(new_size, Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# --------------------------------------------------------------------------- 调用模型
def _build_content(images: list[Image.Image], prompt: str, hint: str) -> list[dict]:
    content: list[dict] = [{"type": "text", "text": prompt}]
    if hint:
        content.append({"type": "text", "text": hint})
    if len(images) > 1:
        content.append({"type": "text", "text": f"下面按顺序给出同一份文档的 {len(images)} 页图片；"
                                               f"同一张表可能跨页延续，请把它合并成一张表。"})
    for index, image in enumerate(images, start=1):
        if len(images) > 1:
            content.append({"type": "text", "text": f"—— 第 {index} 页 ——"})
        content.append({"type": "image_url", "image_url": {"url": image_to_data_url(image)}})
    return content


def call_vision(
    api_key: str,
    images: list[Image.Image],
    hint: str = "",
    model: str = ie.VISION_MODEL,
    prompt: str = ie.DOC_PROMPT,
    max_tokens: int = 4096,
) -> str:
    """调用 DeepSeek 视觉模型，返回原始回复文本（带重试与 JSON 模式回退）。"""
    client = OpenAI(api_key=api_key, base_url=ie.BASE_URL)
    content = _build_content(images, prompt, hint)
    last_error: Exception | None = None

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                temperature=0,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # 有些模型/网关不支持 response_format，回退一次
            if last_error is None and _looks_like_format_error(exc):
                try:
                    response = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": content}],
                        temperature=0,
                        max_tokens=max_tokens,
                    )
                    return response.choices[0].message.content or ""
                except Exception as inner:
                    last_error = inner
                    continue
            last_error = exc

    raise RuntimeError(f"调用视觉模型失败：{last_error}")


def _looks_like_format_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(key in text for key in ("response_format", "json_object", "invalid_request", "unsupported"))


# --------------------------------------------------------------------------- 解析
def _strip_fence(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
    return match.group(1).strip() if match else text.strip()


def _as_text(value) -> str | None:
    """把任意单元格值规整成字符串；空/占位值统一变成 None。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value != value:  # NaN
            return None
        return str(value)
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    if text == "" or text.lower() in PLACEHOLDERS:
        return None
    return text


def _normalize(inline: str) -> dict[str, list[dict]]:
    """把模型回复规整成 {表名: [行字典, ...]}，任何异常情况都返回空 dict。"""
    if not inline or not inline.strip():
        return {}
    try:
        data = json.loads(_strip_fence(inline))
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", inline, re.S)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}

    if isinstance(data, list):  # 容错：模型直接给了行数组
        rows = [_as_text_row(item) for item in data if isinstance(item, dict)]
        rows = [row for row in rows if row]
        return {NO_DATA if not rows else "提取结果": rows} if not rows else {"提取结果": rows}
    if not isinstance(data, dict):
        return {}

    tables: dict[str, list[dict]] = {}
    for name, payload in data.items():
        table_name = str(name).strip() or "提取结果"

        # 情形一：{"表名": {"表头": [...], "数据": [...]}}
        if isinstance(payload, dict) and ("数据" in payload or "表头" in payload or "data" in payload):
            rows = payload.get("数据") or payload.get("data") or []
            if isinstance(rows, dict):  # 容错：单行被包成对象
                rows = [rows]
            if not isinstance(rows, list):
                rows = []
            clean_rows = [row for row in (_as_text_row(r) for r in rows if isinstance(r, dict)) if row]
            if clean_rows:
                tables.setdefault(table_name, []).extend(clean_rows)
            continue

        # 情形二：{"表名": [ {...}, {...} ]}
        if isinstance(payload, list):
            clean_rows = [row for row in (_as_text_row(r) for r in payload if isinstance(r, dict)) if row]
            if clean_rows:
                tables.setdefault(table_name, []).extend(clean_rows)
            continue

        # 情形三：{"数据": "无结构化数据"} 之类的占位
        if isinstance(payload, str):
            text = payload.strip()
            if text and text not in PLACEHOLDERS and _looks_like_rows_text(text):
                try:
                    inner = json.loads(_strip_fence(text))
                except json.JSONDecodeError:
                    continue
                for sub_name, sub_rows in _normalize(json.dumps(inner, ensure_ascii=False)).items():
                    tables.setdefault(sub_name, []).extend(sub_rows)
            continue

        # 情形四：{"表名": {列: 值}} 单行键值对
        if isinstance(payload, dict):
            row = _as_text_row(payload)
            if row:
                tables.setdefault(table_name, []).append(row)

    return tables


def _looks_like_rows_text(text: str) -> bool:
    return text.startswith("{") or text.startswith("[")


def _as_text_row(row: dict) -> dict:
    return {str(key).strip(): _as_text(value) for key, value in row.items() if str(key).strip()}


def has_data(tables: dict[str, list[dict]]) -> bool:
    return any(rows for rows in tables.values())


# --------------------------------------------------------------------------- 对外主入口
def extract_structured(
    path: str | Path,
    api_key: str,
    model: str = ie.VISION_MODEL,
    hint: str = "",
    scale: float = 2.0,
) -> dict:
    """提取单个文件的表格数据，永不抛异常。

    返回：{"文件名": str, "状态": str, "tables": {表名: DataFrame}}
    """
    path = Path(path)
    result: dict = {"文件名": path.name, "状态": "ok", "tables": {}}
    try:
        images = file_to_images(path, scale=scale)
        if not images:
            result["状态"] = "跳过：文件没有可渲染的页面"
            return result
        raw = call_vision(api_key, images, hint=hint, model=model)
        tables = _normalize(raw)
        if not has_data(tables):
            result["状态"] = f"跳过：{NO_DATA}"
            return result
        for name, rows in tables.items():
            frame = pd.DataFrame(rows)
            if frame.empty:
                continue
            frame.insert(0, SOURCE_COL, path.name)
            result["tables"][name] = frame
        if not result["tables"]:
            result["状态"] = f"跳过：{NO_DATA}"
    except Exception as exc:
        result["状态"] = f"{exc.__class__.__name__}: {exc}"
    return result


# --------------------------------------------------------------------------- Excel 导出
def build_sheets(results: list[dict], normalize: bool = True) -> dict[str, pd.DataFrame]:
    """把多个文件的提取结果按表名合并成 {sheet名: DataFrame}。

    normalize=True 时先把列名做同义归一（商品/品名 → 商品名称 等），
    这样不同文件里的同类表能落到同一张 sheet，多余列自动补 NaN。
    """
    merged: dict[str, list[pd.DataFrame]] = {}
    for result in results:
        for table_name, frame in result.get("tables", {}).items():
            if normalize:
                frame = frame.rename(columns=normalize_headers)
                # rename 可能产生重名列（如同时有"商品"和"商品名称"），去重保留内容较多的一列
                if frame.columns.duplicated().any():
                    frame = _dedupe_columns(frame)
            merged.setdefault(_safe_sheet_name(table_name), []).append(frame)

    sheets: dict[str, pd.DataFrame] = {}
    for name, frames in merged.items():
        combined = pd.concat(frames, ignore_index=True, sort=False)
        sheets[name] = combined
    return sheets


def _dedupe_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """合并重名列：保留每行第一个非空值（注意用 iloc 取列，标签索引在重名下会返回 DataFrame）。"""
    result = pd.DataFrame(index=frame.index)
    for position, column in enumerate(frame.columns):
        series = frame.iloc[:, position]
        if column not in result.columns:
            result[column] = series
        else:
            mask = result[column].isna()
            result.loc[mask, column] = series[mask]
    return result


def _safe_sheet_name(name: str) -> str:
    """Excel sheet 名限制：≤31 字符，且不能含 []:*?/\\ 。"""
    cleaned = re.sub(r"[\[\]:*?/\\]", "_", str(name)).strip() or "Sheet"
    return cleaned[:31]


# --------------------------------------------------------------------------- 长表模式
# 常见的"字段/值"型列名，用于识别档案卡这类键值对文档
FIELD_VALUE_HEADERS = {"字段", "项目", "属性", "key", "field", "item", "名称"}
VALUE_HEADERS = {"值", "内容", "value", "content", "数据"}
# 出现频率高、基本可以确定是"字段名"的列名
TYPICAL_FIELD_NAMES = {
    "姓名", "工号", "部门", "职位", "电话", "邮箱", "日期", "性别", "年龄", "学历",
    "月薪", "薪资", "地址", "身份证号", "入职日期", "备注", "状态", "编号",
}


def is_field_value_table(frame: pd.DataFrame) -> bool:
    """判断一张表是不是"字段名当列名"的键值对表（如员工档案卡）。"""
    columns = [str(c).strip() for c in frame.columns if str(c).strip() != SOURCE_COL]
    if len(columns) < 2:
        return False
    if columns[0] in FIELD_VALUE_HEADERS and columns[1] in VALUE_HEADERS:
        return True
    hits = sum(1 for name in columns if name in TYPICAL_FIELD_NAMES)
    return hits >= 3 and hits >= len(columns) * 0.5


def to_long_format(frame: pd.DataFrame) -> pd.DataFrame:
    """把"一行一条记录、列名即字段"的表转成 来源文件/字段/值 三列，便于跨文件汇总。"""
    source = frame[SOURCE_COL] if SOURCE_COL in frame.columns else pd.Series([""] * len(frame))
    fields = [c for c in frame.columns if c != SOURCE_COL]
    records: list[dict] = []
    for position in range(len(frame)):
        for field in fields:
            value = _as_text(frame.iloc[position][field])
            if value is None:
                continue
            records.append({SOURCE_COL: source.iloc[position], "字段": str(field).strip(), "值": value})
    return pd.DataFrame(records, columns=[SOURCE_COL, "字段", "值"])


def reshape_long(sheets: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """对所有"档案卡型"的表应用长表转换。"""
    reshaped: dict[str, pd.DataFrame] = {}
    for name, frame in sheets.items():
        if is_field_value_table(frame):
            reshaped[f"{name}(长表)"] = to_long_format(frame)
        else:
            reshaped[name] = frame
    return reshaped


def write_excel(sheets: dict[str, pd.DataFrame], output_path: str | Path, index_rows: list[dict]) -> Path:
    """把多张表写入一个 Excel：第一张是汇总索引，其余每张表一个 sheet。"""
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    index_frame = pd.DataFrame(index_rows)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        index_frame.to_excel(writer, index=False, sheet_name="汇总索引")
        for name, frame in sheets.items():
            frame.to_excel(writer, index=False, sheet_name=name)

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="1F4E79")
        for sheet_name in writer.sheets:
            sheet = writer.sheets[sheet_name]
            for col_idx in range(1, sheet.max_column + 1):
                cell = sheet.cell(row=1, column=col_idx)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center", vertical="center")
                letter = get_column_letter(col_idx)
                longest = max(
                    [len(str(sheet.cell(row=r, column=col_idx).value or "")) for r in range(1, min(sheet.max_row, 200) + 1)]
                    or [8]
                )
                sheet.column_dimensions[letter].width = min(max(longest + 4, 10), 42)
            sheet.freeze_panes = "A2"
            if sheet.max_row > 1:
                sheet.auto_filter.ref = sheet.dimensions
    return output_path


def make_index_rows(results: list[dict]) -> list[dict]:
    """汇总索引：每个文件一行，说明识别到哪些表。"""
    rows = []
    for result in results:
        tables = result.get("tables", {})
        rows.append(
            {
                "来源文件": result.get("文件名", ""),
                "识别到的表": "、".join(tables.keys()) if tables else "",
                "表数量": len(tables),
                "数据行数": int(sum(len(frame) for frame in tables.values())),
                "状态": result.get("状态", ""),
            }
        )
    return rows
