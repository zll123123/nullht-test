#!/usr/bin/env python3
"""基于 Excel 中已有的 `ppt原文` 与 `日志中的pptstruct` 做独立语义对比。

脚本定位：
1. 不负责提取 PPT 原文。
2. 不依赖本地 PPT 目录。
3. 只消费 Excel 中现成的数据列，输出对比结果与 LLM 审核结果。

输入列：
1. 文件名称
2. 页码
3. ppt原文
4. 日志中的pptstruct

输出列：
1. diff
2. LLM错误类型
3. LLM严重程度
4. LLM判断依据
5. 人工审核结果

执行模式：
1. all
   - 先跑确定性 diff，再跑 LLM
2. diff
   - 只跑确定性 diff
3. llm
   - 只跑 LLM
   - 依赖表中已存在 diff
"""

import argparse
import json
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from loguru import logger
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


DEFAULT_EXCEL_PATH = Path(__file__).resolve().with_name("ppt原文抽取结果_获取pptstruct对比.xlsx")
DEFAULT_LOG_PATH = Path(__file__).resolve().with_name("review_pptstruct_semantics_to_excel.log")
DEFAULT_LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_LLM_MODEL = "deepseek-v4-flash"
DEFAULT_LLM_API_KEY = "sk-433e97f12d014e2d9d74ce0669aa7155"
DEFAULT_LLM_TIMEOUT_SECONDS = 120
DEFAULT_LLM_MAX_RETRIES = 3

FILE_NAME_HEADER = "文件名称"
PAGE_NUMBER_HEADER = "页码"
PPT_STRUCT_HEADER = "日志中的pptstruct"
PPT_SOURCE_HEADER = "ppt原文"
DIFF_HEADER = "diff"
LLM_ERROR_TYPE_HEADER = "LLM错误类型"
LLM_SEVERITY_HEADER = "LLM严重程度"
LLM_BASIS_HEADER = "LLM判断依据"
LLM_RESULT_HEADER = "人工审核结果"

SENTENCE_SEPARATOR_PATTERN = re.compile(r"[。！？!?；;]+|\n+")
WHITESPACE_PATTERN = re.compile(r"\s+")
ALIGNMENT_THRESHOLD = 0.55
MAX_REPORT_ITEMS = 5
MAX_TEXT_SNIPPET_LENGTH = 80


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="基于 Excel 中已有的 PPT 原文与 pptStruct 文本做独立语义对比。")
    parser.add_argument("--sheet-name", help="可选，指定工作表名称；默认使用 active sheet")
    parser.add_argument(
        "--mode",
        choices=("all", "diff", "llm"),
        default="all",
        help="all: 跑 diff + LLM；diff: 只跑 diff；llm: 只跑 LLM",
    )
    parser.add_argument(
        "--save-batch-size",
        type=int,
        default=10,
        help="每处理多少行保存一次 Excel，默认 10",
    )
    return parser.parse_args()


def setup_logging() -> None:
    logger.remove()
    logger.add(str(DEFAULT_LOG_PATH), level="INFO", encoding="utf-8", mode="w")


