import json
import mimetypes
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import requests
from loguru import logger


BASE_URL = "https://dev-api-v3-az-mlr.nullht.com"
UPLOAD_URL = f"{BASE_URL}/api/oss/upload"
CREATE_URL = f"{BASE_URL}/api/audit/management/add"
FILE_DIRECTORY = Path("/Users/layla.zhang/测试用例/测试材料/az/uat环境的case")
ENV_JSON_PATH = Path(__file__).resolve().with_name("env.json")
LOG_PATH = Path(__file__).resolve().with_name("create_audit_tasks.log")
TIMEOUT_SECONDS = 120
ALLOWED_EXTENSIONS = {".ppt", ".pptx", ".pdf", ".doc", ".docx"}
COOKIE_VALUE = "acw_tc=65859a8117767868922998173ecdecb65447593b21d795104d19d91a817262"
SUCCESS_CODES = {"00000", "0", "200"}

COMMON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
    "Cookie": COOKIE_VALUE,
    "Origin": "https://dev-v3-az-mlr.nullht.com",
    "Referer": "https://dev-v3-az-mlr.nullht.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}

UPLOAD_HEADERS = dict(COMMON_HEADERS)

CREATE_HEADERS = {
    **COMMON_HEADERS,
    "Content-Type": "application/json",
}

CREATE_PAYLOAD_TEMPLATE = {
    "file_id": "",
    "file_name": "",
    "literature_package": [],
    "category": "NS",
    "material_properties": [2],
    "file_type_level_1": [73],
    "file_type_level_2": [66],
    "file_type_level_3": [29],
    "medical_education_sub_categories": [4],
    "product_Ids": [
        "f7ce1e4f-5ca7-11f0-8e6d-00163e36469b",
        "f7ce0c74-5ca7-11f0-8e6d-00163e36469b",
        "6a104d70-9c70-4a6a-b42a-e1957aa139b7",
    ],
    "apply_channels": [11255, 11261],
    "target_audience": [17],
}


def load_authorization() -> str:
    env_data = json.loads(ENV_JSON_PATH.read_text(encoding="utf-8"))
    return env_data["authorization"].strip()


def list_target_files():
    return sorted(
        path
        for path in FILE_DIRECTORY.iterdir()
        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS
    )


def log_line(message: str) -> None:
    logger.info(message)


def masked_authorization(authorization: str) -> str:
    if len(authorization) <= 20:
        return authorization
    return f"{authorization[:16]}...{authorization[-8:]}"


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def build_curl_preview(
    prepared: requests.PreparedRequest,
    *,
    file_path: Path = None,
    payload: dict = None,
) -> str:
    parts = [f"curl {shell_quote(prepared.url)}"]
    for key, value in prepared.headers.items():
        shown_value = value
        if key.lower() == "authorization":
            shown_value = masked_authorization(value)
        parts.append(f"-H {shell_quote(f'{key}: {shown_value}')}")
    if file_path is not None:
        parts.append(f"-F {shell_quote(f'file=@{file_path}')}")
    if payload is not None:
        parts.append(f"--data-raw {shell_quote(json.dumps(payload, ensure_ascii=False))}")
    return " \\\n  ".join(parts)


def log_prepared_request(name: str, prepared: requests.PreparedRequest, *, file_path: Path = None) -> None:
    headers = dict(prepared.headers)
    if "Authorization" in headers:
        headers["Authorization"] = masked_authorization(headers["Authorization"])
    log_line(f"===== {name} 实际接口调用开始 =====")
    log_line(f"{name} 请求方法: {prepared.method}")
    log_line(f"{name} 请求地址: {prepared.url}")
    log_line(f"{name} 请求头: {json.dumps(headers, ensure_ascii=False)}")
    if file_path is not None:
        log_line(f"{name} 上传文件路径: {file_path}")
        log_line(f"{name} 上传文件名: {file_path.name}")
        log_line(f"{name} 上传文件大小: {file_path.stat().st_size} bytes")
    if prepared.body and isinstance(prepared.body, str):
        log_line(f"{name} 请求体: {prepared.body}")


