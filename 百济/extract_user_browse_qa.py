#!/usr/bin/env python3

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(description="Extract browse / QA / recall data from full.log")
    parser.add_argument(
        "--log",
        default="/Users/layla.zhang/workspace/nullht-test/yzj_knowledge/full.log",
        help="Path to full.log",
    )
    parser.add_argument(
        "--out",
        default="/Users/layla.zhang/workspace/nullht-test/yzj_knowledge/日志_用户画像_浏览与问答.xlsx",
        help="Output Excel path",
    )
    return parser.parse_args()


def fmt_uid(value):
    if value is None:
        return None
    return "'" + str(value)


def safe_json_loads(text, default=None):
    if text is None:
        return {} if default is None else default
    try:
        return json.loads(text)
    except Exception:
        return {} if default is None else default


def json_text(value):
    return json.dumps(value, ensure_ascii=False)


def normalize_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def extract_json_block(block_text):
    text = (block_text or "").strip()
    if "{" not in text or "}" not in text:
        return None
    text = text[text.find("{") : text.rfind("}") + 1]
    return safe_json_loads(text, default=None)


def parse_inline_list(text):
    text = (text or "").strip()
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def to_number(value):
    if value in (None, "", "null", "None"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def max_score(a, b):
    a_num = to_number(a)
    b_num = to_number(b)
    if a_num is None:
        return b
    if b_num is None:
        return a
    return a if a_num >= b_num else b


def update_file_meta(file_meta_by_id, kb_name_by_id, *, file_id=None, kb_id=None, kb_name=None, file_name=None, file_type=None):
    if file_id in (None, ""):
        return
    file_id = str(file_id)
    meta = file_meta_by_id[file_id]
    if kb_id not in (None, "") and not meta.get("kb_id"):
        meta["kb_id"] = str(kb_id)
    if file_name and file_name not in ("null", "None") and not meta.get("file_name"):
        meta["file_name"] = file_name
    if file_type and not meta.get("file_type"):
        meta["file_type"] = file_type
    if kb_name and kb_name not in ("null", "None"):
        if kb_id not in (None, ""):
            kb_name_by_id[str(kb_id)] = kb_name
        if not meta.get("kb_name"):
            meta["kb_name"] = kb_name


def enrich_file_fields(row, file_meta_by_id, kb_name_by_id):
    file_id = row.get("fileId")
    if file_id in (None, ""):
        return row
    meta = file_meta_by_id.get(str(file_id), {})
    kb_id = row.get("kbId") or meta.get("kb_id")
    if kb_id not in (None, ""):
        row["kbId"] = str(kb_id)
    if not row.get("kbName"):
        row["kbName"] = meta.get("kb_name") or kb_name_by_id.get(str(row.get("kbId") or ""))
    if not row.get("fileName"):
        row["fileName"] = meta.get("file_name")
    return row


def is_article_candidate(event_row):
    event_type = str(event_row.get("eventType") or "")
    event_id = str(event_row.get("eventId") or "")
    has_file = bool(event_row.get("fileId") or event_row.get("fileName"))
    if has_file:
        return True, "包含file_id/file_name，判定为文件浏览事件"
    if event_type in ("点击「查看原文/打开文件」", "访问文件详情页"):
        return True, f"eventType={event_type}，判定为文章浏览行为"
    event_id_low = event_id.lower()
    if "file" in event_id_low and ("view" in event_id_low or "browse" in event_id_low):
        return True, f"eventId={event_id} 命中文件浏览模式"
    return False, "非文章浏览事件"


def dedupe_intent_rows(rows):
    merged = {}
    ordered = []
    for row in rows:
        key = (
            row.get("userId"),
            row.get("qaList"),
            row.get("visitFileList"),
            row.get("tagCandidateSet"),
            row.get("tagToFileIdsMap"),
        )
        if key not in merged:
            merged[key] = dict(row)
            ordered.append(key)
            continue
        target = merged[key]
        for field in ("keyWords", "prefTags", "queryText", "candidateTagSize", "outputLogLineNo"):
            if not target.get(field) and row.get(field):
                target[field] = row.get(field)
        if row.get("inputLogLineNo") and (
            not target.get("inputLogLineNo") or row["inputLogLineNo"] < target["inputLogLineNo"]
        ):
            target["inputLogLineNo"] = row["inputLogLineNo"]
    return [merged[key] for key in ordered]


def dedupe_recall_rows(rows):
    merged = {}
    ordered = []
    for row in rows:
        key = (
            row.get("userId"),
            row.get("recallType"),
            str(row.get("fileId") or ""),
            str(row.get("kbId") or ""),
            row.get("permission"),
        )
        if key not in merged:
            merged[key] = dict(row)
            merged[key]["logHitCount"] = 1
            ordered.append(key)
            continue
        target = merged[key]
        target["logHitCount"] += 1
        target["score"] = max_score(target.get("score"), row.get("score"))
        if (row.get("hitTagCount") or 0) > (target.get("hitTagCount") or 0):
            target["hitTagCount"] = row.get("hitTagCount")
        if not target.get("fileName") and row.get("fileName"):
            target["fileName"] = row.get("fileName")
        if not target.get("kbId") and row.get("kbId"):
            target["kbId"] = row.get("kbId")
        if not target.get("kbName") and row.get("kbName"):
            target["kbName"] = row.get("kbName")
        if not target.get("queryText") and row.get("queryText"):
            target["queryText"] = row.get("queryText")
        if not target.get("prefTags") and row.get("prefTags"):
            target["prefTags"] = row.get("prefTags")
        if row.get("logLineNo") and (
            not target.get("logLineNo") or row["logLineNo"] < target["logLineNo"]
        ):
            target["logLineNo"] = row["logLineNo"]
        existing_tags = set(safe_json_loads(target.get("hitTags") or "[]", []))
        new_tags = set(safe_json_loads(row.get("hitTags") or "[]", []))
        if existing_tags or new_tags:
            target["hitTags"] = json_text(sorted(existing_tags | new_tags))
    return [merged[key] for key in ordered]


def build_browse_rows(lines, users, file_meta_by_id, kb_name_by_id):
    browse_rows = []
    raw_browse_line_no = None

    for line_no, line in enumerate(lines, 1):
        if "开始处理近7天的浏览记录：" not in line:
            continue
        raw_browse_line_no = line_no
        payload = line.split("开始处理近7天的浏览记录：", 1)[1]
        events = safe_json_loads(payload, [])
        for event in events:
            uid = fmt_uid(event.get("userId"))
            if not uid:
                continue
            users.add(uid)
            event_data = event.get("eventData") if isinstance(event.get("eventData"), dict) else {}
            page_view = event_data.get("pv") if isinstance(event_data.get("pv"), dict) else {}
            file_id = event_data.get("file_id") or event.get("fileId")
            file_name = event_data.get("file_name") or event.get("fileName")
            kb_id = event_data.get("kb_id") or event_data.get("from_kb_id")
            kb_name = event_data.get("kb_name") or event_data.get("from_kb_name")
            row = {
                "userId": uid,
                "stage": "raw_browse",
                "eventTime": event.get("eventTime"),
                "title": file_name or page_view.get("title"),
                "fileId": str(file_id) if file_id is not None else None,
                "fileType": event_data.get("file_type"),
                "kbId": str(kb_id) if kb_id is not None else None,
                "kbName": kb_name,
                "tags": None,
                "visitCnt7d": None,
                "eventType": event.get("eventType"),
                "eventId": event.get("eventId"),
                "pageName": event.get("pageName"),
                "platform": event.get("platform"),
                "question": event.get("question"),
                "ruleReason": None,
                "requestId": event.get("requestId"),
                "logLineNo": line_no,
            }
            browse_rows.append(row)
            update_file_meta(
                file_meta_by_id,
                kb_name_by_id,
                file_id=file_id,
                kb_id=kb_id,
                kb_name=kb_name,
                file_name=file_name,
                file_type=event_data.get("file_type"),
            )

            is_candidate, reason = is_article_candidate(row)
            if is_candidate:
                candidate_row = dict(row)
                candidate_row["stage"] = "browse_candidate"
                candidate_row["ruleReason"] = reason
                browse_rows.append(candidate_row)
        break

    return browse_rows, raw_browse_line_no


def build_qa_rows(lines, users):
    qa_rows = []
    re_qa_raw = re.compile(r"用户(\d+)开始清洗问答数据，原始条数: (\d+) ,数据：(\[.*\])")
    re_rule = re.compile(r"用户(\d+)规则过滤后: (\d+)/(\d+)，过滤: (\d+)")
    re_exact = re.compile(r"用户(\d+)精确去重后: (\d+)/(\d+)，去重: (\d+)")
    re_semantic = re.compile(r"用户(\d+)语义去重后: (\d+)/(\d+)，去重: (\d+)，最终: (\d+).*(result：\[.*\])")

    for line_no, line in enumerate(lines, 1):
        match = re_qa_raw.search(line)
        if match:
            uid = fmt_uid(match.group(1))
            users.add(uid)
            items = safe_json_loads(match.group(3), [])
            qa_rows.append(
                {
                    "userId": uid,
                    "stage": "qa_raw_count",
                    "text": None,
                    "createdTime": None,
                    "answerId": None,
                    "recordId": None,
                    "isDeepThink": None,
                    "countBefore": int(match.group(2)),
                    "countAfter": None,
                    "filtered": None,
                    "dedup": None,
                    "finalCount": None,
                    "logLineNo": line_no,
                }
            )
            for item in items:
                qa_rows.append(
                    {
                        "userId": uid,
                        "stage": "qa_raw_item",
                        "text": item.get("chat_question"),
                        "createdTime": item.get("created_time"),
                        "answerId": item.get("answer_id"),
                        "recordId": item.get("id"),
                        "isDeepThink": item.get("is_deep_think"),
                        "countBefore": None,
                        "countAfter": None,
                        "filtered": None,
                        "dedup": None,
                        "finalCount": None,
                        "logLineNo": line_no,
                    }
                )
            continue

        match = re_rule.search(line)
        if match:
            uid = fmt_uid(match.group(1))
            users.add(uid)
            qa_rows.append(
                {
                    "userId": uid,
                    "stage": "qa_rule_filter",
                    "text": None,
                    "createdTime": None,
                    "answerId": None,
                    "recordId": None,
                    "isDeepThink": None,
                    "countBefore": int(match.group(3)),
                    "countAfter": int(match.group(2)),
                    "filtered": int(match.group(4)),
                    "dedup": None,
                    "finalCount": None,
                    "logLineNo": line_no,
                }
            )
            continue

        match = re_exact.search(line)
        if match:
            uid = fmt_uid(match.group(1))
            users.add(uid)
            qa_rows.append(
                {
                    "userId": uid,
                    "stage": "qa_exact_dedup",
                    "text": None,
                    "createdTime": None,
                    "answerId": None,
                    "recordId": None,
                    "isDeepThink": None,
                    "countBefore": int(match.group(3)),
                    "countAfter": int(match.group(2)),
                    "filtered": None,
                    "dedup": int(match.group(4)),
                    "finalCount": None,
                    "logLineNo": line_no,
                }
            )
            continue

        match = re_semantic.search(line)
        if match:
            uid = fmt_uid(match.group(1))
            users.add(uid)
            qa_rows.append(
                {
                    "userId": uid,
                    "stage": "qa_semantic_dedup",
                    "text": None,
                    "createdTime": None,
                    "answerId": None,
                    "recordId": None,
                    "isDeepThink": None,
                    "countBefore": int(match.group(3)),
                    "countAfter": int(match.group(2)),
                    "filtered": None,
                    "dedup": int(match.group(4)),
                    "finalCount": int(match.group(5)),
                    "logLineNo": line_no,
                }
            )
            result_json = match.group(6).split("result：", 1)[1]
            for item in safe_json_loads(result_json, []):
                qa_rows.append(
                    {
                        "userId": uid,
                        "stage": "qa_semantic_item",
                        "text": item.get("text"),
                        "createdTime": item.get("createTime"),
                        "answerId": None,
                        "recordId": None,
                        "isDeepThink": None,
                        "countBefore": None,
                        "countAfter": None,
                        "filtered": None,
                        "dedup": None,
                        "finalCount": None,
                        "logLineNo": line_no,
                    }
                )

    return qa_rows


def build_recommendation_rows(lines, users, browse_rows, file_meta_by_id, kb_name_by_id):
    intent_rows = []
    recall_rows = []
    result_rows = []

    latest_intent_idx_by_user = {}
    pending_output_idx = None
    current_user = None
    current_phase = None
    current_phase_user = None
    active_tag = None
    tag_recall_row_idx = {}

    re_user_start = re.compile(r"生成用户每日推荐开始, userId=(\d+)")
    re_llm_input = re.compile(r"调用大模型输入, userId=(\d+) \| input=(\{.*\})")
    re_llm_pref = re.compile(r"LLM返回prefTags=\[(.*?)\], candidateTagSize=(\d+)")
    re_vector_start = re.compile(r"开始向量召回, userId=(\d+), queryText=(.*)")
    re_vector_keep = re.compile(
        r"向量召回保留: userId=(\d+), fileId=(\d+), projectId=(\d+), title=(.*?), score=([0-9eE.\-]+)"
    )
    re_vector_skip = re.compile(
        r"向量召回跳过: 无权限, userId=(\d+), fileId=(\d+), projectId=(\d+), title=(.*?), score=([0-9eE.\-]+)"
    )
    re_vector_end = re.compile(
        r"向量召回完成, userId=(\d+), rawChunks=(\d+), afterRerank=(\d+), afterDedup=(\d+), "
        r"metaDataNull=(\d+), permissionDenied=(\d+), final=(\d+)"
    )
    re_tag_start = re.compile(r"开始标签召回, userId=(\d+), tags=\[(.*)\], mapSize=(\d+)")
    re_tag_end = re.compile(r"标签召回完成, userId=(\d+), tagMatchedFiles=(\d+), final=(\d+)")
    re_permission = re.compile(r"用户有文件读取权限, userId=(\d+), projectId=(\d+), fileId=(\d+)")
    re_final_candidates = re.compile(r"准备使用高频文件补足, userId=(\d+), finalCandidates=(\[.*\])")
    re_hot_files = re.compile(r"最终获取到的有权限的高频文件, userId=(\d+), hotFiles=(\[.*\])")
    re_saved = re.compile(r"推荐结果已保存, userId=(\d+), date=([0-9-]+), count=(\d+)")

    border_line = re.compile(r"^═+")

    line_index = 0
    while line_index < len(lines):
        line_no = line_index + 1
        line = lines[line_index]

        match = re_user_start.search(line)
        if match:
            current_user = fmt_uid(match.group(1))
            users.add(current_user)

        match = re_llm_input.search(line)
        if match:
            uid = fmt_uid(match.group(1))
            users.add(uid)
            current_user = uid
            input_obj = safe_json_loads(match.group(2), {})
            user_content = None
            for message in input_obj.get("messages", []):
                if message.get("role") == "user":
                    user_content = message.get("content")
                    break
            user_obj = safe_json_loads(user_content, {})
            qa_list = user_obj.get("qaList", [])
            visit_file_list = user_obj.get("visitFileList", [])
            tag_candidate_set = user_obj.get("tagCandidateSet", [])
            tag_to_file_ids_map = user_obj.get("tagToFileIdsMap", {})

            intent_rows.append(
                {
                    "userId": uid,
                    "qaList": json_text(qa_list),
                    "visitFileList": json_text(visit_file_list),
                    "tagCandidateSet": json_text(tag_candidate_set),
                    "tagToFileIdsMap": json_text(tag_to_file_ids_map),
                    "keyWords": None,
                    "prefTags": None,
                    "queryText": None,
                    "candidateTagSize": None,
                    "inputLogLineNo": line_no,
                    "outputLogLineNo": None,
                }
            )
            latest_intent_idx_by_user[uid] = len(intent_rows) - 1
            pending_output_idx = len(intent_rows) - 1

            for visit in visit_file_list:
                browse_rows.append(
                    {
                        "userId": uid,
                        "stage": "visit_file_list",
                        "eventTime": None,
                        "title": visit.get("title"),
                        "fileId": None,
                        "fileType": None,
                        "kbId": None,
                        "kbName": None,
                        "tags": json_text(visit.get("tags", [])),
                        "visitCnt7d": visit.get("visitCnt7d"),
                        "eventType": None,
                        "eventId": None,
                        "pageName": None,
                        "platform": None,
                        "question": None,
                        "ruleReason": None,
                        "requestId": None,
                        "logLineNo": line_no,
                    }
                )

            line_index += 1
            continue

        if "大模型输出:" in line:
            block_start_line = line_no
            scan_index = line_index + 1
            block_lines = []
            while scan_index < len(lines):
                if border_line.match(lines[scan_index]):
                    break
                block_lines.append(lines[scan_index].strip())
                scan_index += 1
            if pending_output_idx is not None:
                output_obj = extract_json_block("\n".join(block_lines))
                if isinstance(output_obj, dict) and {"key_words", "pref_tags"} <= set(output_obj.keys()):
                    intent_rows[pending_output_idx]["keyWords"] = json_text(output_obj.get("key_words", []))
                    intent_rows[pending_output_idx]["prefTags"] = json_text(output_obj.get("pref_tags", []))
                    intent_rows[pending_output_idx]["outputLogLineNo"] = block_start_line
                    pending_output_idx = None
            line_index = scan_index + 1
            continue

        match = re_llm_pref.search(line)
        if match and current_user in latest_intent_idx_by_user:
            intent_rows[latest_intent_idx_by_user[current_user]]["candidateTagSize"] = int(match.group(2))

        match = re_vector_start.search(line)
        if match:
            uid = fmt_uid(match.group(1))
            current_user = uid
            current_phase = "vector"
            current_phase_user = uid
            users.add(uid)
            if uid in latest_intent_idx_by_user and not intent_rows[latest_intent_idx_by_user[uid]].get("queryText"):
                intent_rows[latest_intent_idx_by_user[uid]]["queryText"] = match.group(2).strip()
            line_index += 1
            continue

        match = re_vector_keep.search(line)
        if match:
            uid = fmt_uid(match.group(1))
            users.add(uid)
            file_id = match.group(2)
            kb_id = match.group(3)
            title = match.group(4)
            score = match.group(5)
            query_text = None
            if uid in latest_intent_idx_by_user:
                query_text = intent_rows[latest_intent_idx_by_user[uid]].get("queryText")
            update_file_meta(file_meta_by_id, kb_name_by_id, file_id=file_id, kb_id=kb_id, file_name=title)
            recall_rows.append(
                {
                    "userId": uid,
                    "recallType": "向量召回",
                    "permission": "有权限",
                    "status": "保留",
                    "fileId": file_id,
                    "fileName": None if title in ("null", "None") else title,
                    "kbId": kb_id,
                    "kbName": None,
                    "score": score,
                    "hitTagCount": None,
                    "hitTags": None,
                    "queryText": query_text,
                    "prefTags": None,
                    "source": "vector_log",
                    "logLineNo": line_no,
                    "note": None,
                }
            )
            line_index += 1
            continue

        match = re_vector_skip.search(line)
        if match:
            uid = fmt_uid(match.group(1))
            users.add(uid)
            file_id = match.group(2)
            kb_id = match.group(3)
            title = match.group(4)
            score = match.group(5)
            query_text = None
            if uid in latest_intent_idx_by_user:
                query_text = intent_rows[latest_intent_idx_by_user[uid]].get("queryText")
            update_file_meta(file_meta_by_id, kb_name_by_id, file_id=file_id, kb_id=kb_id, file_name=title)
            recall_rows.append(
                {
                    "userId": uid,
                    "recallType": "向量召回",
                    "permission": "无权限",
                    "status": "跳过",
                    "fileId": file_id,
                    "fileName": None if title in ("null", "None") else title,
                    "kbId": kb_id,
                    "kbName": None,
                    "score": score,
                    "hitTagCount": None,
                    "hitTags": None,
                    "queryText": query_text,
                    "prefTags": None,
                    "source": "vector_log",
                    "logLineNo": line_no,
                    "note": None,
                }
            )
            line_index += 1
            continue

        match = re_vector_end.search(line)
        if match:
            uid = fmt_uid(match.group(1))
            if current_phase == "vector" and current_phase_user == uid:
                current_phase = None
                current_phase_user = None
            line_index += 1
            continue

        match = re_tag_start.search(line)
        if match:
            uid = fmt_uid(match.group(1))
            users.add(uid)
            current_user = uid
            current_phase = "tag"
            current_phase_user = uid
            selected_tags = parse_inline_list(match.group(2))
            tag_map = {}
            if uid in latest_intent_idx_by_user:
                tag_map = safe_json_loads(intent_rows[latest_intent_idx_by_user[uid]].get("tagToFileIdsMap"), {})
            matched_files = defaultdict(set)
            for tag in selected_tags:
                for file_id in tag_map.get(tag, []):
                    matched_files[str(file_id)].add(tag)
            active_tag = {
                "userId": uid,
                "selectedTags": selected_tags,
                "matchedFiles": matched_files,
                "permissionYes": {},
                "startLineNo": line_no,
            }
            line_index += 1
            continue

        match = re_permission.search(line)
        if match:
            uid = fmt_uid(match.group(1))
            users.add(uid)
            kb_id = match.group(2)
            file_id = match.group(3)
            update_file_meta(file_meta_by_id, kb_name_by_id, file_id=file_id, kb_id=kb_id)
            if current_phase == "tag" and active_tag and current_phase_user == uid:
                active_tag["permissionYes"][str(file_id)] = line_no
            line_index += 1
            continue

        match = re_tag_end.search(line)
        if match:
            uid = fmt_uid(match.group(1))
            users.add(uid)
            if active_tag and active_tag["userId"] == uid:
                pref_tags_json = json_text(active_tag["selectedTags"])
                for file_id, hit_tags in active_tag["matchedFiles"].items():
                    permission = "有权限" if file_id in active_tag["permissionYes"] else "无权限"
                    status = "保留" if permission == "有权限" else "跳过"
                    recall_row = {
                        "userId": uid,
                        "recallType": "标签召回",
                        "permission": permission,
                        "status": status,
                        "fileId": file_id,
                        "fileName": None,
                        "kbId": None,
                        "kbName": None,
                        "score": None,
                        "hitTagCount": len(hit_tags),
                        "hitTags": json_text(sorted(hit_tags)),
                        "queryText": None,
                        "prefTags": pref_tags_json,
                        "source": "tag_map_reconstructed",
                        "logLineNo": active_tag["permissionYes"].get(file_id) or line_no,
                        "note": "标签召回日志未逐条输出score，未命中最终候选时score为空",
                    }
                    recall_rows.append(recall_row)
                    tag_recall_row_idx[(uid, str(file_id))] = len(recall_rows) - 1
                active_tag = None
            if current_phase == "tag" and current_phase_user == uid:
                current_phase = None
                current_phase_user = None
            line_index += 1
            continue

        match = re_final_candidates.search(line)
        if match:
            uid = fmt_uid(match.group(1))
            users.add(uid)
            items = safe_json_loads(match.group(2), [])
            for item in items:
                file_id = item.get("fileId")
                kb_id = item.get("projectId")
                update_file_meta(
                    file_meta_by_id,
                    kb_name_by_id,
                    file_id=file_id,
                    kb_id=kb_id,
                    file_name=item.get("title"),
                )
                result_rows.append(
                    {
                        "userId": uid,
                        "stage": "final_candidates",
                        "fileId": str(file_id) if file_id is not None else None,
                        "fileName": item.get("title"),
                        "kbId": str(kb_id) if kb_id is not None else None,
                        "kbName": None,
                        "score": item.get("recallScore"),
                        "hitTagCount": item.get("hitTagCount"),
                        "hitTags": json_text(item.get("hitTags", [])),
                        "visitCount7d": item.get("visitCount7d"),
                        "date": None,
                        "count": None,
                        "sourceCode": item.get("source"),
                        "logLineNo": line_no,
                    }
                )
                if item.get("source") == 2:
                    tag_key = (uid, str(file_id))
                    if tag_key in tag_recall_row_idx:
                        target = recall_rows[tag_recall_row_idx[tag_key]]
                        target["score"] = item.get("recallScore")
                        target["fileName"] = target.get("fileName") or item.get("title")
                        target["kbId"] = target.get("kbId") or (str(kb_id) if kb_id is not None else None)
                        if item.get("hitTagCount") is not None:
                            target["hitTagCount"] = item.get("hitTagCount")
                        if item.get("hitTags") is not None:
                            target["hitTags"] = json_text(item.get("hitTags", []))
            line_index += 1
            continue

        match = re_hot_files.search(line)
        if match:
            uid = fmt_uid(match.group(1))
            users.add(uid)
            items = safe_json_loads(match.group(2), [])
            for item in items:
                file_id = item.get("fileId")
                kb_id = item.get("projectId")
                update_file_meta(
                    file_meta_by_id,
                    kb_name_by_id,
                    file_id=file_id,
                    kb_id=kb_id,
                    file_name=item.get("title"),
                )
                result_rows.append(
                    {
                        "userId": uid,
                        "stage": "hot_files",
                        "fileId": str(file_id) if file_id is not None else None,
                        "fileName": item.get("title"),
                        "kbId": str(kb_id) if kb_id is not None else None,
                        "kbName": None,
                        "score": item.get("recallScore"),
                        "hitTagCount": item.get("hitTagCount"),
                        "hitTags": json_text(item.get("hitTags", [])),
                        "visitCount7d": item.get("visitCount7d"),
                        "date": None,
                        "count": None,
                        "sourceCode": item.get("source"),
                        "logLineNo": line_no,
                    }
                )
            line_index += 1
            continue

        match = re_saved.search(line)
        if match:
            uid = fmt_uid(match.group(1))
            users.add(uid)
            result_rows.append(
                {
                    "userId": uid,
                    "stage": "saved_count",
                    "fileId": None,
                    "fileName": None,
                    "kbId": None,
                    "kbName": None,
                    "score": None,
                    "hitTagCount": None,
                    "hitTags": None,
                    "visitCount7d": None,
                    "date": match.group(2),
                    "count": int(match.group(3)),
                    "sourceCode": None,
                    "logLineNo": line_no,
                }
            )
            line_index += 1
            continue

        line_index += 1

    return intent_rows, recall_rows, result_rows


def main():
    args = parse_args()
    log_path = Path(args.log)
    out_path = Path(args.out)

    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()

    users = set()
    file_meta_by_id = defaultdict(dict)
    kb_name_by_id = {}

    browse_rows, raw_browse_line_no = build_browse_rows(lines, users, file_meta_by_id, kb_name_by_id)
    qa_rows = build_qa_rows(lines, users)
    intent_rows, recall_rows, result_rows = build_recommendation_rows(
        lines, users, browse_rows, file_meta_by_id, kb_name_by_id
    )

    intent_rows = dedupe_intent_rows(intent_rows)
    recall_rows = dedupe_recall_rows(recall_rows)

    for row in browse_rows:
        if row.get("fileId"):
            enrich_file_fields(row, file_meta_by_id, kb_name_by_id)
    for row in recall_rows:
        enrich_file_fields(row, file_meta_by_id, kb_name_by_id)
    for row in result_rows:
        if row.get("fileId"):
            enrich_file_fields(row, file_meta_by_id, kb_name_by_id)

    browse_df = pd.DataFrame(browse_rows)
    qa_df = pd.DataFrame(qa_rows)
    intent_df = pd.DataFrame(intent_rows)
    recall_df = pd.DataFrame(recall_rows)
    result_df = pd.DataFrame(result_rows)

    if not browse_df.empty:
        browse_df.sort_values(["userId", "logLineNo", "stage"], inplace=True)
    if not qa_df.empty:
        qa_df.sort_values(["userId", "logLineNo", "stage"], inplace=True)
    if not intent_df.empty:
        intent_df.sort_values(["userId", "inputLogLineNo"], inplace=True)
    if not recall_df.empty:
        recall_df["_score"] = pd.to_numeric(recall_df["score"], errors="coerce")
        recall_df.sort_values(
            ["userId", "recallType", "permission", "_score", "fileId"],
            ascending=[True, True, True, False, True],
            inplace=True,
        )
        recall_df.drop(columns=["_score"], inplace=True)
    if not result_df.empty:
        result_df.sort_values(["userId", "logLineNo", "stage"], inplace=True)

    all_users = sorted(users)
    browse_stage_counts = browse_df.groupby(["userId", "stage"]).size().to_dict() if not browse_df.empty else {}
    qa_stage_counts = qa_df.groupby(["userId", "stage"]).size().to_dict() if not qa_df.empty else {}
    intent_counts = intent_df.groupby("userId").size().to_dict() if not intent_df.empty else {}
    recall_counts = (
        recall_df.groupby(["userId", "recallType", "permission"]).size().to_dict() if not recall_df.empty else {}
    )
    saved_counts = {}
    if not result_df.empty:
        saved_df = result_df[result_df["stage"] == "saved_count"]
        if not saved_df.empty:
            saved_counts = saved_df.groupby("userId")["count"].sum().to_dict()

    summary_rows = []
    for uid in all_users:
        summary_rows.append(
            {
                "userId": uid,
                "browseRawCount": browse_stage_counts.get((uid, "raw_browse"), 0),
                "browseCandidateCount": browse_stage_counts.get((uid, "browse_candidate"), 0),
                "visitFileListCount": browse_stage_counts.get((uid, "visit_file_list"), 0),
                "qaRawItemCount": qa_stage_counts.get((uid, "qa_raw_item"), 0),
                "qaSemanticItemCount": qa_stage_counts.get((uid, "qa_semantic_item"), 0),
                "intentCount": intent_counts.get(uid, 0),
                "vectorAllowedCount": recall_counts.get((uid, "向量召回", "有权限"), 0),
                "vectorDeniedCount": recall_counts.get((uid, "向量召回", "无权限"), 0),
                "tagAllowedCount": recall_counts.get((uid, "标签召回", "有权限"), 0),
                "tagDeniedCount": recall_counts.get((uid, "标签召回", "无权限"), 0),
                "savedRecommendCount": int(saved_counts.get(uid, 0)),
                "rawBrowseLogLineNo": raw_browse_line_no,
            }
        )

    summary_df = pd.DataFrame(summary_rows)

    header_maps = {
        "汇总": {
            "userId": "userId(用户ID)",
            "browseRawCount": "browseRawCount(原始浏览条数)",
            "browseCandidateCount": "browseCandidateCount(文章浏览候选条数)",
            "visitFileListCount": "visitFileListCount(入模浏览条数)",
            "qaRawItemCount": "qaRawItemCount(问答原始条数)",
            "qaSemanticItemCount": "qaSemanticItemCount(问答语义去重条数)",
            "intentCount": "intentCount(意图提炼记录数)",
            "vectorAllowedCount": "vectorAllowedCount(向量召回有权限文件数)",
            "vectorDeniedCount": "vectorDeniedCount(向量召回无权限文件数)",
            "tagAllowedCount": "tagAllowedCount(标签召回有权限文件数)",
            "tagDeniedCount": "tagDeniedCount(标签召回无权限文件数)",
            "savedRecommendCount": "savedRecommendCount(最终保存推荐数)",
            "rawBrowseLogLineNo": "rawBrowseLogLineNo(原始浏览日志行号)",
        },
        "浏览链路": {
            "userId": "userId(用户ID)",
            "stage": "stage(链路阶段)",
            "eventTime": "eventTime(事件时间)",
            "title": "title(标题/文件名)",
            "fileId": "fileId(文件ID)",
            "fileType": "fileType(文件类型)",
            "kbId": "kbId(知识库ID)",
            "kbName": "kbName(知识库名称)",
            "tags": "tags(标签JSON)",
            "visitCnt7d": "visitCnt7d(近7天访问次数)",
            "eventType": "eventType(事件类型)",
            "eventId": "eventId(事件ID)",
            "pageName": "pageName(页面名称)",
            "platform": "platform(平台)",
            "question": "question(问题/文本)",
            "ruleReason": "ruleReason(判定原因)",
            "requestId": "requestId(请求ID)",
            "logLineNo": "logLineNo(日志行号)",
        },
        "问答链路": {
            "userId": "userId(用户ID)",
            "stage": "stage(清洗阶段)",
            "text": "text(问题/文本)",
            "createdTime": "createdTime(创建时间)",
            "answerId": "answerId(回答ID)",
            "recordId": "recordId(记录ID)",
            "isDeepThink": "isDeepThink(是否深度思考)",
            "countBefore": "countBefore(处理前条数)",
            "countAfter": "countAfter(处理后条数)",
            "filtered": "filtered(过滤数量)",
            "dedup": "dedup(去重数量)",
            "finalCount": "finalCount(最终条数)",
            "logLineNo": "logLineNo(日志行号)",
        },
        "意图提炼": {
            "userId": "userId(用户ID)",
            "qaList": "qaList(问答输入JSON)",
            "visitFileList": "visitFileList(浏览输入JSON)",
            "tagCandidateSet": "tagCandidateSet(候选标签JSON)",
            "tagToFileIdsMap": "tagToFileIdsMap(标签映射JSON)",
            "keyWords": "keyWords(提炼关键词JSON)",
            "prefTags": "prefTags(提炼偏好标签JSON)",
            "queryText": "queryText(向量召回查询词)",
            "candidateTagSize": "candidateTagSize(候选标签数量)",
            "inputLogLineNo": "inputLogLineNo(输入日志行号)",
            "outputLogLineNo": "outputLogLineNo(输出日志行号)",
        },
        "召回明细": {
            "userId": "userId(用户ID)",
            "recallType": "recallType(召回类型)",
            "permission": "permission(是否有权限)",
            "status": "status(处理结果)",
            "fileId": "fileId(文件ID)",
            "fileName": "fileName(文件名)",
            "kbId": "kbId(知识库ID)",
            "kbName": "kbName(知识库名称)",
            "score": "score(分数)",
            "hitTagCount": "hitTagCount(命中标签数)",
            "hitTags": "hitTags(命中标签JSON)",
            "queryText": "queryText(向量召回查询词)",
            "prefTags": "prefTags(标签召回使用标签JSON)",
            "source": "source(来源)",
            "logLineNo": "logLineNo(日志行号)",
            "note": "note(备注)",
            "logHitCount": "logHitCount(相同文件日志命中次数)",
        },
        "结果补足": {
            "userId": "userId(用户ID)",
            "stage": "stage(结果阶段)",
            "fileId": "fileId(文件ID)",
            "fileName": "fileName(文件名)",
            "kbId": "kbId(知识库ID)",
            "kbName": "kbName(知识库名称)",
            "score": "score(分数)",
            "hitTagCount": "hitTagCount(命中标签数)",
            "hitTags": "hitTags(命中标签JSON)",
            "visitCount7d": "visitCount7d(近7天访问次数)",
            "date": "date(推荐日期)",
            "count": "count(保存推荐数)",
            "sourceCode": "sourceCode(来源编码)",
            "logLineNo": "logLineNo(日志行号)",
        },
    }

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        sheets = {
            "汇总": summary_df,
            "浏览链路": browse_df,
            "问答链路": qa_df,
            "意图提炼": intent_df,
            "召回明细": recall_df,
            "结果补足": result_df,
        }
        for sheet_name, df in sheets.items():
            rename_map = header_maps.get(sheet_name, {})
            output_df = df.rename(columns=rename_map) if rename_map and not df.empty else df
            output_df.to_excel(writer, index=False, sheet_name=sheet_name)

    print(out_path)


if __name__ == "__main__":
    main()