def normalize_name(name: str) -> str:
    normalized = name.strip().lower()
    normalized = normalized.replace(".pptx.pptx", ".pptx")
    normalized = normalized.replace(".ppt.ppt", ".ppt")
    normalized = WHITESPACE_PATTERN.sub("", normalized)
    return normalized


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [WHITESPACE_PATTERN.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def compact_text(text: str) -> str:
    return re.sub(r"[\s，,。！？!?；;:：、“”\"'‘’（）()\[\]【】·\-_/]", "", text).lower()


def shorten_text(text: str, max_length: int = MAX_TEXT_SNIPPET_LENGTH) -> str:
    text = normalize_text(text).replace("\n", " ")
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def normalize_page_number(value) -> Optional[int]:
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def collect_struct_texts(value) -> List[str]:
    texts: List[str] = []
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            normalized = normalize_text(text)
            if normalized:
                texts.append(normalized)
        summary = value.get("ppt_summary")
        if isinstance(summary, str):
            normalized = normalize_text(summary)
            if normalized:
                texts.append(normalized)
        for child_key, child_value in value.items():
            if child_key in {"text", "ppt_summary"}:
                continue
            texts.extend(collect_struct_texts(child_value))
    elif isinstance(value, list):
        for child in value:
            texts.extend(collect_struct_texts(child))
    return texts


def build_ppt_struct_text(ppt_struct_obj: Dict[str, object]) -> str:
    ordered_texts: List[str] = []
    seen = set()
    # 将 pptStruct 中分散的 text / ppt_summary 按遍历顺序拼成可比对文本。
    for text in collect_struct_texts(ppt_struct_obj):
        key = compact_text(text)
        if not key or key in seen:
            continue
        seen.add(key)
        ordered_texts.append(text)
    return normalize_text("\n".join(ordered_texts))


def split_sentences(text: str) -> List[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    sentences: List[str] = []
    for chunk in SENTENCE_SEPARATOR_PATTERN.split(normalized):
        sentence = normalize_text(chunk)
        if not sentence:
            continue
        if len(compact_text(sentence)) <= 1:
            continue
        sentences.append(sentence)
    return sentences


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, compact_text(left), compact_text(right)).ratio()


def build_best_match_map(sentences: List[str], candidates: List[str]) -> Dict[int, Tuple[Optional[int], float]]:
    result: Dict[int, Tuple[Optional[int], float]] = {}
    # 为每个句子挑选最相近的候选句，后续再做双向一致性校验。
    for sentence_index, sentence in enumerate(sentences):
        best_index: Optional[int] = None
        best_score = 0.0
        for candidate_index, candidate in enumerate(candidates):
            score = similarity(sentence, candidate)
            if score > best_score:
                best_index = candidate_index
                best_score = score
        result[sentence_index] = (best_index, best_score)
    return result


def summarize_char_diff(source_text: str, target_text: str, max_items: int = 3) -> str:
    # 对已对齐的句子做字符级差异摘要，输出替换 / 缺失 / 新增片段。
    matcher = SequenceMatcher(None, source_text, target_text)
    parts: List[str] = []
    for tag, source_start, source_end, target_start, target_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        source_fragment = source_text[source_start:source_end]
        target_fragment = target_text[target_start:target_end]
        if tag == "replace":
            parts.append("替换[{} -> {}]".format(shorten_text(source_fragment, 20), shorten_text(target_fragment, 20)))
        elif tag == "delete":
            parts.append("缺失[{}]".format(shorten_text(source_fragment, 20)))
        elif tag == "insert":
            parts.append("新增[{}]".format(shorten_text(target_fragment, 20)))
        if len(parts) >= max_items:
            break
    return "；".join(parts) if parts else "存在字符级差异"


def short_join(items: List[str], empty_text: str) -> str:
    if not items:
        return empty_text
    return "；".join(items[:MAX_REPORT_ITEMS])


def find_header_columns(sheet) -> Dict[str, int]:
    header_map: Dict[str, int] = {}
    for cell in sheet[1]:
        if isinstance(cell.value, str):
            header = cell.value.strip()
            if header:
                header_map[header] = cell.column
    return header_map


def ensure_output_column(sheet, header_map: Dict[str, int], header_name: str, preferred_index: int) -> int:
    column_index = header_map.get(header_name)
    if column_index is None:
        column_index = preferred_index
        sheet.cell(1, column_index).value = header_name
        header_map[header_name] = column_index
    return column_index


def require_columns(header_map: Dict[str, int], headers: List[str]) -> Dict[str, int]:
    missing = [header for header in headers if header not in header_map]
    if missing:
        raise RuntimeError("Excel 缺少表头: {}".format(", ".join(missing)))
    return {header: header_map[header] for header in headers}


def review_semantics(source_text: str, ppt_struct_obj: Dict[str, object]) -> Dict[str, object]:
    # 对比链路：PPT 原文 -> 句子切分 -> 双向对齐 -> 字符级差异摘要。
    struct_text = build_ppt_struct_text(ppt_struct_obj)
    source_sentences = split_sentences(source_text)
    struct_sentences = split_sentences(struct_text)

    if not source_sentences:
        return {
            "struct_text": struct_text,
            "diff_text": "PPT 原文为空，无法比对",
        }
    if not struct_sentences:
        return {
            "struct_text": struct_text,
            "diff_text": "pptStruct 未提取到有效文本",
        }

    source_to_struct = build_best_match_map(source_sentences, struct_sentences)
    struct_to_source = build_best_match_map(struct_sentences, source_sentences)

    missing_items: List[str] = []
    extra_items: List[str] = []
    diff_items: List[str] = []

    for source_index, source_sentence in enumerate(source_sentences):
        struct_index, score = source_to_struct[source_index]
        if struct_index is None or score < ALIGNMENT_THRESHOLD:
            missing_items.append("原文未覆盖: {}".format(shorten_text(source_sentence)))
            continue
        reverse_index, reverse_score = struct_to_source[struct_index]
        if reverse_index is None or reverse_score < ALIGNMENT_THRESHOLD:
            missing_items.append("原文未覆盖: {}".format(shorten_text(source_sentence)))
            continue
        struct_sentence = struct_sentences[struct_index]
        if compact_text(source_sentence) != compact_text(struct_sentence):
            diff_items.append(
                "原文[{}] vs pptStruct[{}]，{}".format(
                    shorten_text(source_sentence),
                    shorten_text(struct_sentence),
                    summarize_char_diff(source_sentence, struct_sentence),
                )
            )

    for struct_index, struct_sentence in enumerate(struct_sentences):
        source_index, score = struct_to_source[struct_index]
        if source_index is None or score < ALIGNMENT_THRESHOLD:
            extra_items.append("pptStruct 额外内容: {}".format(shorten_text(struct_sentence)))

    incomplete_items = missing_items + extra_items
    diff_text_parts: List[str] = []
    if incomplete_items:
        diff_text_parts.append(short_join(incomplete_items, ""))
    if diff_items:
        diff_text_parts.append(short_join(diff_items, ""))
    diff_text = "\n".join(part for part in diff_text_parts if part)
    if not diff_text:
        diff_text = "无差异"
    return {
        "struct_text": struct_text,
        "diff_text": diff_text,
    }


def build_llm_prompt(source_text: str, struct_text: str, compare_summary: str) -> str:
    return """你是一名严格的医学内容审核助手。
    请基于给定的PPT原文、pptStruct文本和差异摘要，判断问题类型、严重程度和依据。

输出要求：
1. 仅输出JSON，不要输出Markdown代码块。
2. JSON字段固定为：error_type, severity, basis, result。
3. error_type 从以下枚举中选一个或多个并用顿号连接：语义遗漏、语义冗余、事实错误、表述偏差、结构错位、无法判断。
4. severity 只能是：高、中、低。
5. 如果审核通过或未发现明显问题，basis 必须返回空字符串。
6. 只有判断存在不一致或风险时，basis 才填写中文简洁说明判断依据。
7. result 用中文总结审核意见。

PPT原文：
{source_text}

pptStruct文本：
{struct_text}

对比差异：
{compare_summary}
""".format(source_text=source_text, struct_text=struct_text, compare_summary=compare_summary)


def normalize_llm_json(content: str) -> Dict[str, str]:
    normalized = content.strip()
    normalized = re.sub(r"<think>.*?</think>", "", normalized, flags=re.DOTALL).strip()
    if normalized.startswith("```"):
        normalized = normalized.strip("`")
        if normalized.startswith("json"):
            normalized = normalized[4:].strip()
    parsed = json.loads(normalized)
    return {
        "error_type": str(parsed.get("error_type") or "无法判断"),
        "severity": str(parsed.get("severity") or "无法判断"),
        "basis": str(parsed.get("basis") or ""),
        "result": str(parsed.get("result") or ""),
    }


def call_llm_review(source_text: str, struct_text: str, compare_summary: str) -> Dict[str, str]:
    if not DEFAULT_LLM_API_KEY or "请在这里填写实际LLM_API_KEY" in DEFAULT_LLM_API_KEY:
        return {
            "error_type": "LLM未配置",
            "severity": "无法判断",
            "basis": "请先在代码中配置 DEFAULT_LLM_API_KEY",
            "result": "未执行LLM审核",
        }
    payload = {
        "model": DEFAULT_LLM_MODEL,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": "你只返回JSON。"},
            {"role": "user", "content": build_llm_prompt(source_text, struct_text, compare_summary)},
        ],
    }
    last_error: Optional[Exception] = None
    for attempt in range(1, DEFAULT_LLM_MAX_RETRIES + 1):
        try:
            response = requests.post(
                DEFAULT_LLM_BASE_URL.rstrip("/") + "/chat/completions",
                headers={
                    "Authorization": "Bearer {}".format(DEFAULT_LLM_API_KEY),
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=DEFAULT_LLM_TIMEOUT_SECONDS,
            )
            if response.status_code in {429, 500, 502, 503, 504, 529}:
                raise RuntimeError(
                    "LLM 服务暂时不可用(status={}): {}".format(response.status_code, shorten_text(response.text, 300))
                )
            response.raise_for_status()
            response_json = response.json()
            content = response_json["choices"][0]["message"]["content"]
            return normalize_llm_json(content)
        except Exception as exc:
            last_error = exc
            if attempt >= DEFAULT_LLM_MAX_RETRIES:
                break
            logger.warning("LLM 调用第 {} 次失败，准备重试: {}", attempt, exc)
            time.sleep(attempt)
    raise RuntimeError(str(last_error))


def run_deterministic_compare(source_text: str, ppt_struct_obj: Dict[str, object]) -> Dict[str, object]:
    return review_semantics(source_text, ppt_struct_obj)


def run_llm_compare(source_text: str, struct_text: str, diff_text: str) -> Dict[str, str]:
    if not diff_text:
        return {
            "error_type": "无",
            "severity": "低",
            "basis": "",
            "result": "未发现明显问题",
        }
    return call_llm_review(source_text, struct_text, diff_text)


def save_if_needed(workbook, excel_path: Path, processed_rows: int, batch_size: int) -> None:
    if processed_rows % batch_size == 0:
        workbook.save(excel_path)
        logger.info("批量保存完成: processed_rows={} excel={}", processed_rows, excel_path)


def main() -> int:
    setup_logging()
    args = parse_args()
    if args.save_batch_size <= 0:
        raise RuntimeError("--save-batch-size 必须大于 0")
    excel_path = DEFAULT_EXCEL_PATH.expanduser().resolve()
    workbook = load_workbook(excel_path)
    sheet = workbook[args.sheet_name] if args.sheet_name else workbook.active
    header_map = find_header_columns(sheet)
    required_headers = [FILE_NAME_HEADER, PAGE_NUMBER_HEADER, PPT_STRUCT_HEADER, PPT_SOURCE_HEADER]
    if args.mode == "llm":
        required_headers.append(DIFF_HEADER)
    required_input_columns = require_columns(header_map, required_headers)
    diff_column = ensure_output_column(sheet, header_map, DIFF_HEADER, sheet.max_column + 1)
    llm_error_type_column = ensure_output_column(sheet, header_map, LLM_ERROR_TYPE_HEADER, max(sheet.max_column + 1, diff_column + 1))
    llm_severity_column = ensure_output_column(sheet, header_map, LLM_SEVERITY_HEADER, max(sheet.max_column + 1, llm_error_type_column + 1))
    llm_basis_column = ensure_output_column(sheet, header_map, LLM_BASIS_HEADER, max(sheet.max_column + 1, llm_severity_column + 1))
    llm_result_column = ensure_output_column(sheet, header_map, LLM_RESULT_HEADER, max(sheet.max_column + 1, llm_basis_column + 1))
    sheet.column_dimensions[get_column_letter(diff_column)].width = 80
    sheet.column_dimensions[get_column_letter(llm_error_type_column)].width = 20
    sheet.column_dimensions[get_column_letter(llm_severity_column)].width = 12
    sheet.column_dimensions[get_column_letter(llm_basis_column)].width = 60
    sheet.column_dimensions[get_column_letter(llm_result_column)].width = 40
    processed_rows = 0

    for row_index in range(2, sheet.max_row + 1):
        file_name = sheet.cell(row_index, required_input_columns[FILE_NAME_HEADER]).value
        page_number = normalize_page_number(sheet.cell(row_index, required_input_columns[PAGE_NUMBER_HEADER]).value)
        ppt_struct_raw = sheet.cell(row_index, required_input_columns[PPT_STRUCT_HEADER]).value
        source_text_raw = sheet.cell(row_index, required_input_columns[PPT_SOURCE_HEADER]).value
        if not file_name or page_number is None or not ppt_struct_raw:
            continue
        logger.info("processing row={} file={} page={}", row_index, file_name, page_number)

        try:
            ppt_struct_obj = json.loads(str(ppt_struct_raw))
        except Exception as exc:
            if args.mode in {"all", "diff"}:
                sheet.cell(row_index, diff_column).value = "pptStruct 解析失败: {}".format(exc)
            if args.mode in {"all", "llm"}:
                sheet.cell(row_index, llm_error_type_column).value = "无法判断"
                sheet.cell(row_index, llm_severity_column).value = "无法判断"
                sheet.cell(row_index, llm_basis_column).value = "pptStruct 解析失败: {}".format(exc)
                sheet.cell(row_index, llm_result_column).value = "未执行LLM审核"
            processed_rows += 1
            save_if_needed(workbook, excel_path, processed_rows, args.save_batch_size)
            continue

        source_text = normalize_text(str(source_text_raw or ""))
        if not source_text:
            diff_text = "PPT 原文为空，无法对比"
            llm_result = {
                "error_type": "无法判断",
                "severity": "无法判断",
                "basis": "PPT 原文为空，无法对比",
                "result": "未执行LLM审核",
            }
            if args.mode in {"all", "diff"}:
                sheet.cell(row_index, diff_column).value = diff_text
            if args.mode in {"all", "llm"}:
                sheet.cell(row_index, llm_error_type_column).value = llm_result["error_type"]
                sheet.cell(row_index, llm_severity_column).value = llm_result["severity"]
                sheet.cell(row_index, llm_basis_column).value = llm_result["basis"]
                sheet.cell(row_index, llm_result_column).value = llm_result["result"]
            processed_rows += 1
            save_if_needed(workbook, excel_path, processed_rows, args.save_batch_size)
            continue

        struct_text = build_ppt_struct_text(ppt_struct_obj)
        diff_text = normalize_text(str(sheet.cell(row_index, diff_column).value or ""))

        if args.mode in {"all", "diff"}:
            try:
                compare_result = run_deterministic_compare(source_text, ppt_struct_obj)
                struct_text = compare_result["struct_text"]
                diff_text = compare_result["diff_text"]
                sheet.cell(row_index, diff_column).value = diff_text
            except Exception as exc:
                diff_text = "确定性对比失败: {}".format(exc)
                sheet.cell(row_index, diff_column).value = diff_text
                if args.mode == "all":
                    llm_result = {
                        "error_type": "无法判断",
                        "severity": "无法判断",
                        "basis": "确定性对比失败: {}".format(exc),
                        "result": "未执行LLM审核",
                    }
                    sheet.cell(row_index, llm_error_type_column).value = llm_result["error_type"]
                    sheet.cell(row_index, llm_severity_column).value = llm_result["severity"]
                    sheet.cell(row_index, llm_basis_column).value = llm_result["basis"]
                    sheet.cell(row_index, llm_result_column).value = llm_result["result"]
                processed_rows += 1
                save_if_needed(workbook, excel_path, processed_rows, args.save_batch_size)
                continue

        if args.mode in {"all", "llm"}:
            if not diff_text:
                llm_result = {
                    "error_type": "无法判断",
                    "severity": "无法判断",
                    "basis": "diff 为空，请先运行 diff 模式",
                    "result": "未执行LLM审核",
                }
            else:
                try:
                    llm_result = run_llm_compare(source_text, struct_text, diff_text)
                except Exception as exc:
                    llm_result = {
                        "error_type": "无法判断",
                        "severity": "无法判断",
                        "basis": "LLM 调用失败: {}".format(exc),
                        "result": "未执行LLM审核",
                    }

            sheet.cell(row_index, llm_error_type_column).value = llm_result["error_type"]
            sheet.cell(row_index, llm_severity_column).value = llm_result["severity"]
            sheet.cell(row_index, llm_basis_column).value = llm_result["basis"]
            sheet.cell(row_index, llm_result_column).value = llm_result["result"]
        processed_rows += 1
        save_if_needed(workbook, excel_path, processed_rows, args.save_batch_size)

    workbook.save(excel_path)
    logger.info("Excel 已更新: {}", excel_path)
    logger.info("总处理行数: {}", processed_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
