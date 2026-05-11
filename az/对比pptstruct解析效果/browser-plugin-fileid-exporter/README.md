# AI预审 FileId 导出插件

## 功能

- 不再向业务页面常驻注入脚本或样式
- 通过 Chrome 工具栏插件 popup 触发导出
- 临时读取当前查询结果中的任务编号
- 调用列表接口和详情接口提取 `file_id`
- 在插件 popup 中展示结果
- 支持一键复制

## 加载方式

1. 打开 `chrome://extensions/`
2. 开启右上角“开发者模式”
3. 点击“加载已解压的扩展程序”
4. 选择当前目录：

`/Users/layla.zhang/workspace/nullht-test/az/对比pptstruct解析效果/browser-plugin-fileid-exporter`

## 使用方式

1. 打开 AI 预审站点并登录
2. 进入“文件审核列表”
3. 先按页面条件点击 `查询`
4. 点击 Chrome 工具栏中的插件图标
5. 在 popup 中点击 `导出当前页`
6. 点击 `一键复制`

## 当前实现说明

- 插件优先从页面的 `localStorage` 和 `sessionStorage` 中查找 Bearer Token
- 当前任务编号通过页面表格 `td` 文本识别
- 详情接口默认并发数为 4
- 若个别任务失败，会在 popup 底部显示失败原因

## 已知限制

- 如果页面后续改版，按钮定位和任务编号识别规则可能需要调整
- 如果站点认证 Token 不在浏览器存储里，需补充页面请求拦截方案
