r"""用 Streamlit 官方测试框架跑一遍 app.py，验证脚本本身无异常。

    python tests\test_app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  [PASS] {name}")
    else:
        FAILED.append(f"{name} {detail}".strip())
        print(f"  [FAIL] {name} {detail}")


print("== 1. 脚本能无异常运行（AppTest） ==")
try:
    from streamlit.testing.v1 import AppTest
except Exception as exc:  # pragma: no cover
    print(f"  [SKIP] 当前 streamlit 不支持 AppTest：{exc}")
    raise SystemExit(0)

at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
at.run()

check("脚本运行没有未捕获异常", not at.exception, str(at.exception))
titles = [block.value for block in at.markdown] if hasattr(at, "markdown") else []
joined = " ".join(str(t) for t in titles)
check("页面渲染出大标题", "智能文档表格提取器" in joined, joined[:200])
check("存在文件上传控件", len(at.get("file_uploader")) >= 1, f"实际 {len(at.get('file_uploader'))}")
check("存在开始提取按钮", any("开始提取" in (b.label or "") for b in at.button), str([b.label for b in at.button]))
check("侧边栏有 API Key 输入", any("API Key" in (i.label or "") for i in at.text_input))
check("侧边栏有模型输入", any((i.value or "").startswith("deepseek") for i in at.text_input), str([i.value for i in at.text_input]))

print("== 2. 导出函数（不依赖界面上下文） ==")
import app as app_module  # noqa: E402
import multimodal_extractor as mx  # noqa: E402
import pandas as pd  # noqa: E402

sheets = {
    "商品清单": pd.DataFrame([{"来源文件": "a.pdf", "商品名称": "苹果", "数量": "3"}]),
    "员工信息(长表)": pd.DataFrame([{"来源文件": "b.pdf", "字段": "姓名", "值": "张伟"}]),
}
index_rows = [{"来源文件": "a.pdf", "识别到的表": "商品清单", "表数量": 1, "数据行数": 1, "状态": "ok"}]

data = app_module.to_excel_bytes(sheets, index_rows)
check("Excel 字节流非空", len(data) > 2000, f"{len(data)} bytes")
check("是合法的 xlsx（zip 头）", data[:2] == b"PK", str(data[:4]))

import io

workbook = pd.ExcelFile(io.BytesIO(data))
check("Excel 含 汇总索引 + 两张表", list(workbook.sheet_names) == ["汇总索引", "商品清单", "员工信息(长表)"], str(workbook.sheet_names))

results = [{"文件名": "a.pdf", "状态": "ok", "tables": {"商品清单": sheets["商品清单"]}}]
raw = app_module.json_bytes(results)
parsed = json.loads(raw.decode("utf-8"))
check("JSON 可被标准解析", isinstance(parsed, list) and parsed[0]["文件名"] == "a.pdf", str(parsed)[:120])

print("== 3. 上传落盘逻辑 ==")


class FakeUpload:
    def __init__(self, name: str, payload: bytes) -> None:
        self.name = name
        self._payload = payload

    def getbuffer(self):
        return self._payload


import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    saved = app_module.save_uploads([FakeUpload("x.pdf", b"%PDF-1.4 test")], Path(tmp) / "batch")
    check("文件已落盘", len(saved) == 1 and saved[0].is_file(), str(saved))
    check("落盘内容一致", saved[0].read_bytes() == b"%PDF-1.4 test")

print()
print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
for item in FAILED:
    print("  FAILED:", item)
raise SystemExit(1 if FAILED else 0)
