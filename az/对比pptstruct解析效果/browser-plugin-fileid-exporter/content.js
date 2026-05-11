let entryElements = null;
let isExporting = false;

/**
 * 延迟注入轻量右侧入口。
 */
function bootstrap() {
  window.setTimeout(() => {
    injectEntry();
  }, 1200);
}

/**
 * 注入右侧展开/收起入口。
 */
function injectEntry() {
  if (entryElements && document.body.contains(entryElements.root)) {
    return;
  }

  const root = document.createElement('div');
  root.className = 'fileid-exporter-entry';
  root.innerHTML = `
    <div class="fileid-exporter-panel">
      <div class="fileid-exporter-panel-inner">
        <div class="fileid-exporter-panel-title">FileId 导出</div>
        <div class="fileid-exporter-panel-desc">点击导出后，会读取当前查询结果中的任务并提取 file_id。</div>
        <div class="fileid-exporter-panel-actions">
          <button type="button" class="fileid-exporter-panel-button">开始导出</button>
          <button type="button" class="fileid-exporter-panel-secondary">收起</button>
        </div>
        <div class="fileid-exporter-status"></div>
      </div>
    </div>
    <button type="button" class="fileid-exporter-handle" aria-label="展开 FileId 导出">
      <span class="fileid-exporter-handle-text">导出\nfileId</span>
      <span class="fileid-exporter-handle-arrow">◀</span>
    </button>
  `;

  document.body.appendChild(root);

  entryElements = {
    root,
    panel: root.querySelector('.fileid-exporter-panel'),
    handle: root.querySelector('.fileid-exporter-handle'),
    exportButton: root.querySelector('.fileid-exporter-panel-button'),
    collapseButton: root.querySelector('.fileid-exporter-panel-secondary'),
    status: root.querySelector('.fileid-exporter-status'),
  };

  entryElements.handle.addEventListener('click', togglePanel);
  entryElements.collapseButton.addEventListener('click', closePanel);
  entryElements.exportButton.addEventListener('click', handleExportClick);
}

/**
 * 切换面板状态。
 */
function togglePanel() {
  if (!entryElements) {
    return;
  }
  const isOpen = entryElements.panel.classList.toggle('is-open');
  entryElements.handle.classList.toggle('is-open', isOpen);
}

/**
 * 收起面板。
 */
function closePanel() {
  if (!entryElements) {
    return;
  }
  entryElements.panel.classList.remove('is-open');
  entryElements.handle.classList.remove('is-open');
}

/**
 * 更新状态文案。
 *
 * @param {string} message 提示文本。
 */
function setStatus(message) {
  if (!entryElements) {
    return;
  }
  entryElements.status.textContent = message;
}

/**
 * 触发浏览器工具栏 popup。
 *
 * 受 Chrome 限制，页面脚本无法直接弹出 popup，这里改为直接复用同样的后台消息链路。
 */
async function handleExportClick() {
  if (isExporting || !entryElements) {
    return;
  }

  try {
    isExporting = true;
    entryElements.exportButton.disabled = true;
    entryElements.exportButton.textContent = '导出中...';
    setStatus('正在读取当前页面并请求详情...');

    const pageData = collectPageData();
    if (!pageData.taskIds.length) {
      throw new Error('当前页面没有识别到任务编号，请先点击查询');
    }
    if (!pageData.token) {
      throw new Error('未读取到页面认证 Token，请确认当前页面已登录');
    }

    const response = await chrome.runtime.sendMessage({
      type: 'EXPORT_FILE_IDS',
      payload: pageData,
    });
    if (!response?.ok) {
      throw new Error(response?.errorMessage || '导出失败');
    }

    const rows = response.data.rows || [];
    const fileIds = [...new Set(rows.filter((row) => row.ok && row.fileId).map((row) => row.fileId))];
    setStatus(`导出完成，共 ${fileIds.length} 个 fileId，已复制到剪贴板`);
    await copyText(fileIds.join('\n'));
  } catch (error) {
    setStatus(error instanceof Error ? error.message : '导出失败');
  } finally {
    isExporting = false;
    if (entryElements) {
      entryElements.exportButton.disabled = false;
      entryElements.exportButton.textContent = '开始导出';
    }
  }
}

/**
 * 从页面中收集任务编号和 token。
 *
 * @returns {{taskIds: string[], token: string}} 页面数据。
 */
function collectPageData() {
  const taskIds = Array.from(document.querySelectorAll('td'))
    .map((element) => (element.textContent || '').trim())
    .filter((text) => /^20\d{2}AZ\d+$/.test(text));

  const token = findTokenFromStorage(window.localStorage) || findTokenFromStorage(window.sessionStorage);
  return {
    taskIds: [...new Set(taskIds)],
    token,
  };
}

/**
 * 从 Storage 中查找认证 token。
 *
 * @param {Storage} storage 浏览器存储。
 * @returns {string} Bearer token。
 */
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

/**
 * 从任意文本中抽取 Bearer token。
 *
 * @param {string | null} value 原始文本。
 * @returns {string} Bearer token。
 */
function extractBearerToken(value) {
  if (!value) {
    return '';
  }
  const text = String(value).trim();
  if (text.startsWith('Bearer ')) {
    return text;
  }
  const matched = text.match(/eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+/);
  if (matched) {
    return `Bearer ${matched[0]}`;
  }
  try {
    const parsed = JSON.parse(text);
    return findTokenInObject(parsed);
  } catch (_error) {
    return '';
  }
}

/**
 * 递归查找 token。
 *
 * @param {unknown} value 任意对象。
 * @returns {string} Bearer token。
 */
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

/**
 * 复制文本到剪贴板。
 *
 * @param {string} text 待复制内容。
 */
async function copyText(text) {
  if (!text) {
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
  } catch (_error) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    textarea.remove();
  }
}

bootstrap();
