# 对比 pptStruct 解析效果

本文档说明当前目录下几个脚本的职责、输入输出，以及围绕当前主表的推荐执行顺序。

当前统一使用的主表是：

- `ppt原文抽取结果_获取pptstruct对比.xlsx`

这张表是逐文件、逐页的一行一页结构，当前表头为：

- `文件名称`
- `taskid`
- `detailId`
- `总页数`
- `页码`
- `提取方式`
- `ppt原文`
- `提取原文错误信息`
- `日志中的pptstruct`
- `llm错误类型`
- `llm严重程度`
- `llm判断依据`
- `人工审核结果`
- `报错审核点`
- `审核点错误摘要`

表里存在隐藏列，但当前脚本都按表头名定位，不按固定列序号定位，所以隐藏列不会导致处理失败。

## 脚本清单

当前目录主要使用这些脚本：

1. `export_ppt_source_texts_to_excel.py`
2. `fill_audit_excel_from_log.py`
3. `fill_audit_excel_from_api.py`
4. `review_pptstruct_semantics_to_excel.py`

## 一、export_ppt_source_texts_to_excel.py

### 作用

从指定目录扫描所有 `.ppt` / `.pptx`：

- 先获取每个文件总页数
- 再逐页提取 `ppt原文`
- 把结果写入独立 Excel

默认输出文件：

- `ppt原文抽取结果.xlsx`

### 提取策略

每页原文提取采用两层策略：

1. 优先读取 PPT 原生文本对象
   - 文本框
   - 表格文本
   - 组合对象中的子文本
2. 如果该页没有原生文本，则自动走 OCR 兜底
   - `soffice` 转 PDF
   - `pdftotext` 提取 PDF 文本层
   - `pdftoppm` 渲染页面
   - `tesseract` OCR

### 输出列

- `文件名称`
- `文件路径`
- `总页数`
- `页码`
- `提取方式`
- `ppt原文`
- `错误信息`

### 使用方式

```bash
cd /Users/layla.zhang/workspace/nullht-test/az/对比pptstruct解析效果
python3 export_ppt_source_texts_to_excel.py \
  --ppt-dir '/Users/layla.zhang/测试用例/测试材料/az/ppt解析验证case' \
  --output-path '/Users/layla.zhang/workspace/nullht-test/az/对比pptstruct解析效果/ppt原文抽取结果.xlsx'
```

### 适用场景

适合先独立抽取整批 PPT 的逐页原文，再把结果整理进后续审核主表。

## 二、fill_audit_excel_from_log.py

### 作用

根据主表中的：

- `taskid`
- `页码`

从当前目录下的 `app_*.out` 日志提取 `pptStruct`，回填到：

- `日志中的pptstruct`

### 支持两种模式

1. `error-page`
   - 默认模式
   - 只提取当前行 `页码` 对应的 `pptStruct`
2. `full-file`
   - 提取该文件对应的整份 `pptStruct`
   - 会把所有页按页码顺序组装成一个 JSON 后写入当前单元格

### 参数

- `--sheet-name`
- `--mode error-page|full-file`
- `--skip-non-empty`

`--skip-non-empty` 的含义：

- 如果 `日志中的pptstruct` 这一列已有内容，则跳过该行，不覆盖

### 使用方式

只提取错误页：

```bash
python3 fill_audit_excel_from_log.py --mode error-page
```

提取整份文件的所有页：

```bash
python3 fill_audit_excel_from_log.py --mode full-file
```

只补空白行：

```bash
python3 fill_audit_excel_from_log.py --mode full-file --skip-non-empty
```

### 日志提取逻辑

脚本会从日志建立两个映射：

- `taskid -> file_id`
- `file_id -> pptStruct JSON`

然后按模式写回主表。

## 三、fill_audit_excel_from_api.py

### 作用

根据主表中的 `文件名称` 调审核管理接口，获取该文件最新审核结果，并按页更新主表。

### 当前写回规则

脚本不会删除或重建整表，而是直接更新现有逐页行。

更新逻辑分两层：

