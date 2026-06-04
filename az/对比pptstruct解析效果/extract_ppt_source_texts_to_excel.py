#!/usr/bin/env python3
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger
from openpyxl import Workbook
from pptx import Presentation


DEFAULT_PPT_DIR = Path("/Users/layla.zhang/测试用例/测试材料/az/验证case/")
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().with_name("ppt原文抽取结果.xlsx")
DEFAULT_LOG_PATH = Path(__file__).resolve().with_name("export_ppt_source_texts_to_excel.log")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Returns:
        argparse.Namespace: 启动参数。
    """
    parser = argparse.ArgumentParser(description="提取目录下 PPT/PPTX 每一页的原文并写入 Excel。")
    parser.add_argument("--ppt-dir", default=str(DEFAULT_PPT_DIR), help="待提取的 PPT 目录")
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH), help="输出 Excel 路径")
    return parser.parse_args()


def setup_logging() -> None:
    """初始化日志输出。"""
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="{message}")
    logger.add(str(DEFAULT_LOG_PATH), level="INFO", encoding="utf-8", mode="w", format="{message}")


def normalize_text(text: str) -> str:
    """清洗提取出的文本。

    Args:
        text: 原始文本。

    Returns:
        str: 规范化后的文本。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def compact_text(text: str) -> str:
    """压缩文本用于去重比对。

    Args:
        text: 原始文本。

    Returns:
        str: 去除空白和常见符号后的文本。
    """
    return "".join(char for char in text.lower() if char.isalnum() or "\u4e00" <= char <= "\u9fff")


def merge_text_blocks(texts: List[str]) -> str:
    """合并多来源文本并做块级去重。

    Args:
        texts: 多来源文本列表。

    Returns:
        str: 去重合并后的文本。
    """
    merged: List[str] = []
    seen = set()
    for raw_text in texts:
        normalized = normalize_text(raw_text)
        if not normalized:
            continue
        for block in normalized.split("\n"):
            block_text = normalize_text(block)
            if not block_text:
                continue
            key = compact_text(block_text)
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(block_text)
    return "\n".join(merged)


def list_ppt_files(ppt_dir: Path) -> List[Path]:
    """列出目录下所有 PPT/PPTX 文件。

    Args:
        ppt_dir: PPT 根目录。

    Returns:
        List[Path]: 文件列表。
    """
    files: List[Path] = []
    for path in sorted(ppt_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".ppt", ".pptx"}:
            files.append(path)
    return files


def require_command(command_name: str) -> None:
    """校验依赖命令是否存在。

    Args:
        command_name: 命令名。
    """
    if shutil.which(command_name) is None:
        raise RuntimeError("缺少依赖命令: {}".format(command_name))


def run_command(command: List[str]) -> None:
    """执行命令，不返回输出。

    Args:
        command: 命令列表。
    """
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def run_command_output(command: List[str]) -> str:
    """执行命令并返回标准输出。

    Args:
        command: 命令列表。

    Returns:
        str: 标准输出。
    """
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout


def safe_path_name(path: Path) -> str:
    """生成可用于临时目录的文件名。

    Args:
        path: 原始路径。

    Returns:
        str: 安全文件名。
    """
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in path.stem)


def convert_ppt_to_pptx(ppt_path: Path, work_dir: Path) -> Path:
    """将 .ppt 转换为 .pptx。

    Args:
        ppt_path: 原始 PPT 路径。
        work_dir: 临时目录。

    Returns:
        Path: 转换后的 PPTX 路径。
    """
    require_command("soffice")
    output_dir = work_dir / "pptx"
    output_dir.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "soffice",
            "--headless",
            "--convert-to",
            "pptx",
            "--outdir",
            str(output_dir),
            str(ppt_path),
        ]
    )
    pptx_path = output_dir / "{}.pptx".format(ppt_path.stem)
    if not pptx_path.exists():
        raise RuntimeError("未生成 PPTX: {}".format(pptx_path))
    return pptx_path


def resolve_presentation_path(ppt_path: Path, work_dir: Path, converted_cache: Dict[Path, Path]) -> Path:
    """获取可供 python-pptx 打开的演示文件路径。

    Args:
        ppt_path: 原始文件路径。
        work_dir: 临时目录。
        converted_cache: 转换缓存。

    Returns:
        Path: 可读取的演示文件路径。
    """
    if ppt_path.suffix.lower() == ".pptx":
        return ppt_path
    cached = converted_cache.get(ppt_path)
    if cached is not None:
        return cached
    converted = convert_ppt_to_pptx(ppt_path, work_dir)
    converted_cache[ppt_path] = converted
    return converted


