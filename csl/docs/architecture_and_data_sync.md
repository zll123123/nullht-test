# CSL 项目架构与测试数据同步说明

## 1. 文档范围

本文档说明当前 CSL 接口自动化项目的：

- 目录分层和核心职责。
- 测试数据从 Excel 同步到 YAML 的规则。
- 对话执行、拜访计划生成、断言和报告输出链路。
- 关键业务路径及关注点分支规则。

## 2. 项目架构

```text
csl/
├── config/                 配置、环境变量和运行路径
├── data/                   YAML 测试数据
├── clients/                HTTP 和 LLM 请求封装
├── services/               业务流程编排
├── models/                 case、执行结果和校验结果模型
├── validators/             字段提取、规则和断言
├── reporters/              JSON、Markdown、Qase 输出
├── utils/                  YAML 加载、日志、接口计时
├── tests/                  pytest 单元测试
├── prompts/                LLM 评估和审核提示词
├── docs/                   项目设计和专项说明
├── run_csl_full_paths.py   命令行入口
└── pytest.ini              pytest 配置
```

调用关系：

```text
命令行入口
  -> run_service
    -> conversation_service
      -> chat_client
        -> requests.Session
    -> plan_polling_service
      -> chat_client.history
    -> validation_service
    -> reporters
```

### 2.1 配置层

`config/` 负责普通配置、敏感配置、环境切换和路径管理：

- `config/config.yaml`：普通运行配置，例如 `active_env`、超时、重试次数和轮询间隔。
- `config/dev.env`、`config/uat.env`、`config/prod.env`：环境地址和敏感鉴权信息。
- `config/llm_config.yaml`：通用 LLM 请求配置。
- `config/app_config.py`：将 YAML 和环境变量加载为 `AppConfig`。
- `config/settings.py`：项目根目录、数据文件、日志和输出目录等路径常量。

环境切换只由 `config.yaml` 的 `active_env` 控制，实际环境地址从对应的 env 文件读取。

### 2.2 客户端层

`clients/` 只负责请求格式、请求头、超时、响应解析和 HTTP 异常：

- `chat_client.py`：封装 `start`、`message`、`stop`、`history` 接口。
- `llm_client.py`：封装通用 LLM 请求。

测试数据和业务服务不直接调用 `requests`。

### 2.3 服务层

- `case_loader.py`：从 YAML 构建 `CaseCollection`、`CaseConfig` 和关注点策略。
- `conversation_service.py`：执行单条 case 的多轮问答并生成对话结果模型。
- `focus_service.py`：识别关注点问题并决定 F1、F2 或 F3 的回答策略。
- `run_service.py`：编排多条 case、异步轮询、重试和输出。
- `plan_polling_service.py`：通过 `history` 获取最终拜访计划并完成断言。
- `plan_review_runner.py`：在正式产物生成后执行本地 LLM 审核，不改变接口断言结果。

### 2.4 校验和输出层

`validators/` 负责把接口返回转换为字段校验结果；`reporters/` 负责把模型序列化成 JSON、Markdown 和 Qase Report。业务服务不直接拼接报告文本。

## 3. Excel 到 YAML 的数据关系

### 3.1 唯一关联方式

YAML 中的 `expected.source_excel_row` 是 Excel 与 case 的唯一关联键：

```yaml
expected:
  source_excel_row: 47
```

脚本不得按 case 顺序、case 编号、科室文本或关注点文本推算 Excel 行号，也不得通过相邻行猜测业务值。

没有 `source_excel_row` 的 case 是原始 AI 问询等无固定表格行路径，数据同步时跳过并记录原因。

一个 Excel 行可以对应多个 YAML case。例如普通梯度路径和梯度未收集路径可能共用同一行，它们共享 Excel 固定预期字段，但 `answers` 和 `focus_strategy` 仍然独立维护。

### 3.2 Excel 字段映射

| YAML 预期字段 | Excel 列 | Excel 含义 |
|---|---:|---|
| `doctor_type` | M | 对应医生类型 |
| `doctor_grade` | P | 对应医生梯度 |
| `trans_info` | U | 传递信息 |
| `support_info` | V | 支持信息 |
| `comm_literature_titles` | W | 传递信息参考文献 |
| `comm_literature_summaries` | X | 传递信息研究简介及结果 |
| `focus_title` | Y | 临床医生可能的关注点标题 |
| `focus_content` | Z | 临床医生可能的关注点内容 |
| `focus_literature_titles` | AA | 关注点参考文献 |
| `focus_literature_summaries` | AB | 关注点研究简介及结果 |

医生类型取 Excel 的固定映射列 **M 列「对应医生类型」**，不从医生类型问题选项列推断。医生梯度优先取 P 列；当梯度问题没有收集到有效值时，业务路径通过传递信息回答反推梯度，对应表格中的传递信息映射值应使用 S 列。

### 3.3 合并单元格

如果目标单元格属于 Excel 合并区域，读取该区域左上角单元格的值；否则读取当前单元格值。不能使用整列向上查找替代合并单元格解析，否则可能把真正的空值误判为继承值。

### 3.4 值处理原则

- Excel 的 `-` 表示没有该项固定内容，写入 YAML 时转换为 `null`。
- 其他业务文本保留原文，只统一换行符。
- 不自动增删项目符号。
- 不修正文案、标点、错别字或文献编号。
- 文本归一化只用于差异展示，不用于生成新的业务值。

## 4. YAML 更新流程

后续工具建议放在 `tools/excel_to_yaml.py`，只负责数据同步，不参与接口测试执行。

### 4.1 预览

