"""Reusable PDF + DeepSeek extraction logic (shared by extract_info.py / batch_process.py).

Public API:
    extract_pdf_text(pdf_path)      -> str              读取 PDF 全文
    to_pure_json(raw)               -> str              把模型回复规整成纯 JSON
    extract_fields(text, api_key)   -> dict             返回四个字段 + _raw 原始 JSON
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    raise SystemExit("缺少 pdfplumber，请先执行：python -m pip install -r requirements.txt")

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    raise SystemExit("缺少 openai，请先执行：python -m pip install openai")

BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"
FIELDS = ["姓名", "电话", "邮箱", "日期"]

# ---- 多模态（视觉）相关：deepseek-flash 支持图片输入 ----
VISION_MODEL = "deepseek-flash"
NO_DATA_PLACEHOLDER = "无结构化数据"

DOC_PROMPT = (
    "请分析这张图片或文档，识别所有的表格和结构化数据。识别出表头，并以 JSON 格式返回包含所有列的数据。\n"
    "\n"
    "输出要求（必须严格遵守）：\n"
    "1. 只输出一个 JSON 对象，不要输出任何解释文字，不要使用 ``` 代码块包裹。\n"
    "2. JSON 结构固定为：\n"
    '   {"表名": {"表头": [...], "数据": [ {列名: 值, ...}, ... ]}}\n'
    "3. 顶层键是表名，同一份文档里的多张表用不同的表名区分；表名用简短中文，如 \"商品清单\"、\"员工信息\"。\n"
    '4. 每个表里 "表头" 是字符串数组，按原文档从左到右的顺序排列。\n'
    '5. "数据" 是对象数组，每个对象的键必须与 "表头" 完全一致，一行数据一个对象。\n'
    "6. 单元格里的数字保留原样（可以是数字或字符串），缺失的单元格填 null，不要臆造内容。\n"
    '7. 如果图片或文档中完全没有表格或结构化数据，只输出 {"数据": "无结构化数据"}。\n'
    "\n"
    "命名规范（很重要，便于多份文档汇总）：\n"
    "8. 表头请使用通用规范的列名，例如：商品名称、数量、单价、金额、日期、姓名、电话、部门、工号。\n"
    "   不要因为原文写作\"商品\"、\"品名\"、\"货物\"就换用不同的列名，统一用\"商品名称\"。\n"
    "9. 同类表格（例如都是商品清单）请使用完全相同的表名和列名，不要加入文件特有的后缀。\n"
    "10. 如果同一份文档里两张表其实描述同一类记录，请合并成一张表，不要拆开。\n"
)

SYSTEM_PROMPT = (
    "你是一个信息抽取引擎。请从下面的文本中提取【姓名、电话、邮箱、日期】这四项信息。\n"
    "要求：\n"
    "1. 只输出纯 JSON，不要输出任何解释、前后缀、markdown 代码块或多余文字。\n"
    '2. JSON 顶层必须且只能包含这四个键："姓名"、"电话"、"邮箱"、"日期"。\n'
    "3. 每项的值是字符串；同一项有多个值时用英文逗号连接；文本中没有的项填空字符串 \"\"。\n"
    "4. 不要臆造原文中不存在的信息。\n"
    "5. 电话保留原文数字，日期规范成 YYYY-MM-DD（无法确定格式时保留原文）。\n"
)


def extract_pdf_text(pdf_path: str | Path) -> str:
    """Return the full text of a PDF (all pages joined by newlines)."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        pages = [(page.extract_text() or "") for page in pdf.pages]
    return "\n".join(pages).strip()


def to_pure_json(raw: str) -> str:
    """Normalize a model reply into a pure JSON string; raise ValueError if impossible."""
    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise ValueError(f"模型未返回 JSON：{raw!r}")
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError(f"模型返回的不是 JSON 对象：{raw!r}")

    ordered: dict[str, str] = {field: data.get(field, "") for field in FIELDS}
    for extra_key, value in data.items():
        if extra_key not in ordered:
            ordered[extra_key] = value
    for key, value in ordered.items():
        if not isinstance(value, str):
            ordered[key] = json.dumps(value, ensure_ascii=False)
    return json.dumps(ordered, ensure_ascii=False, indent=2)


def call_deepseek(api_key: str, text: str, model: str = MODEL) -> str:
    """Send text to DeepSeek in JSON mode and return the raw reply string."""
    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"待抽取文本：\n\n{text}"},
        ],
        temperature=0,
        max_tokens=500,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content or ""


def extract_fields(text: str, api_key: str, model: str = MODEL) -> dict:
    """Extract the four fields from text. Returns {字段: 值, "_raw": 原始JSON字符串}."""
    pure = to_pure_json(call_deepseek(api_key, text, model))
    data: dict = json.loads(pure)
    data["_raw"] = pure
    return data


def resolve_api_key(cli_key: str | None = None, fallback_dir: str | Path | None = None) -> str | None:
    """Find the API key: explicit arg -> env var -> .env in fallback_dir or cwd."""
    if cli_key and cli_key.strip():
        return cli_key.strip()
    env_key = os.environ.get("DEEPSEEK_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()
    candidates = []
    if fallback_dir is not None:
        candidates.append(Path(fallback_dir) / ".env")
    candidates.append(Path.cwd() / ".env")
    for candidate in candidates:
        if candidate.is_file():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                if name.strip() == "DEEPSEEK_API_KEY":
                    return value.strip().strip('"').strip("'")
    return None