def upload_file(session: requests.Session, authorization: str, file_path: Path) -> str:
    mime_type = mimetypes.guess_type(str(file_path))[0]
    if not mime_type:
        mime_type = "application/octet-stream"

    headers = dict(UPLOAD_HEADERS)
    headers["Authorization"] = authorization
    with file_path.open("rb") as file_handle:
        request = requests.Request(
            method="POST",
            url=UPLOAD_URL,
            headers=headers,
            files={"file": (file_path.name, file_handle, mime_type)},
        )
        prepared = session.prepare_request(request)
        log_prepared_request("上传文件", prepared, file_path=file_path)
        log_line(f"上传文件 curl摘要:\n{build_curl_preview(prepared, file_path=file_path)}")
        response = session.send(prepared, timeout=TIMEOUT_SECONDS)

    log_line(f"上传文件 响应状态码: {response.status_code}")
    log_line(f"上传文件 响应内容: {response.text}")
    log_line("===== 上传文件 实际接口调用结束 =====")
    response.raise_for_status()

    response_json = response.json()
    assert str(response_json["code"]) in SUCCESS_CODES
    assert isinstance(response_json["data"], str)
    return response_json["data"]


def create_task(session: requests.Session, authorization: str, file_path: Path, file_id: str):
    payload = deepcopy(CREATE_PAYLOAD_TEMPLATE)
    payload["file_name"] = file_path.name
    payload["file_id"] = file_id

    headers = dict(CREATE_HEADERS)
    headers["Authorization"] = authorization
    request = requests.Request(
        method="POST",
        url=CREATE_URL,
        headers=headers,
        json=payload,
    )
    prepared = session.prepare_request(request)
    log_prepared_request("创建任务", prepared)
    log_line(f"创建任务 请求体: {json.dumps(payload, ensure_ascii=False)}")
    log_line(f"创建任务 curl摘要:\n{build_curl_preview(prepared, payload=payload)}")
    response = session.send(prepared, timeout=TIMEOUT_SECONDS)
    log_line(f"创建任务 响应状态码: {response.status_code}")
    log_line(f"创建任务 响应内容: {response.text}")
    log_line("===== 创建任务 实际接口调用结束 =====")
    response.raise_for_status()

    response_json = response.json()
    assert str(response_json["code"]) in SUCCESS_CODES
    return response_json


def test_create_audit_tasks():
    assert ENV_JSON_PATH.exists(), f"env.json 不存在: {ENV_JSON_PATH}"
    assert FILE_DIRECTORY.exists(), f"上传目录不存在: {FILE_DIRECTORY}"
    assert FILE_DIRECTORY.is_dir(), f"上传目录不可读: {FILE_DIRECTORY}"

    target_files = list_target_files()
    assert target_files, f"目录下没有可上传文件: {FILE_DIRECTORY}"

    logger.remove()
    logger.add(sys.stdout, level="INFO", format="{message}")
    logger.add(LOG_PATH, level="INFO", format="{message}", encoding="utf-8", mode="w")
    authorization = load_authorization()
    session = requests.Session()

    log_line(f"上传目录: {FILE_DIRECTORY}")
    log_line(f"日志路径: {LOG_PATH}")
    log_line(f"待处理文件数: {len(target_files)}")

    for index, file_path in enumerate(target_files, start=1):
        log_line(f"[{index}/{len(target_files)}] 处理文件: {file_path.name}")
        file_id = upload_file(session, authorization, file_path)
        log_line(f"上传成功，file_id: {file_id}")
        create_response = create_task(session, authorization, file_path, file_id)
        log_line(f"创建任务成功，响应: {json.dumps(create_response, ensure_ascii=False)}")


if __name__ == "__main__":
    raise SystemExit(pytest.main(["-s", __file__]))
