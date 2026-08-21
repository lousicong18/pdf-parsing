# Review Bug - backend

## 高严重性
- [x] #1 【高】classify.py:39 PageFeatures.columns 始终为 1（column_detection 传 tuple 不识别）| src/parser/classify.py:39 — ✅ 已修复：column_detection 支持 tuple/dict/object 三种输入
- [x] #6 【高】错误信封不合规：controller 传 detail=code，server handler code=detail | src/server.py:38 + controllers — ✅ 已修复：新增 AppError + handler 正确分离 detail/code

## 中严重性
- [x] #2 【中】pipeline.py:35 dispatch_page 未按设计做 columns 回填 | src/parser/pipeline.py:35 — ✅ 已修复：text/mixed 分支完成后覆盖 features.columns
- [x] #3 【中】vlm.py:85-87 空响应先记 success=True 再抛异常（X3 metrics 失真）| src/parser/vlm.py:85 — ✅ 已修复：先判空再 record success=False
- [x] #4 【中】vlm.py:76,85,95 一次逻辑调用重试成功产生两条 VlmCallMetric | src/parser/vlm.py:76 — ✅ 已修复：仅终态记一条
- [x] #5 【中】extract_table.py:27 table block bbox 硬编码整页，未取 Table.bbox | src/parser/extract_table.py:27 — ✅ 已修复：TableData 加 bbox 字段 + 取真实 Table.bbox
- [x] #7 【中】pdf_utils.py:27-28 get_page_count 打开 fitz 未 close，句柄泄漏 | src/utils/pdf_utils.py:27 — ✅ 已修复：try/finally close
- [x] #8 【中】task_service.py:54-55 + pipeline.py:23 classify_features 双算 | src/task_manager/task_service.py:54 — ✅ 已修复：classify_page 返回 (page_type, features)

## 低严重性
- [x] #9 【低】export_controller.py:18 参数名 format 覆盖 builtin | src/controller/export_controller.py:18 — ✅ 已修复：改名 fmt
- [x] #10 【低】runner.py:26,44,53,92 循环内重复 import | src/eval/runner.py:26 — ✅ 已修复：import 置顶
- [x] #11 【低】classify.py:61 scan 判定未联合 font_flags | src/parser/classify.py:61 — ✅ 已修复：纳入 font_flags 条件
- [x] #12 【低】pipeline.py:22 返回类型注解不精确 tuple[list, PageFeatures] | src/parser/pipeline.py:22 — ✅ 已修复：tuple[list[Block], PageFeatures]