def render_presentation_to_pdf(presentation_path: Path, work_dir: Path, pdf_cache: Dict[Path, Path]) -> Path:
    """将演示文件转换为 PDF。

    Args:
        presentation_path: 演示文件路径。
        work_dir: 临时目录。
        pdf_cache: PDF 缓存。

    Returns:
        Path: PDF 路径。
    """
    cached = pdf_cache.get(presentation_path)
    if cached is not None:
        return cached
    require_command("soffice")
    output_dir = work_dir / "pdf" / safe_path_name(presentation_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(presentation_path),
        ]
    )
    pdf_path = output_dir / "{}.pdf".format(presentation_path.stem)
    if not pdf_path.exists():
        pdf_files = sorted(output_dir.glob("*.pdf"))
        if not pdf_files:
            raise RuntimeError("未生成 PDF: {}".format(pdf_path))
        pdf_path = pdf_files[0]
    pdf_cache[presentation_path] = pdf_path
    return pdf_path


def extract_pdf_page_text(pdf_path: Path, page_number: int) -> str:
    """提取 PDF 指定页文本层。

    Args:
        pdf_path: PDF 路径。
        page_number: 页码。

    Returns:
        str: 文本层内容。
    """
    require_command("pdftotext")
    return run_command_output(
        [
            "pdftotext",
            "-layout",
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            str(pdf_path),
            "-",
        ]
    )


def render_pdf_page_to_png(pdf_path: Path, page_number: int, work_dir: Path) -> Path:
    """将 PDF 指定页渲染为 PNG。

    Args:
        pdf_path: PDF 路径。
        page_number: 页码。
        work_dir: 临时目录。

    Returns:
        Path: 生成的 PNG 路径。
    """
    require_command("pdftoppm")
    output_dir = work_dir / "ocr" / "{}_{}".format(safe_path_name(pdf_path), page_number)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_prefix = output_dir / "page"
    run_command(
        [
            "pdftoppm",
            "-r",
            "300",
            "-png",
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            "-singlefile",
            str(pdf_path),
            str(output_prefix),
        ]
    )
    png_path = output_dir / "page.png"
    if not png_path.exists():
        raise RuntimeError("未生成页面截图: {}".format(png_path))
    return png_path


def ocr_image_text(image_path: Path) -> str:
    """对图片做 OCR。

    Args:
        image_path: 图片路径。

    Returns:
        str: OCR 文本。
    """
    require_command("tesseract")
    return run_command_output(["tesseract", str(image_path), "stdout", "-l", "chi_sim+eng", "--psm", "6"])


def extract_slide_text_by_ocr(
    presentation_path: Path,
    page_number: int,
    work_dir: Path,
    pdf_cache: Dict[Path, Path],
) -> str:
    """使用 PDF 文本层和 OCR 兜底提取页面文本。

    Args:
        presentation_path: 演示文件路径。
        page_number: 页码。
        work_dir: 临时目录。
        pdf_cache: PDF 缓存。

    Returns:
        str: 提取到的文本。
    """
    pdf_path = render_presentation_to_pdf(presentation_path, work_dir, pdf_cache)
    texts = [extract_pdf_page_text(pdf_path, page_number)]
    image_path = render_pdf_page_to_png(pdf_path, page_number, work_dir)
    texts.append(ocr_image_text(image_path))
    return merge_text_blocks(texts)


def collect_shape_texts(shape) -> List[str]:
    """递归收集 shape 内的文本。

    Args:
        shape: pptx shape 对象。

    Returns:
        List[str]: 文本片段列表。
    """
    texts: List[str] = []
    if hasattr(shape, "shapes"):
        for child in shape.shapes:
            texts.extend(collect_shape_texts(child))
    if getattr(shape, "has_text_frame", False):
        text = normalize_text(shape.text or "")
        if text:
            texts.append(text)
    if getattr(shape, "has_table", False):
        for row in shape.table.rows:
            row_texts = []
            for cell in row.cells:
                cell_text = normalize_text(cell.text or "")
                if cell_text:
                    row_texts.append(cell_text)
            if row_texts:
                texts.append(" | ".join(row_texts))
    return texts


