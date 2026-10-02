r"""端到端验证「前端点击开始提取」这条链路（会真实调用 API）。

复用 app.py 里的函数，模拟一次上传 → 提取 → 生成可下载 Excel 的全过程。

    python tests\test_app_e2e.py [样例目录]
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import app as app_module  # noqa: E402
import info_extractor as ie  # noqa: E402
import multimodal_extractor as mx  # noqa: E402

sample_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "examples" / "in"
files = sorted(p for p in sample_dir.iterdir() if p.suffix.lower() in mx.SUPPORTED_SUFFIXES)[:3]

api_key = ie.resolve_api_key(None, fallback_dir=ROOT)
if not api_key:
    print("未找到 API Key，跳过端到端测试")
    raise SystemExit(0)

print(f"样例目录：{sample_dir}")
print(f"选取 {len(files)} 个文件：{[f.name for f in files]}\n")

results = []
for index, path in enumerate(files, start=1):
    print(f"[{index}/{len(files)}] {path.name} ... ", end="", flush=True)
    result = mx.extract_structured(path, api_key, model=ie.VISION_MODEL, hint="", scale=2.0)
    results.append(result)
    print("、".join(f"{k}({len(v)}行)" for k, v in result.get("tables", {}).items()) or result["状态"])

sheets = mx.build_sheets(results, normalize=True)
index_rows = mx.make_index_rows(results)

data = app_module.to_excel_bytes(sheets, index_rows)
out_path = ROOT / "output" / "web" / "e2e_check.xlsx"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_bytes(data)

print(f"\n识别到 {len(sheets)} 张表：" + "、".join(f"{k}({len(v)}行)" for k, v in sheets.items()))
print(f"下载按钮的字节流：{len(data)} bytes，合法 xlsx：{data[:2] == b'PK'}")
print(f"已写出：{out_path}")

import io

import pandas as pd

book = pd.ExcelFile(io.BytesIO(data))
print("Excel sheet 列表：", book.sheet_names)

ok = len(data) > 2000 and data[:2] == b"PK" and len(sheets) > 0
print("\n结果：", "链路正常 ✅" if ok else "链路异常 ❌")
raise SystemExit(0 if ok else 1)
