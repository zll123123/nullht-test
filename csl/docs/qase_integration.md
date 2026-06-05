# Qase 对接文档

## 文档目的
本文档用于说明：

- 当前 `csl` 项目如何对接 `qase-report`
- 其他自动化项目如何快速复用这套方案
- 接入时推荐的最小字段、目录结构和落地步骤

本文档覆盖的是 `qase-report` 本地结果目录和 HTML 报告生成方案，不是直接调用 Qase TestOps 云端 API。

## 当前项目的对接目标
当前项目接入 Qase 的目标不是“管理测试用例”，而是：

- 将每轮自动化执行结果输出为 `qase-report` 可识别的目录结构
- 将每条 case 的执行状态、失败字段、失败原因、执行步骤、接口耗时写入结果文件
- 使用本地 `qase-report` 命令生成 HTML 报告，便于查看

## 当前项目的实现位置

### 核心文件
- [reporters/qase_reporter.py](/Users/layla.zhang/workspace/nullht-test/csl/reporters/qase_reporter.py)
  负责生成 `qase-report` 兼容的 `run.json` 和 `results/*.json`
- [services/run_service.py](/Users/layla.zhang/workspace/nullht-test/csl/services/run_service.py)
  负责在执行结束后调用 Qase 结果输出，并尝试生成 HTML 报告
- [run_csl_full_paths.py](/Users/layla.zhang/workspace/nullht-test/csl/run_csl_full_paths.py)
  负责初始化输出目录和 Qase 报告目录

### 输出目录
当前项目执行完成后，会生成：

- [output/qase-report/run.json](/Users/layla.zhang/workspace/nullht-test/csl/output/qase-report/run.json)
- `output/qase-report/results/*.json`
- [output/qase-report/report.html](/Users/layla.zhang/workspace/nullht-test/csl/output/qase-report/report.html)

目录结构如下：

```text
output/qase-report/
├── run.json
├── report.html
└── results/
    ├── P001.json
    ├── P002.json
    └── ...
```

## 当前项目写入了哪些信息

### 运行级别信息
`run.json` 中包含：

- 测试标题
- 环境名称
- 开始时间
- 结束时间
- 整轮执行时长
- 累计接口耗时
- 通过/失败/跳过统计
- 每条 case 的状态摘要

### 单条 case 级别信息
每条 `results/{case_id}.json` 中包含：

- `id`
- `title`
- `signature`
- `params`
  - `case_id`
  - `session_id`
  - `focus_strategy`
- `message`
  - 优先写断言失败摘要
  - 其次写失败原因或异常
- `fields`
  - `scenario`
  - `status`
  - `result_type`
  - `failure_reason`
  - `stop_error`
  - `first_can_stop_step_index`
  - `stop_called_step_index`
  - `department`
  - `failed_fields`
  - `failed_check_details`
- `steps`
  - 每轮系统提问
  - 每轮测试回答
  - 最终断言步骤
- `execution`
  - `status`
  - `start_time`
  - `end_time`
  - `duration`
  - `stacktrace`

### 当前失败明细的表达方式
当前项目为了让报告可读，额外输出了：

- `failed_fields`
  用逗号拼接的失败字段列表
- `failed_check_details`
  JSON 字符串，包含每个失败字段的：
  - 字段名
  - 预期值
  - 实际值
  - 匹配模式

这部分对接口自动化项目很重要，因为默认测试报告只告诉你“失败了”，但不会告诉你“具体哪个字段失败、预期和实际分别是什么”。

## 本项目的状态映射规则
当前 `csl` 项目把内部执行结果映射成 Qase 状态：

- `passed`
  断言通过
- `failed`
  脚本执行完成，但断言失败
- `broken`
  执行异常，例如请求超时、500、解析失败
- `skipped`
  当前用于 `PENDING_PLAN`

建议其他自动化项目也沿用这个规则，便于统一理解：

- 业务断言失败：`failed`
- 脚本/环境/接口异常：`broken`
- 主动跳过：`skipped`

## 当前项目如何查看 Qase 报告

### 方式一：直接打开本地 HTML
如果执行后已经生成：

- [output/qase-report/report.html](/Users/layla.zhang/workspace/nullht-test/csl/output/qase-report/report.html)

可以直接在浏览器中打开。

### 方式二：使用 qase-report 命令查看
如果本地已经安装 `qase-report`：

```bash
qase-report open /Users/layla.zhang/workspace/nullht-test/csl/output/qase-report
```

### 方式三：手动重新生成 HTML
如果已有 `run.json` 和 `results/*.json`，但还没有 HTML：

```bash
qase-report generate /Users/layla.zhang/workspace/nullht-test/csl/output/qase-report \
  -o /Users/layla.zhang/workspace/nullht-test/csl/output/qase-report/report.html
```

## 其他自动化项目如何快速接入

## 适用场景
适用于：

- `pytest + requests`
- 接口自动化
- UI 自动化
- AI 对话自动化
- 任意能在执行结束后拿到“case 结果对象”的项目

## 推荐的最小接入方案
如果你有一个新的自动化项目，建议只做 4 步：

### 第一步：统一单条 case 结果模型
至少保证每条 case 执行完成后，能拿到一个统一结果对象，建议包含：

- `case_id`
- `title` 或 `scenario`
- `status`
- `error`
- `failure_reason`
- `steps`
- `validation`
- `api_call_records`

其中：

- `steps` 用于生成测试步骤
- `validation` 用于提取失败字段和失败详情
- `api_call_records` 用于计算耗时

## 第二步：新增一个 Qase reporter
建议项目中新增一个独立文件，例如：

```text
reporters/qase_reporter.py
```

至少提供两个方法：

- `initialize_qase_report(output_dir: Path) -> Path`
- `save_qase_report(output_dir: Path, results: list[CaseResult]) -> Path`

