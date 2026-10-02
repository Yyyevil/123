r"""离线单元测试：JSON 解析 / 多表合并 / 空值 / 防崩溃。

不联网、不调用 API，可直接运行：
    python tests\test_extract.py
（也兼容 pytest：pytest tests）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import multimodal_extractor as mx  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  [PASS] {name}")
    else:
        FAILED.append(f"{name} {detail}".strip())
        print(f"  [FAIL] {name} {detail}")


# --------------------------------------------------------------------- 用例数据
NORMAL = json.dumps(
    {
        "商品清单": {
            "表头": ["商品名称", "数量", "单价"],
            "数据": [
                {"商品名称": "苹果", "数量": 3, "单价": 5.5},
                {"商品名称": "牛奶", "数量": 2, "单价": None},
                {"商品名称": "", "数量": "", "单价": "-"},
            ],
        }
    },
    ensure_ascii=False,
)

MULTI_TABLE = json.dumps(
    {
        "销售明细": {"表头": ["产品", "销量"], "数据": [{"产品": "洗衣液", "销量": 120}]},
        "员工信息": {"表头": ["姓名", "电话"], "数据": [{"姓名": "张伟", "电话": "13812345678"}]},
    },
    ensure_ascii=False,
)

NO_TABLE = json.dumps({"数据": "无结构化数据"}, ensure_ascii=False)
FENCED = "```json\n" + NORMAL + "\n```"
BARE_LIST = json.dumps([{"a": 1, "b": 2}], ensure_ascii=False)
FLAT_ROWS = json.dumps({"员工信息": [{"姓名": "李娜"}, {"姓名": "王强"}]}, ensure_ascii=False)
NESTED_STRING = json.dumps({"结果": NORMAL}, ensure_ascii=False)
GARBAGE = "对不起，我看不出任何表格。"
TRUNCATED = '{"商品清单": {"表头": ["商品"], "数据": [{"商品": "苹果"'


def run() -> int:
    print("== 1. 基础结构解析 ==")
    tables = mx._normalize(NORMAL)
    check("识别出表名", list(tables) == ["商品清单"], str(list(tables)))
    rows = tables.get("商品清单", [])
    check("解析出 3 行", len(rows) == 3, f"实际 {len(rows)}")
    check("数字被转成字符串", rows[0]["数量"] == "3", repr(rows[0]["数量"]))
    check("缺失单元格为 None", rows[1]["单价"] is None, repr(rows[1]["单价"]))
    check("空字符串/占位符变 None", rows[2]["商品名称"] is None and rows[2]["单价"] is None, repr(rows[2]))

    print("== 2. 多表识别 ==")
    multi = mx._normalize(MULTI_TABLE)
    check("一张回复里识别出 2 张表", len(multi) == 2, str(list(multi)))
    check("表名正确", set(multi) == {"销售明细", "员工信息"}, str(set(multi)))
    check("has_data 为真", mx.has_data(multi) is True)

    print("== 3. 无表格 → 不报错 ==")
    check("无结构化数据 → 空 dict", mx._normalize(NO_TABLE) == {}, str(mx._normalize(NO_TABLE)))
    check("has_data 为假", mx.has_data(mx._normalize(NO_TABLE)) is False)
    check("乱码回复 → 空 dict", mx._normalize(GARBAGE) == {}, str(mx._normalize(GARBAGE)))
    check("截断的 JSON → 空 dict（不抛异常）", mx._normalize(TRUNCATED) == {}, str(mx._normalize(TRUNCATED)))
    check("空字符串 → 空 dict", mx._normalize("") == {})

    print("== 4. 容错格式 ==")
    check("```json 代码块能被剥离", len(mx._normalize(FENCED).get("商品清单", [])) == 3)
    list_form = mx._normalize(BARE_LIST)
    check("裸数组能用", sum(len(v) for v in list_form.values()) == 1, str(list_form))
    flat = mx._normalize(FLAT_ROWS)
    check('{"表名":[...]} 形式能用', len(flat.get("员工信息", [])) == 2, str(flat))
    nested = mx._normalize(NESTED_STRING)
    check("嵌套的 JSON 字符串能递归解析", len(nested.get("商品清单", [])) == 3, str(list(nested)))

    print("== 5. 多文件/多表合并 ==")

    class FakeResult:
        pass

    import pandas as pd

    results = [
        {"文件名": "a.pdf", "状态": "ok", "tables": {"员工信息": pd.DataFrame([{"姓名": "张伟"}])}},
        {"文件名": "b.pdf", "状态": "ok", "tables": {"员工信息": pd.DataFrame([{"姓名": "李娜", "电话": "123"}])}},
        {"文件名": "c.png", "状态": "跳过：无结构化数据", "tables": {}},
    ]
    sheets = mx.build_sheets(results)
    check("同名表跨文件合并成 1 张 sheet", list(sheets) == ["员工信息"], str(list(sheets)))
    merged = sheets["员工信息"]
    check("合并后 2 行", len(merged) == 2, f"实际 {len(merged)}")
    check("列缺失处补 NaN", pd.isna(merged.loc[0, "电话"]), str(merged.to_dict("records")))
    check("列并集保留 电话", list(merged.columns) == ["姓名", "电话"], str(list(merged.columns)))

    index_rows = mx.make_index_rows(results)
    check("索引有 3 行", len(index_rows) == 3)
    check("无表文件计入索引且状态可读", index_rows[2]["表数量"] == 0 and "无结构化数据" in index_rows[2]["状态"])

    print("== 6. 列名归一 ==")
    check("商品 → 商品名称", mx.normalize_headers("商品") == "商品名称", mx.normalize_headers("商品"))
    check("产品/品名 也归一", mx.normalize_headers("品名") == "商品名称" and mx.normalize_headers("产品") == "商品名称")
    check("联系电话 → 电话", mx.normalize_headers("联系电话") == "电话", mx.normalize_headers("联系电话"))
    check("未登记的列名原样保留", mx.normalize_headers("规格") == "规格", mx.normalize_headers("规格"))

    import pandas as pd

    same_kind = [
        {"文件名": "a.pdf", "状态": "ok", "tables": {"商品清单": pd.DataFrame([{"商品名称": "苹果", "单价": "5.5"}])}},
        {"文件名": "b.png", "状态": "ok", "tables": {"价签账单": pd.DataFrame([{"商品": "牛奶", "单价": "12"}])}},
    ]
    normalized = mx.build_sheets(same_kind, normalize=True)
    check("归一后同类表列一致", all("商品名称" in frame.columns for frame in normalized.values()),
          str({k: list(v.columns) for k, v in normalized.items()}))
    check("关闭归一后保留原列名",
          "商品" in mx.build_sheets(same_kind, normalize=False)["价签账单"].columns)

    tricky = pd.DataFrame([{"商品": "苹果", "商品名称": None}, {"商品": None, "商品名称": "牛奶"}])
    deduped = mx._dedupe_columns(tricky.rename(columns=mx.normalize_headers))
    check("重名列合并后不丢数据", list(deduped["商品名称"]) == ["苹果", "牛奶"], str(list(deduped["商品名称"])))

    print("== 7. 长表模式（档案卡） ==")
    card = pd.DataFrame(
        [{"来源文件": "a.pdf", "姓名": "赵敏", "工号": "E2088", "部门": "供应链部", "电话": "136", "邮箱": None}]
    )
    check("档案卡被识别为字段值表", mx.is_field_value_table(card) is True)
    long_frame = mx.to_long_format(card)
    check("长表是 来源文件/字段/值 三列", list(long_frame.columns) == ["来源文件", "字段", "值"], str(list(long_frame.columns)))
    check("长表只保留非空字段", len(long_frame) == 4, f"实际 {len(long_frame)}")
    check("长表内容正确", ("姓名", "赵敏") in list(zip(long_frame["字段"], long_frame["值"])))

    goods = pd.DataFrame([{"来源文件": "a.pdf", "商品名称": "苹果", "数量": "3", "单价": "5.5", "金额": "16.5"}])
    check("商品表不会被误判成字段值表", mx.is_field_value_table(goods) is False)
    two_col = pd.DataFrame([{"来源文件": "a.pdf", "字段": "姓名", "值": "张伟"}])
    check("字段/值两列表被识别", mx.is_field_value_table(two_col) is True)
    reshaped = mx.reshape_long({"员工信息": card, "商品清单": goods})
    check("reshape_long 只改档案卡", set(reshaped) == {"员工信息(长表)", "商品清单"}, str(set(reshaped)))

    print("== 8. 其他 ==")
    check("sheet 名截断到 31 字符", len(mx._safe_sheet_name("很长的表名" * 20)) <= 31)
    check("非法字符被替换", mx._safe_sheet_name("a/b:c*d?e[f]") == "a_b_c_d_e_f_", mx._safe_sheet_name("a/b:c*d?e[f]"))
    check("支持的图片后缀齐全", {".png", ".jpg", ".jpeg", ".webp"} <= mx.SUPPORTED_SUFFIXES)
    check(".pdf 在支持列表里", ".pdf" in mx.SUPPORTED_SUFFIXES)

    print()
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    for item in FAILED:
        print("  FAILED:", item)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(run())
