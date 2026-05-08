# 校验与断言说明

## 文档说明
本文档用于说明当前 CSL 自动化框架中的校验实现、断言模式和字段规则。

README 只保留架构和运行说明，断言细节统一放在本目录维护。

## 校验职责划分
- `validators/field_extractors.py`
  从接口返回中提取待校验字段。
- `validators/validation_rules.py`
  负责组装字段规则和关注点分支规则。
- `validators/assertion_builder.py`
  根据字段值和匹配模式构建校验项。
- `validators/assertions.py`
  负责基础文本断言能力。
- `validators/validation_service.py`
  作为校验服务入口，返回 `ValidationResult`。

## 当前支持的断言模式
- `exact`
  文本归一化后完全相等。
- `contains`
  文本归一化后包含。
- `list_exact`
  多行列表逐条归一化后完全相等。
- `not_empty`
  字段非空。

## 当前主要校验字段
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

## 关注点分支规则
当前支持以下分支：
- `F1`
  命中固定关注点，对应固定关注点断言。
- `F2_OPTION`
  选择其他选项，关注点相关字段按动态生成处理。
- `F2_CUSTOM`
  自定义输入关注点，关注点相关字段按动态生成处理。
- `F3`
  输入无效内容，回落到固定关注点断言。

固定关注点识别优先级：
1. `fixed_option_label`
2. LLM 语义匹配
3. 本地相似度兜底

## 字段断言规则
- `doctor_type`、`doctor_grade`、`visit_plan_digest.*`
  使用 `exact`
- `trans_info`
  使用 `exact`
- `support_info`
  使用 `contains`
- `comm_literature_titles`、`focus_literature_titles`
  使用 `list_exact`
- `comm_literature_summaries`、`focus_literature_summaries`
  使用 `contains`
- `recommended_materials`
  使用 `contains`
- `focus_title`、`focus_content`
  - `F1`、`F3`、无关注点策略时使用固定预期值
  - `F2_OPTION`、`F2_CUSTOM` 时使用 `not_empty`
- `focus_branch`
  仅在 case 存在关注点策略时校验

## 结果重算
若已有 `output/csl_full_path_results.json`，可通过 `scripts/revalidate_results.py` 重新执行断言，而不重新调用接口。