职责边界建议如下：

- `initialize_qase_report`
  清空旧目录，创建 `qase-report/results`
- `save_qase_report`
  写 `run.json`
  写每条结果文件

## 第三步：在总运行入口结束时调用
建议在统一运行入口里调用，而不是散落在测试脚本里。

示例流程：

1. 开始执行前初始化 Qase 目录
2. 执行全部 case
3. 收集所有结果对象
4. 调用 `save_qase_report`
5. 如果本地安装了 `qase-report`，再尝试生成 HTML

## 第四步：优先输出失败字段明细
如果是接口自动化项目，最有价值的不是“是否失败”，而是：

- 哪个字段失败
- 预期值是什么
- 实际值是什么
- 用的是什么断言模式

所以建议最少补这两个字段：

- `failed_fields`
- `failed_check_details`

## 推荐的结果目录规范
建议所有项目统一为：

```text
output/qase-report/
├── run.json
└── results/
    ├── case_001.json
    ├── case_002.json
    └── ...
```

这样做有几个好处：

- 便于脚本统一查找
- 便于多个项目横向复用
- 便于本地调试和归档

## 推荐的最小字段清单

### run.json 建议至少包含
- `title`
- `environment`
- `execution.start_time`
- `execution.end_time`
- `execution.duration`
- `stats`
- `results`

### 单条结果建议至少包含
- `id`
- `title`
- `signature`
- `message`
- `fields`
- `steps`
- `execution.status`
- `execution.duration`

## 接口自动化项目的推荐 steps 结构
对接口自动化来说，不建议只写“调用接口”这类低信息步骤，建议写成：

### 请求步骤
- 请求接口名
- 关键入参
- 期望结果

### 断言步骤
- 校验哪些字段
- 哪些字段失败
- 每个失败项的预期和实际

如果像当前 `csl` 项目一样是多轮对话自动化，步骤建议直接写：

- 系统提问
- 测试回答
- 断言结果

这样业务人员也能直接看懂。

## 其他项目快速复用模板
一个新项目要快速复用时，建议直接照这个结构落：

```text
project/
├── reporters/
│   └── qase_reporter.py
├── models/
│   └── result_model.py
├── services/
│   └── run_service.py
└── output/
    └── qase-report/
```

最低改造成本通常是：

1. 把项目已有执行结果对象整理成统一模型
2. 复制 `qase_reporter.py` 结构
3. 替换字段映射
4. 在运行入口挂载保存逻辑

## 推荐的字段映射做法
不要在 reporter 里直接硬编码读取杂乱字典，建议先统一结果对象，再做映射。

推荐映射思路：

- 业务执行层负责收集结果
- 校验层负责产出失败项
- reporter 只负责序列化成 Qase 格式

这样其他项目迁移时，只需要改两处：

- 结果对象字段名
- 状态映射规则

## 常见坑

### 1. 只有 summary，没有单条结果文件
表现：

- 报告总数有值
- 左侧 testcase 为空

原因通常是：

- `results/*.json` 没有正确生成
- `id/signature/title` 缺失

### 2. 失败了但看不到原因
原因通常是：

- `message` 为空
- `stacktrace` 为空
- 没有输出 `failed_check_details`

建议：

- `message` 写失败摘要
- `stacktrace` 写完整失败详情

### 3. 耗时全是 0
原因通常是：

- 没有采集接口耗时
- `duration` 没有回填

建议：

- 在请求层统一记录 `elapsed_ms`
- reporter 用累计耗时生成 case duration

### 4. HTML 生成失败
原因通常是：

- 本地没有安装 `qase-report`
- 结果目录结构不完整

建议：

- 先检查 `run.json` 和 `results/*.json`
- 再单独执行 `qase-report generate`

### 5. case 状态映射不合理
常见错误是把所有失败都映射成 `failed`。

更合理的做法是：

- 断言失败：`failed`
- 执行异常：`broken`
- 未执行：`skipped`

## 对其他项目的落地建议

### 如果是普通接口自动化项目
建议优先输出：

- 接口名
- 请求参数摘要
- 响应摘要
- 失败字段
- 预期值
- 实际值

### 如果是 UI 自动化项目
建议优先输出：

- 页面步骤
- 操作动作
- 截图附件
- 定位失败原因

### 如果是 AI 对话自动化项目
建议优先输出：

- 系统问题
- 测试回答
- 会话 ID
- 关键断言字段
- 最终业务摘要

## 当前项目可复用的经验
当前 `csl` 项目这套接入最值得复用的部分有 3 点：

1. Qase 输出和业务执行解耦
   `run_service` 只负责调用，`qase_reporter` 只负责序列化

2. 失败字段可直接看
   不是只告诉你失败，而是把失败字段和预期/实际都带出来

3. 步骤面向业务可读
   对话问题和测试回答直接进入报告，不需要看原始日志

## 建议的快速接入清单
其他项目如果要快速接入，按下面执行即可：

1. 统一结果对象
2. 新增 `reporters/qase_reporter.py`
3. 定义状态映射
4. 定义 `run.json` 和 `results/*.json` 输出
5. 在总运行入口挂载保存逻辑
6. 本地安装 `qase-report`
7. 先验证 1 条通过、1 条失败、1 条异常 case
8. 确认报告中能看到失败字段和失败原因

## 补充说明
如果后续你希望把这套方案从“本地 HTML 报告”继续升级成：

- 对接 Qase TestOps 云端项目
- 自动上传执行结果
- 关联测试用例管理编号

那就需要再补一层：

- Qase 项目配置
- API Token
- TestOps 用例 ID 映射

这部分和当前 `qase-report` 本地报告方案是两套能力，不建议混在第一阶段一起做。
