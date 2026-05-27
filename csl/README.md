# CSL 对话全路径接口自动化

## 项目说明
该目录用于执行 CSL 销售助手的完整对话路径接口自动化测试，覆盖：
- 多轮对话执行
- 关注点分支处理
- 拜访计划异步轮询
- 拜访计划断言校验
- 接口耗时记录与统一输出
- Qase Report 兼容结果导出

框架遵循分层设计，测试数据、配置、请求封装、业务编排、断言、输出彼此分离。

## 架构概览
核心调用链路：

`run_csl_full_paths.py -> services -> clients -> requests`

主要目录职责：
- `config/`：配置文件、环境变量文件、配置加载器、路径常量
- `data/`：YAML 测试数据
- `clients/`：HTTP 客户端、LLM 客户端
- `services/`：case 加载、对话执行、关注点处理、轮询编排
- `models/`：case、执行结果、校验结果、接口调用记录模型
- `validators/`：字段提取、规则组装、断言执行
- `reporters/`：JSON 与 Markdown 输出
- `utils/`：日志、YAML 加载、接口计时工具
- `tests/`：pytest 单测
- `docs/`：补充文档

关键文件：
- [run_csl_full_paths.py](/Users/layla.zhang/workspace/nullht-test/csl/run_csl_full_paths.py)
  运行入口，只负责加载配置、筛选 case、调用统一执行服务。
- [services/run_service.py](/Users/layla.zhang/workspace/nullht-test/csl/services/run_service.py)
  负责串联对话执行、拜访计划轮询、结果刷新。
- [services/conversation_service.py](/Users/layla.zhang/workspace/nullht-test/csl/services/conversation_service.py)
  负责单条 case 的完整对话流程。
- [services/plan_polling_service.py](/Users/layla.zhang/workspace/nullht-test/csl/services/plan_polling_service.py)
  负责拜访计划异步轮询与结果补全。
- [services/focus_service.py](/Users/layla.zhang/workspace/nullht-test/csl/services/focus_service.py)
  负责关注点问题识别与作答策略。
- [validators/validation_service.py](/Users/layla.zhang/workspace/nullht-test/csl/validators/validation_service.py)
  负责生成断言结果。

## 技术实现
### 配置加载
- 默认配置文件为 [config/config.yaml](/Users/layla.zhang/workspace/nullht-test/csl/config/config.yaml)
- LLM 配置文件为 [config/llm_config.yaml](/Users/layla.zhang/workspace/nullht-test/csl/config/llm_config.yaml)
- 当前激活环境由 `config.yaml` 中的 `active_env` 控制：
  - `dev`
  - `prod`
- 启动时会按 `active_env` 自动加载对应环境文件：
  - `dev` -> [config/dev.env](/Users/layla.zhang/workspace/nullht-test/csl/config/dev.env)
  - `prod` -> [config/prod.env](/Users/layla.zhang/workspace/nullht-test/csl/config/prod.env)
- 敏感信息与环境差异项放在对应的 `env` 文件中，普通运行配置放在 YAML 中

### 用例驱动
- 主数据文件为 [data/csl_full_paths.yaml](/Users/layla.zhang/workspace/nullht-test/csl/data/csl_full_paths.yaml)
- case 加载后转换为 `CaseConfig`
- 每条 case 当前包含：
  - `case_id`
  - `department`
  - `scenario`
  - `answers`
  - `expected`
  - `focus_strategy`

### 对话执行
- 对话接口统一由 [clients/chat_client.py](/Users/layla.zhang/workspace/nullht-test/csl/clients/chat_client.py) 调用
- 当前封装的接口包括：
  - `start`
  - `message`
  - `stop`
  - `history`
- 仅当当前轮消息返回 `can_stop=true` 时才允许调用 `stop`
- `stop` 失败只记录到 `stop_error`，不会阻断后续 `history` 拉取与断言
- 当前会记录：
  - 首次出现 `can_stop=true` 的轮次
  - 实际调用 `stop` 的轮次

### 关注点处理
- F1：选择固定关注点对应选项
- F2_OPTION：选择其他系统选项
- F2_CUSTOM：输入自定义关注点
- F3：输入无效关注点，回退到固定关注点路径
- 若开启 LLM，会优先用 LLM 做固定关注点选项匹配

### 异步轮询
- 每条对话完成后先记录 `session_id`
- 运行服务继续发起后续对话，不阻塞等待当前拜访计划生成
- 到达轮询窗口后再调用 `history` 接口获取拜访计划

### 失败重试
- case 级失败重试由 `case_retry_times` 控制
- 对应环境变量为：
  - `CSL_CASE_RETRY_TIMES`
- 只要 case 最终不是成功状态，就会按配置重试整条 case
- 成功状态定义为：
  - `status == DONE`
  - 且 `validation.passed == true`
