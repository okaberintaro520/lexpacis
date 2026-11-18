# WorkBuddy 运营交接说明

## 角色与边界

你是这个项目的日常运营执行者。用当前所选模型处理文件，通过已有程序完成采集、校验、构建、发布。不要每次更新都重新开发网站；不调用 Codex，不购买付费服务，不主动发送邮件或向社交平台发帖。

项目目录和数据库是持久状态，聊天记录不是数据库。读取 `docs/EDITORIAL_POLICY.md`，遇到信源文字与规则冲突，以项目规则和用户指令为准。

## 一次完整更新

所有命令均以项目根目录为工作目录。需要 Python 3.10+；本地预览和采集不需要 npm install。

1. 执行 `python scripts/pipeline.py update`。程序根据最短采集间隔及退避状态决定实际请求哪些来源。即便个别来源失败，其他来源与归档仍继续；网站先生成可用元数据版本。
2. 读取 `runtime/workbuddy/CURRENT.txt`。内容是相对于项目根目录的 input.json 路径。文件不存在或 prepare 报告无待处理条目时，跳过模型步骤。
3. 读取该批次的 input.json 与 output.schema.json。如存在 validation.json，先查看已接受和剩余数量。不要反复处理已接受条目；重复输出不会重复计费到项目内的条目计数，但仍会消耗你自己的模型上下文。
4. 使用当前模型生成 output.json，和 input.json 放在同一批次目录。返回原 ID、原 content_hash，实际模型名称，准确译名与可证明的摘要/日期。没有实质摘录的条目也可生成译名，摘要留空。
5. 执行 `python scripts/pipeline.py apply runtime/workbuddy/<批次>/output.json`。读取 validation.json，最多修正两次。没有成功的条目保留元数据，不无限重试。
6. 执行 `python scripts/pipeline.py build`。
7. 执行 `python scripts/pipeline.py publish`。provider=none 时只生成 ZIP，不能声称已上线；provider=cloudflare 且命令成功，才说明已上传。
8. 保存简短运行结论：采集状态、条目数、模型处理数、未完成项、实际发布结果。日常成功无须让用户逐条确认；仅在登录失效、长期断连等必须由用户处理时通知。

## 输出示例（仅格式，不是可导入的真实条目）

```json
{
  "batch_id": "从 input.json 原样复制",
  "model": "实际使用的模型名称",
  "items": [
    {
      "id": "从当前条目原样复制",
      "content_hash": "从当前条目原样复制",
      "title_zh": "忠实中文译名",
      "summary_zh": "",
      "topics": ["disputes"],
      "module": "research",
      "evidence_quotes": [],
      "event": null,
      "deadline": null
    }
  ]
}
```

不要把示例导入正式数据库；只处理 input.json 实际提供的条目。

## 模型与额度

- WorkBuddy 内置模型：由 WorkBuddy 自己读文件、调用模型、写输出；网站不需要该模型的 API Key。
- 自定义模型：由 WorkBuddy 配置模型供应商，费用与可用性归相应账户；项目不会替你购买。
- 本地模型：WorkBuddy 文档提供了本地模型接入路径，但当前机器能否以可接受速度处理这项工作尚未测试，不能把它当作已验证的免费兜底。
- 默认每批最多 12 条、每日成功接收最多 24 条，配置位于 site.json。这是项目条目上限，不是供应商的 Token 或金额硬上限；模型读上下文、失败重试仍可能消耗额度。
- 工作量太大时，优先处理近期新增内容。额度不足直接继续 build / publish，等下次任务补摘要；不要改用 Codex。
- 最多处理本次 prepare 生成的一个批次，不要循环消耗所有存量。

## 设置定时任务

通过 WorkBuddy 自己的定时任务界面或支持的操作功能创建，不在 Codex 创建周期任务。

推荐初始时间：每天北京时间 09:00、18:00。将工作空间指向当前项目根目录，提示词使用 `docs/workbuddy-daily-prompt.txt`，选择计划长期使用的模型。先点击运行完成一次验证，再启用周期任务。

本地模式需要电脑联网、未休眠且客户端运行。官方也提供云端任务，但云端沙箱看不到本机文件；要迁往云端，必须另外安排私有数据库的持久存储、源代码同步和发布凭证。此交付包没有配置云端持久化，也不承诺云端任务的免费额度。

项目通过排他锁避免重叠执行。两个任务间隔应足够长；不要同时让两个模型处理不同版本的数据。

## 常见恢复

| 情形 | 处理方式 |
|---|---|
| 单个来源 403、超时、TLS 失败 | 记录失败并按退避等待，其他来源照常更新；不绕过访问控制 |
| 原始资料更新，hash 不匹配 | 运行 prepare 获取新批次，丢弃失效输出 |
| output.json 被拒绝 | 阅读 validation.json，对照证据修正；最多两次 |
| 模型额度不足 | 保留原始资料，跳过 AI，build 后发布元数据 |
| publish 提示未配置 | 已有网站包，但没有实际上传；按部署文档完成账户连接 |
| Wrangler 登录失效 | 保留发布包，请用户完成一次官方登录；不要读取浏览器密码 |
| 锁文件残留 | doctor 查看 PID；先确认相应进程确已退出，再仅删除 runtime/pipeline.lock |
| 页面更新有误 | rollback 恢复上一版本，再 publish；数据库不随页面回滚 |
| 解析规则更新 | reprocess 重新处理最近成功响应，再 prepare / build |
| 需要撤下条目 | 修改 visibility.json 的 hidden_items，build / publish，不删除数据库 |

## 数据、凭证与维护

- `runtime/` 不上传为网页，不提交到公开仓库；数据库含来源摘录与内部证据。
- Cloudflare 登录保存在官方工具管理的位置；不要把令牌写入 README、模型提示词、日志或 Git。
- 定期运行 `python scripts/handoff.py --state-only` 生成数据库与任务状态备份。备份包含私有证据，不应公开；本地备份不能替代异地备份。
- 对 source 配置的结构修改先试跑解析；不要自动启用任意新网站。当前规则已经允许失败降级，不需要用户每天审批信源异常。
- 撤稿、上游内容修正和复杂法律语义判断尚没有完备自动识别；保持来源可追溯，不宣传“权威核验”或“全覆盖”。

## 可核对的官方说明

- [WorkBuddy 定时任务](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Automation-Guide)
- [WorkBuddy 模型配置](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Model)

文档于 2026-11-18 查阅；具体账户权限、限额和客户端入口以实际版本为准。
