# test-import Agent

执行 `group_chat_sentiment` 模块的导入集成测试。

## 运行步骤

### 1. 清除历史日志

```bash
rm -rf logs/group_chat_sentiment/*
```

### 2. 执行测试

```bash
uv run pytest src/test/test_import_upload.py -v -s
```

### 3. 检查执行结果

```bash
tail -100 $(ls -t logs/group_chat_sentiment/*.log | grep -v stderr | head -1)
```

- pytest 退出码 `0` 即通过
- 失败时查看对应 stderr 日志：`tail -50 logs/group_chat_sentiment/task_<UUID>_stderr.log`