1. 先按 `文件名称` 查询最新审核记录
2. 对同一文件名下的所有行，统一写相同的：
   - `taskid`
   - `detailId`
3. 再按 `文件名称 + 页码` 更新该页的：
   - `报错审核点`
   - `审核点错误摘要`

### 多个审核点 / 多个摘要的拼接规则

- 多个审核点：用 `/` 拼接
- 多个错误摘要：用 `&&` 拼接

### 输入依赖列

- `文件名称`
- `页码`
- `taskid`
- `detailId`
- `报错审核点`
- `审核点错误摘要`

### 使用方式

```bash
cd /Users/layla.zhang/workspace/nullht-test/az/对比pptstruct解析效果
python3 fill_audit_excel_from_api.py
```

指定工作表：

```bash
python3 fill_audit_excel_from_api.py --sheet-name Sheet1
```

### 说明

- 同一个 `文件名称` 下，`taskid` 和 `detailId` 会保持一致
- 某一页没有命中审核点时，该页的 `报错审核点` / `审核点错误摘要` 不会被硬写成报错文本
- 登录态失效时，需要更新脚本中的 `DEFAULT_COOKIE` 和 `DEFAULT_BEARER_TOKEN`

## 四、review_pptstruct_semantics_to_excel.py

### 作用

对主表中的每一页做比对，核心流程是：

1. 根据 `文件名称` 找到源 PPT
2. 根据 `页码` 提取该页 `ppt原文`
3. 读取 `日志中的pptstruct`
4. 做确定性文本差异对比
5. 再调用 LLM 生成错误类型、严重程度、判断依据和人工审核结果

### 输入列

- `文件名称`
- `页码`
- `日志中的pptstruct`

### 输出列

- `ppt原文`
- `diff`
- `llm错误类型`
- `llm严重程度`
- `llm判断依据`
- `人工审核结果`

### 提取原文策略

和 `export_ppt_source_texts_to_excel.py` 一致：

1. 先取原生文本
2. 取不到再 OCR

### 依赖

系统命令：

- `soffice`
- `pdftotext`
- `pdftoppm`
- `tesseract`

Python 依赖：

- `requests`
- `loguru`
- `openpyxl`
- `python-pptx`

### 使用方式

```bash
cd /Users/layla.zhang/workspace/nullht-test/az/对比pptstruct解析效果
python3 review_pptstruct_semantics_to_excel.py
```

## 五、推荐执行顺序

围绕当前主表，推荐顺序是：

1. 先准备逐页主表
   - 可由 `export_ppt_source_texts_to_excel.py` 先抽原文，再整理成主表
2. 再跑接口脚本
   - `python3 fill_audit_excel_from_api.py`
3. 再跑日志脚本
   - `python3 fill_audit_excel_from_log.py --mode error-page`
4. 最后跑语义审核脚本
   - `python3 review_pptstruct_semantics_to_excel.py`

如果你希望主表的 `日志中的pptstruct` 先写整份文件每一页内容，再做别的处理，可以把第 3 步换成：

```bash
python3 fill_audit_excel_from_log.py --mode full-file
```

## 六、常见问题

### 1. 隐藏列会不会导致脚本失败？

不会。当前脚本按表头名定位列，不按固定列序号定位。

### 2. 为什么同一个文件名下 `taskid` / `detailId` 应该一致？

因为 API 回填是先按文件名查最新审核记录，再把这条记录的 `taskid` / `detailId` 统一写给该文件名下所有页。

### 3. 为什么某些页的 `ppt原文` 会有 OCR 噪声？

因为这类页通常是整页图片、扫描页或文本被烘焙进图片，脚本只能走 OCR 兜底。

### 4. 为什么 `人工审核结果` 没有更新？

优先检查：

- `日志中的pptstruct` 是否为空
- `DEFAULT_PPT_DIR` 是否正确
- `DEFAULT_LLM_API_KEY` 是否可用
- LLM 接口是否返回了合法 JSON

## 七、补充说明

这些脚本都直接写同一个主表。批量执行前，建议先备份 Excel。
