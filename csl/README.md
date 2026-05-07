# CSL 对话全路径接口自动化

## 项目概览
该目录用于执行 CSL 销售助手完整对话路径接口自动化，覆盖：
- 固定路径问答
- 关注点分支处理
- LLM 辅助的固定关注点语义匹配
- 拜访计划异步轮询
- 拜访计划断言
- JSON 与 Markdown 统一结果输出

当前已完成模型化重构：
- service 层主链路返回模型对象，不再以 `dict` 作为主要返回形态
- reporter 层统一负责模型对象序列化
- 测试数据、预期断言字段、冒烟 case 都从 YAML 读取

## 当前架构
当前整体分层为：

`tests -> services -> clients -> requests`

同时新增了：
- `models/`：业务模型层
- `validators/`：断言与规则层
- `reporters/`：输出与报告层

## 目录结构与职责

### 入口层
- `run_csl_full_paths.py`
  整个框架的运行入口。仅负责加载配置、读取用例、筛选执行范围并调用统一运行服务。
- `README.md`
  当前项目说明文档。
- `完整对话路径测试路径_按Excel重整.md`
  业务路径梳理文档，不参与脚本执行。

### 配置层
- `config/config.yaml`
  非敏感默认配置，放接口路径、超时、日志等级、默认回答等。
- `config/dev.env`
  开发/测试环境覆盖配置，当前已统一为 `/api/...` 路径模板。
- `config/prod.env`
  生产环境模板配置。
- `config/llm_config.yaml`
  LLM 通用配置，供关注点语义匹配使用。
- `config/app_config.py`
  统一配置加载器，负责读取 `config/config.yaml`、`config/llm_config.yaml`、`config/.env`、`config/dev.env` 并组装成 `AppConfig`。
- `config/constants.py`
  常量定义，包括断言模式、默认值、关注点分支枚举等。
- `config/settings.py`
  项目内路径常量定义，集中管理配置、数据、日志、输出路径。

### 数据层
- `data/csl_full_paths.yaml`
  主测试数据文件，包含 29 条 case、预期断言字段、关注点策略、冒烟用例 `smoke_case_ids`。

### 模型层
- `models/case_model.py`
  case 相关模型，包含：
  - `FocusStrategy`
  - `FocusDecision`
  - `CaseConfig`
  - `CaseCollection`
- `models/result_model.py`
  执行过程与执行结果模型，包含：
  - `ConversationStep`
  - `ConversationExecutionResult`
  - `CaseExecutionResult`
  - `ExecutionSummary`

说明：
- `AppConfig` 继续留在 `config/app_config.py`
- `AssertionResult` 继续留在 `validators/assertions.py`

### 客户端层
- `clients/chat_client.py`
  对话接口客户端，封装 `start / message / stop / history` 的 HTTP 请求、请求头、重试和响应标准化。
- `clients/llm_client.py`
  LLM 客户端，用于调用外部模型匹配固定关注点对应的选项。

### 服务层
- `services/case_loader.py`
  负责将 YAML 用例转换成 `CaseCollection`、`CaseConfig` 等模型对象。
- `services/conversation_service.py`
  负责执行单条 case 的完整对话流程，返回：
  - `ConversationExecutionResult`
  - `CaseExecutionResult`
- `services/focus_service.py`
  关注点处理服务。当前核心结构为 `FocusService`，负责：
  - 识别关注点问题
  - 解析选项
  - 匹配固定关注点选项
  - 生成 `F1/F2_OPTION/F2_CUSTOM/F3` 分支回答
  - 记录 `FocusDecision`
- `services/focus_match_service.py`
  固定关注点语义匹配服务，负责组织提示词并调用 LLM。
- `services/plan_polling_service.py`
  拜访计划轮询服务。负责基于 `session_id` 异步轮询 `history/{session_id}`，并原地更新 `CaseExecutionResult`。
- `services/run_service.py`
  通用运行编排服务。负责串联 case 执行、异步轮询拜访计划以及统一输出刷新。
- `services/validation_service.py`
  兼容转发层，当前转发到 `validators/` 下的断言实现，避免调用点一次性全部改动。

### 断言层
- `validators/assertions.py`
  通用文本断言工具，负责：
  - 文本归一化
  - 文本相等断言
  - 文本包含断言
  - 文本相似度断言
  - 多行列表逐条断言
- `validators/assertion_models.py`
  断言模型定义，包含：
  - `ValidationCheck`
  - `ValidationResult`
- `validators/assertion_builder.py`
  断言构建器，负责根据字段值和匹配模式生成断言对象。
- `validators/field_extractors.py`
  拜访计划字段提取器，负责从 `final_data / detail_data / visit_plan` 中抽取断言所需字段。
- `validators/validation_rules.py`
  断言规则层，负责：
  - 识别实际关注点分支
  - 构建关注点断言规则
  - 构建全量字段断言规则
- `validators/validation_service.py`
  断言服务入口，返回 `ValidationResult`。

### 报告层
- `reporters/json_reporter.py`
  JSON 结果输出器，负责：
  - 初始化结果文件
  - 过滤待执行 case
  - 将模型对象统一序列化为 JSON
- `reporters/markdown_reporter.py`
  Markdown 执行记录输出器，负责：
  - 生成执行明细
  - 生成失败汇总
  - 基于模型对象输出 Markdown

### 工具层
- `utils/logger.py`
  日志初始化工具，统一配置 `loguru` 输出到控制台和文件。
- `utils/yaml_loader.py`
  YAML 通用加载工具，统一读取 YAML 文件。