```bash
cd /Users/layla.zhang/workspace/nullht-test/csl
python3 -m tools.excel_to_yaml \
  --excel "/path/CSL销售手册-选项与映射值关系.xlsx" \
  --yaml data/csl_full_paths.yaml \
  --check-only
```

预览输出 case、Excel 行号、字段名、旧值和新值，不修改 YAML。

### 4.2 写入

```bash
python3 -m tools.excel_to_yaml \
  --excel "/path/CSL销售手册-选项与映射值关系.xlsx" \
  --yaml data/csl_full_paths.yaml \
  --write
```

写入流程：

1. 校验 Excel、YAML 和 `cases` 结构。
2. 读取 Excel 合并单元格值。
3. 按 `source_excel_row` 生成字段更新结果。
4. 在内存中完成全部更新。
5. 写入 YAML。
6. 重新加载 YAML，验证格式和 case 数量不变。

工具不删除 case、不重排 case、不修改 `answers`，也不修改原始 Excel。

## 5. 核心业务流程

### 5.1 第一阶段信息收集

1. 启动会话，获取首个问题。
2. 回答医生职称。
3. 回答目标科室问题 Q2：`请问您本次拜访的目标科室是？`。
4. 根据科室决定是否询问医生分级：
   - `医院管理层/药剂科`：不追问分级，拜访计划中的 `doctorInfo.level` 固定为 `M类客户`。
   - ICU、心脏外科、肝病等科室：继续询问医生分级。
5. 医生分级选项当前为 `P1客户`、`P2客户`、`P3客户`、`P4客户`、`未分级`。
6. 继续收集医生熟悉程度、产品使用比例、医生类型和医生梯度。

### 5.2 医生类型和梯度

医生类型使用 Excel 固定映射值，典型类型包括：

- 低蛋白使用者
- 白蛋白笃信者
- 合理用药管理者
- 品牌认知者

医生梯度优先由梯度问题回答决定。若梯度问题未收集到有效值，则系统提问传递信息问题，测试路径根据回答值反推对应梯度，并使用同一 Excel 行的固定传递信息、支持信息和关注点数据。

### 5.3 关注点分支

固定关注点来自 Excel 的 `Y/Z/AA/AB` 四列。

- `F1`：回答与固定关注点语义一致的系统选项，使用固定关注点字段断言。
- `F2_OPTION`：回答其他系统选项，关注点相关字段只做非空断言。
- `F2_CUSTOM`：手动输入额外关注点，关注点相关字段只做非空断言。
- `F3`：输入空字符串、“不知道”“不清楚”等无效内容，回落到该 case 的固定关注点并使用固定值断言。

F1 的选项位置不固定。执行时从当前问题的 A/B/C/D 选项中提取文本，再通过关注点匹配服务判断与固定关注点最接近的选项，不能把固定关注点预设为某个选项字母。

## 6. 对话、停止和拜访计划

### 6.1 对话记录

每轮记录：

- 系统问题。
- 测试回答。
- 接口返回中的必要状态信息。

完整接口原始响应保存在结构化 JSON 结果中，Markdown 只记录完整问答过程和汇总信息。

### 6.2 stop 规则

- 只有当前 `message` 返回 `can_stop=true` 时才允许调用 `stop`。
- `can_stop=true` 不代表必须立即调用 `stop`，可以继续收集更多信息。
- 记录首次出现 `can_stop=true` 的轮次。
- 如果实际调用 `stop` 失败，仅记录 `stop_error`，不阻断后续 `history` 获取。

### 6.3 异步拜访计划

1. 对话结束后先保存 `session_id`。
2. 继续执行下一条 case，不串行等待当前拜访计划。
3. 到达轮询时间后调用 `/chat/history/{session_id}`。
4. 获取 `visit_plan` 后写入对应 `CaseExecutionResult`。
5. 基于最终结果执行字段断言。

最终拜访计划的获取和断言以 history 接口返回为准。

## 7. 断言与审核边界

接口自动化断言由 `validators/` 完成，结果写入正式 JSON、Markdown 和 Qase Report。断言规则详见 [validation.md](/Users/layla.zhang/workspace/nullht-test/csl/docs/validation.md)。

拜访计划 LLM 审核属于本地辅助审核链路：所有 case 的对话和拜访计划产物完成后统一执行，结果单独写入 `output/plan_review_results.json`，不改变正式接口断言状态，也不写入 Qase 测试结果。

## 8. 执行入口和结果

统一入口为：

```bash
cd /Users/layla.zhang/workspace/nullht-test/csl
python3 run_csl_full_paths.py --smoke
```

常用参数：

```bash
python3 run_csl_full_paths.py --case-id P048
python3 run_csl_full_paths.py --case-id P017 P021 P030
python3 run_csl_full_paths.py --case-id P017,P021,P030
python3 run_csl_full_paths.py --dept ICU
python3 run_csl_full_paths.py --dept 心脏外科 --smoke
python3 run_csl_full_paths.py --first-visit
python3 run_csl_full_paths.py --dry-run
```

`--case-id` 支持空格或逗号分隔的多个 case，按传入顺序执行并自动去重；不存在的 case 会直接报错。

主要产物：

- `output/csl_full_path_results.json`：完整结构化执行结果、拜访计划和接口耗时。
- `output/csl_full_path_execution_record.md`：问答过程和本批次失败汇总。
- `output/qase-report/`：Qase Report 本地报告数据及 HTML 报告。
- `output/plan_review_results.json`：本地拜访计划审核结果。
- `logs/app.log`：运行日志。

每次运行前会清理上一批运行产物，不保留历史执行结果。
