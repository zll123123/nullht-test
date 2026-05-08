# CSL 对话全路径接口自动化

## 项目简介
该目录用于执行 CSL 销售助手的完整对话路径接口自动化测试，覆盖：
- 多轮对话执行
- 关注点分支处理
- 拜访计划异步生成与轮询
- 结果校验与统一输出

当前框架遵循分层设计，测试数据、配置、执行逻辑、断言逻辑、输出逻辑彼此分离，便于维护和扩展。

## 架构说明
整体调用链路为：

`tests -> services -> clients -> requests`

在此基础上补充了以下层次：
- `models/`
  统一承接 case、对话过程、执行结果、校验结果等模型对象。
- `validators/`
  负责字段提取、规则组装、断言执行。
- `reporters/`
  负责 JSON 和 Markdown 结果输出。

入口脚本保持轻量：
- `run_csl_full_paths.py`
  只负责加载配置、筛选用例并调用统一运行服务。

统一运行编排位于：
- `services/run_service.py`
  负责串联对话执行、拜访计划轮询、结果汇总与输出刷新。

## 目录结构
核心目录说明如下：

- `config/`
  配置层，包含 YAML 配置、环境变量文件、路径常量和配置加载器。
- `data/`
  测试数据层，当前主文件为 `csl_full_paths.yaml`。
- `clients/`
  HTTP 客户端与 LLM 客户端封装。
- `services/`
  业务服务层，负责 case 加载、对话执行、关注点处理、轮询编排等。
- `models/`
  业务模型层，避免 service 间裸 `dict` 传递。
- `validators/`
  校验规则与断言执行层。
- `reporters/`
  输出层，统一负责结果序列化。
- `utils/`
  通用工具层，例如日志和 YAML 加载。
- `tests/`
  pytest 单元测试与样例数据。
- `docs/`
  补充文档目录，放断言规则、校验说明等不适合放在 README 的细节文档。

## 技术实现说明
框架当前的核心实现方式如下：

### 1. 配置加载
- 默认配置放在 `config/config.yaml`
- 敏感信息和环境差异配置放在 `config/dev.env`、`config/prod.env` 或 `config/.env`
- 配置优先级为 `.env > YAML`
- 路径常量统一由 `config/settings.py` 管理

### 2. 用例驱动
- 所有测试 case 从 `data/csl_full_paths.yaml` 读取
- 用例加载后转换为模型对象，而不是在运行期直接操作原始字典
- 冒烟用例、关注点策略、预期结果都由 YAML 驱动

### 3. 对话执行
- 通过 `clients/chat_client.py` 统一调用 `start`、`message`、`stop`、`history`
- `services/conversation_service.py` 负责单条 case 的完整对话执行
- 仅当最后一轮返回 `can_stop=true` 时才调用 `stop`

### 4. 关注点处理
- `services/focus_service.py` 负责识别关注点问题并生成回答
- 固定关注点匹配优先使用显式选项，其次可调用 LLM 做语义匹配
- 匹配结果会记录到执行结果中，供后续排查和校验使用

### 5. 拜访计划异步获取
- 对话完成后先记录 `session_id`
- 由 `services/run_service.py` 串行发起对话，同时并行时机轮询历史会话结果
- `services/plan_polling_service.py` 负责按轮询窗口补全拜访计划

### 6. 模型化结果流转
- service 层主链路返回模型对象
- reporter 层作为统一序列化出口
- 这样可以降低 service 和输出格式之间的耦合

## 运行流程
一次完整执行的主流程如下：

1. 加载配置和测试数据
2. 选择待执行 case
3. 创建会话并进入多轮问答
4. 根据 case 或关注点策略自动回复
5. 对话结束后记录 `session_id`
6. 异步轮询拜访计划结果
7. 获取拜访计划后执行校验
8. 输出统一 JSON 结果和 Markdown 执行记录

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
默认行为：
- 优先读取 `config/.env`
- 若不存在，则回退到 `config/dev.env`

切换到生产环境时，可先加载 `config/prod.env`：

```bash
cd /Users/layla.zhang/workspace/nullht-test/csl

set -a
source /Users/layla.zhang/workspace/nullht-test/csl/config/prod.env
set +a

python3 run_csl_full_paths.py --smoke
```

如果开发和生产只有 `BASE_URL` 不同，建议直接在对应 env 文件中维护。

## 输出文件
- `output/csl_full_path_results.json`
  统一结果文件，适合程序化处理和结果复核。
- `output/csl_full_path_execution_record.md`
  统一执行记录，包含每轮问题、测试回答和失败汇总。
- `logs/app.log`
  运行日志文件。

## 重新校验已有结果
如果不想重新调用接口，只想基于已有输出重跑校验，可使用：

```bash
cd /Users/layla.zhang/workspace/nullht-test/csl
python3 scripts/revalidate_results.py
```

## 补充文档
- [校验与断言说明](./docs/validation.md)