### 脚本层
- `scripts/revalidate_results.py`
  基于已有 `output` 结果文件重新计算断言，不重新调接口。当前流程为：
  1. 从 JSON 读取历史结果
  2. 反序列化为 `CaseExecutionResult`
  3. 重算 `ValidationResult`
  4. 重新输出 JSON 和 Markdown

### 测试层
- `pytest.ini`
  pytest 配置，指定测试目录。
- `conftest.py`
  pytest 公共初始化，主要把项目根目录加入 `sys.path`。
- `tests/test_app_config.py`
  测试配置加载逻辑。
- `tests/test_common_assertions.py`
  测试通用断言工具。
- `tests/test_conversation_service.py`
  测试对话流程，重点覆盖 `can_stop` 控制规则。
- `tests/test_focus_strategy.py`
  测试关注点分支选择逻辑。
- `tests/test_llm_api.py`
  测试 LLM API 配置和调用链。
- `tests/test_validation.py`
  测试断言构建、模型序列化、结果汇总、冒烟筛选等逻辑。
- `tests/data/*.yaml`
  各类单测依赖的样例数据。

### 输出层
- `logs/app.log`
  运行日志文件。
- `output/csl_full_path_results.json`
  统一 JSON 结果文件，包含汇总和每条 case 的执行结果。
- `output/csl_full_path_execution_record.md`
  统一 Markdown 执行记录，包含每步问题、测试回答、关注点执行记录、拜访计划与失败汇总。

## 执行流程
当前脚本的真实执行链路为：

1. 调用 `start` 创建会话
2. 读取首个系统问题
3. 按 case 预设答案或关注点策略持续调用 `message`
4. 若命中关注点问题，交给 `FocusService` 生成回答
5. 当最后一轮 `message` 返回 `is_complete=true` 时结束对话
6. 仅当最后一轮 `message` 返回 `can_stop=true` 时调用 `stop`
7. 基于 `session_id` 异步轮询 `history/{session_id}`
8. 拿到最终拜访计划后执行断言，得到 `ValidationResult`
9. reporter 层统一序列化输出 JSON 和 Markdown

## 关注点分支规则
当前支持的关注点分支包括：
- `F1`
  命中固定关注点，对应固定表格关注点内容
- `F2_OPTION`
  选择其他选项，关注点相关内容按动态生成处理
- `F2_CUSTOM`
  自定义输入关注点，关注点相关内容按动态生成处理
- `F3`
  输入无效内容，如“不知道”，回落到固定关注点内容

固定关注点匹配优先级为：
1. `fixed_option_label`
2. LLM 语义匹配
3. 本地相似度兜底匹配

## 断言体系

### 当前支持的断言模式
- `exact`
  文本归一化后完全相等
- `contains`
  文本归一化后包含，适用于段落、摘要、较长说明文本
- `list_exact`
  多行列表逐条归一化后完全相等，适用于文献标题列表
- `not_empty`
  字段非空，适用于动态生成内容

### 当前校验字段
- `doctor_type`
- `doctor_grade`
- `trans_info`
- `support_info`
- `comm_literature_titles`
- `comm_literature_summaries`
- `focus_title`
- `focus_content`
- `focus_literature_titles`
- `focus_literature_summaries`
- `recommended_materials`
- `visit_plan_digest.department`
- `visit_plan_digest.rank`
- `visit_plan_digest.type`
- `visit_plan_digest.grade`
- `focus_branch`

### 当前字段断言规则
- `doctor_type` / `doctor_grade` / `digest.*`
  使用 `exact`
- `trans_info`
  使用 `exact`
- `support_info`
  使用 `contains`
- `comm_literature_titles` / `focus_literature_titles`
  使用 `list_exact`
- `comm_literature_summaries` / `focus_literature_summaries`
  使用 `contains`
- `recommended_materials`
  使用 `contains`
- `focus_title` / `focus_content`
  - F1、F3、无关注点策略时：使用固定预期值，按 `contains` 断言
  - F2_OPTION、F2_CUSTOM 时：按 `not_empty` 断言
- `focus_branch`
  仅当 case 存在关注点策略时校验，使用 `exact`

## 运行方式

### 全量执行
```bash
cd /Users/layla.zhang/workspace/nullht-test/csl
python3 run_csl_full_paths.py
```

### 只做配置与数据校验
```bash
python3 run_csl_full_paths.py --dry-run
```

### 只执行冒烟用例
```bash
python3 run_csl_full_paths.py --smoke
```

### 只执行单条 case
```bash
python3 run_csl_full_paths.py --case-id P017
```

## 环境切换
- 脚本优先读取 `config/.env`
- 若 `config/.env` 不存在，则读取 `config/dev.env`
- 你也可以先手动 `source` 指定环境文件，再执行脚本

例如生产环境：
```bash
cd /Users/layla.zhang/workspace/nullht-test/csl

set -a
source /Users/layla.zhang/workspace/nullht-test/csl/config/prod.env
set +a

python3 run_csl_full_paths.py --smoke
```

## 输出文件
- `output/csl_full_path_results.json`
  保存统一 JSON 结果，适合后续程序化处理或重跑断言
- `output/csl_full_path_execution_record.md`
  保存统一 Markdown 执行记录，适合人工查看和问题排查
- `logs/app.log`
  保存运行日志

## 备注
- 所有测试路径与断言字段均来自 `data/csl_full_paths.yaml`
- `P028`、`P029` 为原始 AI 问询路径
- 冒烟用例从 `smoke_case_ids` 读取
- `services/validation_service.py` 目前仍是兼容转发层
- 若需要基于已有结果重跑断言，可使用 `scripts/revalidate_results.py`
