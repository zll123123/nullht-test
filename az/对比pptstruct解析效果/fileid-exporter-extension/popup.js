const exportButton = document.getElementById('exportButton');
const copyButton = document.getElementById('copyButton');
const statusElement = document.getElementById('status');
const resultElement = document.getElementById('result');
const summaryElement = document.getElementById('summary');
const taskCountElement = document.getElementById('taskCount');
const successCountElement = document.getElementById('successCount');
const failedCountElement = document.getElementById('failedCount');
const fileCountElement = document.getElementById('fileCount');
const errorsElement = document.getElementById('errors');

const TASK_ID_PATTERN = /^20\d{2}AZ\d+$/;
const TOKEN_PREFIX = 'Bearer ';

/**
 * 更新状态文案。
 *
 * @param {string} message 提示文本。
 */
function setStatus(message) {
  statusElement.textContent = message;
}

/**
 * 获取当前激活标签页。
 *
 * @returns {Promise<chrome.tabs.Tab>} 当前标签页。
 */
async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tabs[0] || !tabs[0].id || !tabs[0].url) {
    throw new Error('未找到当前标签页');
  }
  return tabs[0];
}

/**
 * 在当前页面上下文内提取任务编号和 token。
 *
 * @param {number} tabId 标签页 ID。
 * @returns {Promise<{taskIds: string[], token: string}>} 页面数据。
 */
async function collectPageData(tabId) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    world: 'MAIN',
    func: () => {
      const taskIdPattern = /^20\d{2}AZ\d+$/;
      const tokenPrefix = 'Bearer ';

      function extractBearerToken(value) {
        if (!value) {
          return '';
        }
        const directText = String(value).trim();
        if (directText.startsWith(tokenPrefix)) {
          return directText;
        }
        const directJwt = directText.match(/eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+/);
        if (directJwt) {
          return `${tokenPrefix}${directJwt[0]}`;
        }
        try {
          const parsed = JSON.parse(directText);
          return findTokenInObject(parsed);
        } catch (_error) {
          return '';
        }
      }

      function findTokenInObject(value) {
        if (!value) {
          return '';
        }
        if (typeof value === 'string') {
          return extractBearerToken(value);
        }
        if (Array.isArray(value)) {
          for (const item of value) {
            const token = findTokenInObject(item);
            if (token) {
              return token;
            }
          }
          return '';
        }
        if (typeof value === 'object') {
          for (const [key, item] of Object.entries(value)) {
            if (/token|authorization|auth/i.test(key)) {
              const token = findTokenInObject(item);
              if (token) {
                return token;
              }
            }
          }
        }
        return '';
      }

      function findTokenFromStorage(storage) {
        for (let index = 0; index < storage.length; index += 1) {
          const key = storage.key(index);
          if (!key) {
            continue;
          }
          const token = extractBearerToken(storage.getItem(key));
          if (token) {
            return token;
          }
        }
        return '';
      }

      const taskIds = Array.from(document.querySelectorAll('td'))
        .map((element) => (element.textContent || '').trim())
        .filter((text) => taskIdPattern.test(text));

      const token = findTokenFromStorage(window.localStorage) || findTokenFromStorage(window.sessionStorage);

      return {
        taskIds: [...new Set(taskIds)],
        token,
      };
    },
  });

  return result || { taskIds: [], token: '' };
}

/**
 * 渲染结果。
 *
 * @param {Array<any>} rows 导出结果。
 */
function renderRows(rows) {
  const successRows = rows.filter((row) => row.ok && row.fileId);
  const failedRows = rows.filter((row) => !row.ok || !row.fileId);
  const fileIds = [...new Set(successRows.map((row) => row.fileId).filter(Boolean))];

  summaryElement.hidden = false;
  taskCountElement.textContent = `任务 ${rows.length}`;
  successCountElement.textContent = `成功 ${successRows.length}`;
  failedCountElement.textContent = `失败 ${failedRows.length}`;
  fileCountElement.textContent = `fileId ${fileIds.length}`;

  resultElement.value = fileIds.join('\n');
  copyButton.disabled = fileIds.length === 0;

  if (failedRows.length > 0) {
    errorsElement.hidden = false;
    errorsElement.textContent = failedRows
      .map((row) => `${row.taskId || '未知任务'}：${row.errorMessage || '未返回 fileId'}`)
      .join('\n');
  } else {
    errorsElement.hidden = true;
    errorsElement.textContent = '';
  }
}

/**
 * 处理导出按钮点击。
 */
async function handleExportClick() {
  exportButton.disabled = true;
  copyButton.disabled = true;
  setStatus('正在读取当前页面...');
  summaryElement.hidden = true;
  errorsElement.hidden = true;
  errorsElement.textContent = '';
  resultElement.value = '';

  try {
    const tab = await getActiveTab();
    if (!tab.url.includes('/file-audit-list')) {
      throw new Error('请先切换到文件审核列表页面');
    }

    const { taskIds, token } = await collectPageData(tab.id);
    if (!taskIds.length) {
      throw new Error('当前页面没有识别到任务编号，请先点击查询');
    }
    if (!token || !token.startsWith(TOKEN_PREFIX) || !TASK_ID_PATTERN.test(taskIds[0])) {
      throw new Error('未读取到页面认证 Token，请确认当前页面已登录');
    }

    setStatus(`已识别 ${taskIds.length} 个任务，正在请求详情...`);
    const response = await chrome.runtime.sendMessage({
      type: 'EXPORT_FILE_IDS',
      payload: { token, taskIds },
    });

    if (!response?.ok) {
      throw new Error(response?.errorMessage || '导出失败');
    }

    renderRows(response.data.rows || []);
    setStatus(`导出完成，共处理 ${response.data.rows.length} 个任务`);
  } catch (error) {
    setStatus(error instanceof Error ? error.message : '导出失败');
  } finally {
    exportButton.disabled = false;
  }
}

/**
 * 复制结果文本。
 */
async function handleCopyClick() {
  if (!resultElement.value.trim()) {
    return;
  }
  try {
    await navigator.clipboard.writeText(resultElement.value);
    setStatus('已复制到剪贴板');
  } catch (_error) {
    resultElement.select();
    document.execCommand('copy');
    setStatus('已复制到剪贴板');
  }
}

exportButton.addEventListener('click', handleExportClick);
copyButton.addEventListener('click', handleCopyClick);
