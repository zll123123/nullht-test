const LIST_URL = 'https://dev-api-v3-az-mlr.nullht.com/api/audit/management/list';
const DETAIL_URL = 'https://dev-api-v3-az-mlr.nullht.com/api/audit/management/detail';
const MAX_CONCURRENCY = 4;
const SUCCESS_CODE = '00000';

/**
 * 构建请求头。
 *
 * @param {string} token 页面认证 token。
 * @returns {Record<string, string>} 请求头。
 */
function buildHeaders(token) {
  return {
    Accept: 'application/json, text/plain, */*',
    Authorization: token,
    'Content-Type': 'application/json',
    Origin: 'https://dev-v3-az-mlr.nullht.com',
    Referer: 'https://dev-v3-az-mlr.nullht.com/',
  };
}

/**
 * 发起 JSON 请求。
 *
 * @param {string} url 请求地址。
 * @param {Record<string, string>} headers 请求头。
 * @param {Record<string, unknown>} payload 请求体。
 * @returns {Promise<any>} 响应 JSON。
 */
async function postJson(url, headers, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status}`);
  }
  return response.json();
}

/**
 * 查询单个任务的列表记录。
 *
 * @param {string} token 页面认证 token。
 * @param {string} taskId 任务编号。
 * @returns {Promise<{id: string, audit_id: string, task_id: string, file_name: string}>} 任务记录。
 */
async function fetchListRow(token, taskId) {
  const headers = buildHeaders(token);
  const payload = {
    page_num: 1,
    page_size: 10,
    status: [],
    task_id: taskId,
    sorts: ['CREATED_TIME_DESC'],
  };
  const response = await postJson(LIST_URL, headers, payload);
  if (response.code !== SUCCESS_CODE) {
    throw new Error(`列表接口失败: ${response.msg || response.code}`);
  }
  const rows = (response.data && response.data.rows) || [];
  const row = rows[0];
  if (!row || !row.id) {
    throw new Error(`未查询到任务: ${taskId}`);
  }
  return row;
}

/**
 * 查询单个任务详情。
 *
 * @param {string} token 页面认证 token。
 * @param {string} rowId 列表行 ID。
 * @returns {Promise<any>} 详情数据。
 */
async function fetchDetail(token, rowId) {
  const headers = buildHeaders(token);
  const response = await postJson(DETAIL_URL, headers, { id: rowId });
  if (response.code !== SUCCESS_CODE) {
    throw new Error(`详情接口失败: ${response.msg || response.code}`);
  }
  return response.data || {};
}

/**
 * 处理单个任务编号。
 *
 * @param {string} token 页面认证 token。
 * @param {string} taskId 任务编号。
 * @returns {Promise<{taskId: string, auditId: string, fileName: string, fileId: string, pdfFileId: string}>} 导出结果。
 */
async function exportTask(token, taskId) {
  const listRow = await fetchListRow(token, taskId);
  const detail = await fetchDetail(token, listRow.id);
  return {
    taskId,
    auditId: listRow.audit_id || '',
    fileName: detail.file_name || listRow.file_name || '',
    fileId: detail.file_id || '',
    pdfFileId: detail.pdf_file_id || '',
  };
}

/**
 * 按并发数执行异步任务。
 *
 * @template T
 * @param {Array<() => Promise<T>>} runners 任务函数。
 * @param {number} concurrency 并发数。
 * @returns {Promise<T[]>} 执行结果。
 */
async function runWithConcurrency(runners, concurrency) {
  const results = new Array(runners.length);
  let nextIndex = 0;

  async function worker() {
    while (nextIndex < runners.length) {
      const current = nextIndex;
      nextIndex += 1;
      results[current] = await runners[current]();
    }
  }

  const workers = Array.from({ length: Math.min(concurrency, runners.length) }, () => worker());
  await Promise.all(workers);
  return results;
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== 'EXPORT_FILE_IDS') {
    return false;
  }

  (async () => {
    const { token, taskIds } = message.payload || {};
    if (!token) {
      throw new Error('未获取到认证 Token');
    }
    if (!Array.isArray(taskIds) || taskIds.length === 0) {
      throw new Error('当前表格没有可导出的任务编号');
    }

    const uniqueTaskIds = [...new Set(taskIds.map((item) => String(item).trim()).filter(Boolean))];
    const runners = uniqueTaskIds.map((taskId) => async () => {
      try {
        const result = await exportTask(token, taskId);
        return { ok: true, ...result };
      } catch (error) {
        return {
          ok: false,
          taskId,
          errorMessage: error instanceof Error ? error.message : '未知错误',
        };
      }
    });

    const rows = await runWithConcurrency(runners, MAX_CONCURRENCY);
    sendResponse({
      ok: true,
      data: {
        rows,
      },
    });
  })().catch((error) => {
    sendResponse({
      ok: false,
      errorMessage: error instanceof Error ? error.message : '未知错误',
    });
  });

  return true;
});
