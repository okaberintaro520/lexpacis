# 法域前沿 · LexAtlas

面向高校师生与研究者的国际法资讯工作台。**初期开发完成后，日常运营可以完全脱离 Codex，由 WorkBuddy 和其他模型接手。**

当前为可运行的 1.1 版：静态网页 + Python 标准库采集/存储/发布程序 + 模型无关的文件交接协议。没有模型 API 客户端，不自动购买任何服务。

GitHub 云端已完成一次真实采集和公开发布。每天北京时间约 09:17、18:17 尝试刷新基础资料，运行不依赖站主电脑。WorkBuddy 可从现有源码接手，按需补充中文整理。见 [云端部署说明](docs/CLOUD_START_HERE.md) 与 [公开站点](https://okaberintaro520.github.io/lexpacis/)。

**1.1 更新**：新增浏览器本地引注转换器、36 种中英文期刊的 CFP/投稿导航、集中改名配置与安全网络检查。使用方法见 [新增功能说明](docs/FEATURES_1.1.md)。大陆及境外网络实测见 [访问方案](docs/REGIONAL_ACCESS.md)。

## 直接查看

GitHub 仓库保留公开数据快照及构建源码。首次从 GitHub 下载到空目录时，运行 `python scripts/cloud.py run --offline` 可从快照生成 `dist/index.html`。现有本机数据库的完整交接包请继续使用 `python scripts/pipeline.py build`。

双击 `dist/index.html`，无需安装依赖即可浏览当前资讯快照，包括搜索、筛选、收藏、专题及日历。离线打开时，原文链接仍需网络。也可双击 Windows 下的 `预览网站.cmd`，使用本地 HTTP 服务预览。

`dist/` 是网站发布目录；**不要把整个项目目录上传为网站根目录**，`runtime/` 包含数据库、原始信源证据和模型交接文件，应留在本机。

## 接手路径

1. 将整个项目解压到一个固定文件夹。
2. 用 WorkBuddy 打开该文件夹。
3. 把 [WORKBUDDY_START_HERE.md](WORKBUDDY_START_HERE.md) 的“给 WorkBuddy 的首条指令”发送给它。
4. 它先执行健康检查和本地完整试跑；随后按 [运营交接说明](docs/WORKBUDDY_HANDOFF.md) 配置免费托管与实际定时任务。

已经生成网站，不等于已经接通你的 WorkBuddy 账户。交付包不包含你的账号、模型额度或托管凭证，也没有代你创建任何 Codex 周期任务。

## 基本命令

在项目根目录运行，需要 Python 3.10 或更新版本。Windows 默认使用 `python`；若未加入 PATH，可用 `py -3` 替代。

```powershell
python scripts/pipeline.py doctor
python scripts/pipeline.py update
python scripts/pipeline.py prepare
python scripts/pipeline.py apply runtime/workbuddy/<批次>/output.json
python scripts/pipeline.py build
python scripts/pipeline.py publish
```

- `update`：采集到期信源 → 准备 AI 文件 → 构建元数据版网站。**不会自行调用模型，也不会自动上传网站。**
- `prepare`：生成或复用当前批次，路径保存在 `runtime/workbuddy/CURRENT.txt`。模型通过 WorkBuddy 读取并写回。
- `apply`：校验模型输出，逐条接受或拒绝；详见批次目录的 `validation.json`。
- `build`：统一生成首页、独立详情页、RSS、ICS、JSON 和站点地图。保留上一版本供本地回滚。
- `publish`：默认仅生成 `artifacts/lexatlas-web.zip`。配置 Cloudflare 后才会实际上传。
- `collect --force`：手动诊断时强制刷新，忽略最短间隔；不要作为常规定时配置。
- `reprocess`：用本机最近一次成功响应重新解析，适用于分类规则修改。不会伪造新的采集成功时间。
- `rollback`：恢复本地上一版网站；远程恢复需要再次运行 `publish`。
- `serve --open`：启动仅监听 `127.0.0.1:8765` 的本地预览。

首次试跑无需 Node.js。选择 Wrangler 自动发布时，才需要 Node.js 与一次性的免费 Cloudflare 登录配置。

## 目录

```text
config/       信源、站点、可见性、模型输出格式
web/          原始网页和样式
scripts/      采集、校验、构建、发布、交接打包
docs/         编辑规则、WorkBuddy 接手、托管、验证报告
tests/        数据与运营流程测试
dist/         可直接打开或上传的网站
runtime/      私有数据库、证据、日志、模型批次（不进 Git/网站）
```

## 目前的覆盖边界

启用的入口包括学术评论平台、ESIL 公告、WTO 官方新闻、国际法院新闻稿和三个期刊的 Crossref 元数据。部分已配置入口可能因网络或访问限制失败，状态以当前网站信源目录为准。候选入口不会被标作已经接通。

目前不提供全球论文全覆盖、付费全文检索、跨设备账户、实时法律问答或用户邮件推送。期刊索引中的书评不等于已接入专著目录。

AIHOT 的自动采集与整理思路是设计参考；本版为适配免费静态托管与跨工具交接而独立实现。没有直接复制其应用代码，参见 [参考与实现取舍](docs/ARCHITECTURE.md)。

## 验证

```powershell
python -m unittest discover -s tests -v
```

首轮真实信源接入、浏览器验证和仍需完成的账号配置，记录于 [验收报告](docs/ACCEPTANCE.md)。

程序代码采用 MIT 许可。来源标题、书目数据和机构材料的权利归原权利人；本项目许可不替代其各自规则。