def extract_slide_source_text(
    ppt_path: Path,
    page_number: int,
    work_dir: Path,
    converted_cache: Dict[Path, Path],
    pdf_cache: Dict[Path, Path],
    presentation_cache: Dict[Path, Presentation],
) -> Tuple[str, str]:
    """提取指定页原文。

    Args:
        ppt_path: 原始 PPT 路径。
        page_number: 页码。
        work_dir: 临时目录。
        converted_cache: PPTX 转换缓存。
        pdf_cache: PDF 缓存。
        presentation_cache: Presentation 缓存。

    Returns:
        Tuple[str, str]: 原文和提取方式。
    """
    presentation_path = resolve_presentation_path(ppt_path, work_dir, converted_cache)
    presentation = presentation_cache.get(presentation_path)
    if presentation is None:
        presentation = Presentation(str(presentation_path))
        presentation_cache[presentation_path] = presentation
    if page_number < 1 or page_number > len(presentation.slides):
        raise RuntimeError("页码超出范围: {} / {}".format(page_number, len(presentation.slides)))

    slide = presentation.slides[page_number - 1]
    texts: List[str] = []
    for shape in slide.shapes:
        texts.extend(collect_shape_texts(shape))

    shape_text = merge_text_blocks(texts)
    ocr_text = extract_slide_text_by_ocr(presentation_path, page_number, work_dir, pdf_cache)
    merged_text = merge_text_blocks([shape_text, ocr_text])
    if merged_text:
        if shape_text and ocr_text:
            return merged_text, "shape+ocr"
        if shape_text:
            return merged_text, "shape"
        return merged_text, "ocr"

    logger.info("page text is empty after shape+ocr merge: file={} page={}", ppt_path.name, page_number)
    return "", "empty"


def get_total_pages(
    ppt_path: Path,
    work_dir: Path,
    converted_cache: Dict[Path, Path],
    presentation_cache: Dict[Path, Presentation],
) -> int:
    """获取 PPT 总页数。

    Args:
        ppt_path: 原始 PPT 路径。
        work_dir: 临时目录。
        converted_cache: PPTX 转换缓存。
        presentation_cache: Presentation 缓存。

    Returns:
        int: 总页数。
    """
    presentation_path = resolve_presentation_path(ppt_path, work_dir, converted_cache)
    presentation = presentation_cache.get(presentation_path)
    if presentation is None:
        presentation = Presentation(str(presentation_path))
        presentation_cache[presentation_path] = presentation
    return len(presentation.slides)


def build_workbook() -> Workbook:
    """构建输出工作簿。

    Returns:
        Workbook: 已初始化表头的工作簿。
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "ppt原文"
    headers = ["文件名称", "文件路径", "总页数", "页码", "提取方式", "ppt原文", "错误信息"]
    for index, header in enumerate(headers, start=1):
        sheet.cell(1, index).value = header
    return workbook


def append_row(
    sheet,
    row_index: int,
    file_path: Path,
    total_pages: int,
    page_number: int,
    extract_mode: str,
    source_text: str,
    error_message: str,
) -> None:
    """写入一行结果。

    Args:
        sheet: 工作表。
        row_index: 行号。
        file_path: 文件路径。
        total_pages: 总页数。
        page_number: 当前页码。
        extract_mode: 提取方式。
        source_text: 原文内容。
        error_message: 错误信息。
    """
    sheet.cell(row_index, 1).value = file_path.name
    sheet.cell(row_index, 2).value = str(file_path)
    sheet.cell(row_index, 3).value = total_pages
    sheet.cell(row_index, 4).value = page_number
    sheet.cell(row_index, 5).value = extract_mode
    sheet.cell(row_index, 6).value = source_text
    sheet.cell(row_index, 7).value = error_message


def main() -> int:
    """脚本主入口。

    Returns:
        int: 退出码。
    """
    args = parse_args()
    setup_logging()
    ppt_dir = Path(args.ppt_dir).expanduser().resolve()
    output_path = Path(args.output_path).expanduser().resolve()
    if not ppt_dir.exists():
        raise RuntimeError("PPT 目录不存在: {}".format(ppt_dir))

    files = list_ppt_files(ppt_dir)
    workbook = build_workbook()
    sheet = workbook.active
    row_index = 2

    with tempfile.TemporaryDirectory(prefix="ppt-source-export-") as temp_dir:
        temp_root = Path(temp_dir)
        converted_cache: Dict[Path, Path] = {}
        pdf_cache: Dict[Path, Path] = {}
        presentation_cache: Dict[Path, Presentation] = {}

        for file_path in files:
            logger.info("processing file: {}", file_path)
            try:
                total_pages = get_total_pages(file_path, temp_root, converted_cache, presentation_cache)
            except Exception as exc:
                append_row(sheet, row_index, file_path, 0, 0, "failed", "", str(exc))
                row_index += 1
                continue

            for page_number in range(1, total_pages + 1):
                try:
                    source_text, extract_mode = extract_slide_source_text(
                        file_path,
                        page_number,
                        temp_root,
                        converted_cache,
                        pdf_cache,
                        presentation_cache,
                    )
                    append_row(sheet, row_index, file_path, total_pages, page_number, extract_mode, source_text, "")
                except Exception as exc:
                    append_row(sheet, row_index, file_path, total_pages, page_number, "failed", "", str(exc))
                row_index += 1

    workbook.save(output_path)
    logger.info("Excel 已更新: {}", output_path)
    logger.info("文件数: {}", len(files))
    logger.info("写入记录数: {}", row_index - 2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