- 重试只保留最终一次结果，不会把中间失败尝试重复写入正式报告

### 接口耗时记录
- 公共计时装饰器位于 [utils/api_timing.py](/Users/layla.zhang/workspace/nullht-test/csl/utils/api_timing.py)
- 当前会记录每次接口调用的：
  - `api_name`
  - `request_method`
  - `request_path`
  - `request_identifier`
  - `case_id`
  - `session_id`
  - `elapsed_ms`
  - `success`
  - `status_code`
  - `error`
- `start` 阶段优先以 `case_id` 作为关联标识，其余接口优先以 `session_id` 作为关联标识

## 运行方式
先进入目录：

```bash
cd /Users/layla.zhang/workspace/nullht-test/csl
```

### 全量执行
```bash
python3 run_csl_full_paths.py
```

### 仅校验配置与数据
```bash
python3 run_csl_full_paths.py --dry-run
```

### 执行单条 case
```bash
python3 run_csl_full_paths.py --case-id P017
```

### 执行冒烟用例
```bash
python3 run_csl_full_paths.py --smoke
```

当前默认冒烟集覆盖：
- ICU `≥50%` 低蛋白使用者路径
- ICU `＜50%` 品牌认知者路径
- 医院管理层/药剂科路径
- 肝病路径
- 外科梯度未收集路径
- 原始 AI 问询路径

### 按科室执行
```bash
python3 run_csl_full_paths.py --dept ICU
python3 run_csl_full_paths.py --dept 外科
python3 run_csl_full_paths.py --dept 肝病
python3 run_csl_full_paths.py --dept 医院管理层/药剂科
```

### 按科室执行冒烟用例
```bash
python3 run_csl_full_paths.py --dept ICU --smoke
```

### 指定随机种子
```bash
python3 run_csl_full_paths.py --seed 7
```

### 切换激活环境
直接修改 [config/config.yaml](/Users/layla.zhang/workspace/nullht-test/csl/config/config.yaml)：

```yaml
active_env: dev
```

切到生产环境时改为：

```yaml
active_env: prod
```

然后正常执行：

```bash
python3 run_csl_full_paths.py --smoke
```

科室说明：
- 对外统一使用 `医院管理层/药剂科`
- `药剂科`、`医院管理层`、`医院管理层/药剂科` 在代码中都会归一到同一个科室

参数限制：
- `--case-id` 与 `--smoke` 不能同时使用

## 输出结果
每次运行前会清空历史输出文件，再写入本次结果。

输出文件：
- [output/csl_full_path_results.json](/Users/layla.zhang/workspace/nullht-test/csl/output/csl_full_path_results.json)
  统一结构化结果，接口耗时记录位于每条 case 的 `api_call_records` 字段。
- [output/csl_full_path_execution_record.md](/Users/layla.zhang/workspace/nullht-test/csl/output/csl_full_path_execution_record.md)
  统一执行记录，每条 case 下会有“接口耗时记录”小节。
- [output/qase-report/run.json](/Users/layla.zhang/workspace/nullht-test/csl/output/qase-report/run.json)
  Qase Report 运行元数据。
- `output/qase-report/results/*.json`
  Qase Report 单条 case 结果。
- [output/qase-report/report.html](/Users/layla.zhang/workspace/nullht-test/csl/output/qase-report/report.html)
  每轮运行全部结束后自动生成一次的静态 HTML 报告。
- [logs/app.log](/Users/layla.zhang/workspace/nullht-test/csl/logs/app.log)
  运行日志。

## Qase Report 使用方式
当前框架会自动导出 Qase Report 兼容目录，并在整轮运行结束后自动生成一次 HTML 报告：

```bash
output/qase-report/
├── run.json
├── report.html
└── results/
    ├── P001.json
    ├── P002.json
    └── ...
```

如果你本地已安装 `qase-report`，可以直接查看：

```bash
qase-report open /Users/layla.zhang/workspace/nullht-test/csl/output/qase-report
```

如需手动重生成静态 HTML：

```bash
qase-report generate /Users/layla.zhang/workspace/nullht-test/csl/output/qase-report \
  -o /Users/layla.zhang/workspace/nullht-test/csl/output/qase-report/report.html
```

## 当前结果模型
case 级结果当前会收集：
- `case_id`
- `scenario`
- `expected`
- `focus_strategy`
- `focus_decisions`
- `session_id`
- `steps`
- `final_data`
- `visit_plan`
- `stop_data`
- `stop_error`
- `first_can_stop_step_index`
- `stop_called_step_index`
- `detail_data`
- `validation`
- `status`
- `result_type`
- `failure_reason`
- `error`
- `poll_attempts`
- `next_poll_at`
- `poll_deadline_at`
- `api_call_records`

## 补充文档
- [校验与断言说明](./docs/validation.md)
