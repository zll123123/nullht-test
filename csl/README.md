# CSL 对话全路径接口自动化

## 文件
- `run_csl_full_paths.py`：执行脚本
- `clients/chat_client.py`：接口请求客户端
- `services/case_loader.py`：测试数据加载
- `services/focus_service.py`：关注点分支处理
- `services/conversation_service.py`：完整对话执行
- `services/validation_service.py`：结果断言
- `utils/execution_record_writer.py`：执行记录导出工具
- `utils/result_writer.py`：结果输出工具
- `utils/yaml_loader.py`：统一 YAML 加载工具
- `utils/logger.py`：日志初始化工具
- `config.yaml`：非敏感配置
- `config/app_config.py`：统一配置加载器
- `data/csl_full_paths.yaml`：29 条测试路径及断言字段
- `.env` / `dev.env`：环境变量配置
- `output/csl_full_path_results.json`：执行结果输出
- `output/csl_full_path_execution_record.md`：完整执行记录
- `logs/app.log`：执行日志

## 运行方式
```bash
cd /Users/layla.zhang/workspace/nullht-test/csl
python3 run_csl_full_paths.py --dry-run
python3 run_csl_full_paths.py
python3 run_csl_full_paths.py --case-id P017
```

## 说明
- 脚本按 `start -> message -> stop` 的真实接口流程执行。
- 脚本优先读取 `.env`，若不存在则读取 `dev.env`。
- 所有测试路径与断言字段都从 `data/csl_full_paths.yaml` 读取，不再保留 Excel 读取链路。
- 当前分层为：`tests -> services -> clients -> requests`。
- 校验结果会写入 `output/csl_full_path_results.json` 的 `validation` 字段。
- 完整执行记录会写入 `output/csl_full_path_execution_record.md`，包括每一步系统提问、测试回答、系统响应、最终拜访计划、详情接口返回和断言结果。
- 当前校验字段包括：
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
  - `visit_plan_digest.department/rank/type/grade`
- 若需要额外调用“拜访计划详情接口”，可在 `.env` 中配置 `CSL_DETAIL_PATH`。
- `P028`、`P029` 已内置一条可达的历史追问分支答案。
