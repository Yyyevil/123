"""智能文档表格提取器 —— Streamlit 前端。

运行：
    streamlit run app.py

功能：
- 拖拽批量上传 PDF / JPG / PNG
- 上传文件先落盘到 output\\uploads\\<批次>
- 点击「开始提取」后逐个调用多模态提取逻辑（multimodal_extractor）
- 页面显示进度、识别到的表格、数据预览，并可下载 Excel / JSON
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import info_extractor as ie
import multimodal_extractor as mx

HERE = Path(__file__).resolve().parent
UPLOAD_ROOT = HERE / "output" / "uploads"
RESULT_DIR = HERE / "output" / "web"

CSS = """
<style>
    .block-container {padding-top: 2.2rem; padding-bottom: 3rem;}
    h1.app-title {
        font-size: 2.9rem; font-weight: 800; letter-spacing: 1px;
        background: linear-gradient(90deg, #1F4E79 0%, #2E8BC0 55%, #48B1A0 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: .2rem;
    }
    p.app-sub {color: #6b7280; font-size: 1.02rem; margin-top: 0; margin-bottom: 1.4rem;}
    div[data-testid="stMetricValue"] {font-size: 1.5rem;}
    .hint-box {
        background: #f6f9fc; border-left: 4px solid #2E8BC0;
        padding: .7rem 1rem; border-radius: .35rem; color: #33415c; font-size: .93rem;
    }
</style>
"""


# --------------------------------------------------------------------------- 工具函数
def get_api_key() -> str | None:
    """优先用侧边栏输入，其次环境变量 / .env。"""
    typed = st.session_state.get("api_key_input", "")
    if typed and typed.strip():
        return typed.strip()
    return ie.resolve_api_key(None, fallback_dir=HERE)


def save_uploads(files, batch_dir: Path) -> list[Path]:
    """把上传的文件落盘，返回保存后的路径列表。"""
    batch_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for uploaded in files:
        target = batch_dir / Path(uploaded.name).name
        with target.open("wb") as handle:
            handle.write(uploaded.getbuffer())
        saved.append(target)
    return saved


def run_extraction(files: list[Path], api_key: str, options: dict, progress_bar, status_text):
    """逐个文件提取，实时更新进度。返回 (results, sheets)。"""
    import time

    results: list[dict] = []
    total = len(files)
    for index, path in enumerate(files, start=1):
        progress_bar.progress((index - 1) / total, text=f"正在处理 {index}/{total}：{path.name}")
        status_text.caption(f"⏳ 正在解析 **{path.name}**（{index}/{total}）…")
        results.append(
            mx.extract_structured(
                path,
                api_key,
                model=options["model"],
                hint=options["hint"],
                scale=options["scale"],
            )
        )
        if options["delay"] and index < total:
            time.sleep(options["delay"])
    progress_bar.progress(1.0, text=f"处理完成，共 {total} 个文件")
    return results, mx.build_sheets(results, normalize=not options["no_normalize"])


def to_excel_bytes(sheets: dict[str, pd.DataFrame], index_rows: list[dict]) -> bytes:
    """把结果写进内存里的 Excel（供下载按钮使用）。"""
    import io

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(index_rows).to_excel(writer, index=False, sheet_name="汇总索引")
        for name, sheet_frame in sheets.items():
            sheet_frame.to_excel(writer, index=False, sheet_name=name)
    return buffer.getvalue()


def json_bytes(results: list[dict]) -> bytes:
    payload = [
        {
            "文件名": result["文件名"],
            "状态": result["状态"],
            "表": {name: frame.to_dict(orient="records") for name, frame in result.get("tables", {}).items()},
        }
        for result in results
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def render_preview(results: list[dict], sheets: dict[str, pd.DataFrame]) -> None:
    """结果预览：指标卡 + 每张表的数据预览。"""
    ok = sum(1 for result in results if result.get("tables"))
    skipped = len(results) - ok
    rows = int(sum(len(frame) for frame in sheets.values()))

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("上传文件", len(results))
    col2.metric("识别到表格", len(sheets))
    col3.metric("累计数据行", rows)
    col4.metric("跳过（无表格）", skipped)

    if skipped:
        names = "、".join(result["文件名"] for result in results if not result.get("tables"))
        st.info(f"以下文件没有识别到表格，已跳过（不影响其它文件）：{names}", icon="ℹ️")

    errors = [
        result
        for result in results
        if result.get("状态", "").startswith(
            ("RuntimeError", "APIError", "AuthenticationError", "APIConnectionError", "RateLimitError", "Error")
        )
    ]
    if errors:
        with st.expander(f"⚠️ {len(errors)} 个文件处理出错，点击查看详情"):
            for result in errors:
                st.write(f"**{result['文件名']}**：{result['状态']}")

    if not sheets:
        st.warning("没有识别到任何表格。可以试试提高渲染清晰度，或填写「额外提示」说明文档类型。", icon="🤔")
        return

    st.subheader("数据预览")
    tabs = st.tabs([f"{name}（{len(frame)} 行 × {len(frame.columns)} 列）" for name, frame in sheets.items()])
    for tab, (name, frame) in zip(tabs, sheets.items()):
        with tab:
            st.dataframe(frame, width="stretch", height=min(420, 90 + 36 * min(len(frame), 9)))
            st.download_button(
                "下载这张表 (CSV)",
                frame.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"{name}.csv",
                mime="text/csv",
                key=f"csv_{name}",
            )


def configure_page() -> None:
    st.set_page_config(page_title="智能文档表格提取器", page_icon="📄", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- 主流程
def main() -> None:
    configure_page()

    st.markdown('<h1 class="app-title">📄 智能文档表格提取器</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="app-sub">拖拽上传 PDF / 图片，视觉大模型自动识别表格与结构化数据，'
        "动态生成 Excel —— 不同文档可以有完全不同的列。</p>",
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("⚙️ 设置")
        st.text_input(
            "DeepSeek API Key",
            value="",
            type="password",
            key="api_key_input",
            help="留空则读取环境变量 DEEPSEEK_API_KEY 或项目下的 .env",
        )
        api_key = get_api_key()
        if api_key:
            st.success("API Key 已就绪", icon="✅")
        else:
            st.warning("未检测到 API Key，请在上方填写", icon="🔑")

        model = st.text_input("视觉模型", value=ie.VISION_MODEL)
        hint = st.text_area(
            "额外提示（可选）",
            value="",
            height=80,
            placeholder="例如：这些文件都是员工档案，请统一使用同一个表名",
            help="用来引导模型，尤其是需要把多份文档合并成同一张表时",
        )
        layout = st.radio("结果布局", ["宽表（每行一条记录）", "长表（字段/值，适合档案卡）"], index=0)
        scale = st.slider("PDF 渲染清晰度", 1.0, 4.0, 2.0, 0.5, help="越高越清晰，但请求更大更慢")
        delay = st.slider("每个文件间隔（秒）", 0.0, 5.0, 1.0, 0.5, help="防止接口限流")
        no_normalize = st.checkbox("关闭列名同义归一", value=False)
        keep_files = st.checkbox("保留上传的原始文件", value=True)

        st.divider()
        st.caption(f"工作目录：{HERE}")
        if st.button("🧹 清理历史上传与结果", width="stretch"):
            for folder in (UPLOAD_ROOT, RESULT_DIR):
                shutil.rmtree(folder, ignore_errors=True)
            st.session_state.pop("results", None)
            st.session_state.pop("sheets", None)
            st.success("已清理")

    uploaded = st.file_uploader(
        "把文件拖到这里，或点击选择（支持同时上传多个 PDF / JPG / PNG）",
        type=["pdf", "png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"],
        accept_multiple_files=True,
    )

    if uploaded:
        total_bytes = sum(file.size for file in uploaded)
        st.markdown(
            f'<div class="hint-box">已选择 <b>{len(uploaded)}</b> 个文件，'
            f"合计 <b>{total_bytes / 1024:.0f} KB</b>：" + "、".join(f.name for f in uploaded) + "</div>",
            unsafe_allow_html=True,
        )
        st.write("")
        cols = st.columns(min(len(uploaded), 6))
        for index, file in enumerate(uploaded):
            with cols[index % len(cols)]:
                if Path(file.name).suffix.lower() in mx.IMAGE_SUFFIXES:
                    st.image(file, caption=file.name, width="stretch")
                else:
                    st.caption(f"📄 {file.name}")

    start = st.button("🚀 开始提取", type="primary", width="stretch", disabled=not uploaded)

    if start:
        if not api_key:
            st.error("请先在左侧填写 DeepSeek API Key（或设置环境变量 DEEPSEEK_API_KEY）")
            return
        if not uploaded:
            st.error("请先上传至少一个文件")
            return

        batch_dir = UPLOAD_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S")
        saved = save_uploads(uploaded, batch_dir)
        st.caption(f"已保存到本地：`{batch_dir}`")

        options = {
            "model": model or ie.VISION_MODEL,
            "hint": hint,
            "scale": scale,
            "delay": delay,
            "no_normalize": no_normalize,
        }
        progress = st.progress(0.0, text="准备中…")
        status = st.empty()
        try:
            results, sheets = run_extraction(saved, api_key, options, progress, status)
        except Exception as exc:  # 兜底，页面不白屏
            st.error(f"处理过程出错：{exc.__class__.__name__}: {exc}")
            return

        if layout.startswith("长表"):
            sheets = mx.reshape_long(sheets)
        if not keep_files and batch_dir.exists():
            shutil.rmtree(batch_dir, ignore_errors=True)

        st.session_state["results"] = results
        st.session_state["sheets"] = sheets
        st.session_state["index_rows"] = mx.make_index_rows(results)
        st.session_state["batch_dir"] = str(batch_dir)
        status.empty()

    results = st.session_state.get("results")
    sheets = st.session_state.get("sheets")
    if results is None or sheets is None:
        return

    st.divider()
    st.header("✅ 提取结果")
    render_preview(results, sheets)

    index_rows = st.session_state.get("index_rows", [])
    with st.expander("📊 汇总索引（每个文件识别到哪些表）"):
        st.dataframe(pd.DataFrame(index_rows), width="stretch")

    st.subheader("下载")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    excel_path = RESULT_DIR / f"extracted_tables_{stamp}.xlsx"
    excel_path.write_bytes(to_excel_bytes(sheets, index_rows))

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.download_button(
            "⬇️ 下载 Excel 表格",
            excel_path.read_bytes(),
            file_name=excel_path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            width="stretch",
        )
    with col2:
        st.download_button(
            "下载 JSON",
            json_bytes(results),
            file_name=f"extracted_tables_{stamp}.json",
            mime="application/json",
            width="stretch",
        )
    with col3:
        st.caption(f"服务端副本：\n`{excel_path.name}`")

    with st.expander("📄 原始 JSON（模型返回的结构化数据）"):
        st.code(json_bytes(results).decode("utf-8"), language="json")


# 只有真正在 Streamlit 运行时才执行页面；被 import（测试/复用函数）时不触发
def _running_in_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


if _running_in_streamlit():
    main()
