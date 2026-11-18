# 关机后仍能更新：云端部署交接

运行记录可在 GitHub Actions 查看。需确认采集和 Pages 发布均成功，才能认定云端更新已接通。

## 各部分由谁运行

| 工作 | 执行者 | 用户电脑关机时 |
| --- | --- | --- |
| 采集已登记的 RSS、官方新闻目录、Crossref 元数据 | GitHub Actions 内的 Python 脚本 | 云端配置生效后可继续 |
| 去重、专题关键词分类、生成网站及发布 | 脚本和 GitHub Pages 发布任务 | 云端配置生效后可继续 |
| 新条目的中文译名、内容摘要、复杂 CFP 期限提取 | 可选 WorkBuddy 或其他 agent | 本机 WorkBuddy 不运行；新增条目先发布原始元数据 |
| 阅读网站、搜索、引注格式化 | 托管站点及访问者浏览器 | 不受站主电脑开关机影响 |

此版云端流程不调用 Codex、OpenAI 或其他收费模型 API，不装第三方 Python 依赖，不修改电脑 DNS、代理或证书。已有中文标题仅在原始标题不变时保留；新条目保留原文。摘要不会由脚本猜测生成。活动日期需要本次可核对的原文证据，不能从旧快照重新推断。

## 用户的一次性操作

1. 安装并连接 GitHub 集成，或在 GitHub 官网登录。不要将账户密码或个人访问令牌发到聊天中。
2. 选择专门用于本平台的新仓库。GitHub Free 下公开仓库的标准云端 runner 免费，公开 Pages 也可用；这会公开项目源码和已公开的资讯索引，需先由所有者确认。若不愿公开源码，可另选私有仓库及托管路径，需重新核对免费计算和发布额度。
3. 只导入 `artifacts/LexAtlas-云端部署源码.zip` 中的文件。该包不含本机数据库、采集正文缓存、原 Git 历史、Sites 身份或凭证。不要上传完整交接包。
4. 在仓库 Settings → Pages 选择 GitHub Actions 发布源。将默认分支设为 main（任务文件需在默认分支）。
5. 首次推送工作流及源码时 GitHub 会启动 `LexAtlas cloud metadata`。也可以从 Actions 页面手动运行。查看采集结果、部署结果和线上来源状态。任务每天北京时间约 09:17 和 18:17 运行，平台调度可能延迟。

## 关机与故障时的表现

云端任务配置生效后，不依赖用户电脑；用户关机不会使网站下线。采集失败的来源保留已公开资料和失败状态，其他正常来源仍可更新；构建或发布失败时，线上继续显示上一版。页面生成时间不能当作每一个来源的最后成功采集时间。

云端机器每次从当前仓库的 `dist/data.json` 恢复已公开历史，再增量采集。仓库里只提交更新后的公开数据快照，完整网站作为发布产物交给 Pages。SQLite、缓存、日志和 WorkBuddy 队列留在运行时。任务使用 GitHub 自动提供的临时令牌，发布组件固定到 GitHub 官方 Actions 的指定提交。

免费不等于永不需要处理：GitHub 可延迟或丢弃繁忙时段任务；公开仓库长时间无活动时可能停用 schedule。任务失败、账户变更、信源改版仍可能需要维护。不要使用自建服务器、较大付费 runner 或购买额度，本项目未开通这些服务。

## 国内分享入口是另一项工作

GitHub 云端采集解决电脑关机时的更新，不保证 github.io 或当前 chatgpt.site 在中国大陆直连。腾讯 EdgeOne Makers 默认域名在中国大陆有预览链接时限，匿名项目还有限时认领及访问限制，不能冒充永久公开入口。本项目没有创建临时项目或申请不明免费域名。

零费用且不使用第三方中转的长期大陆入口，仍需正规托管与适合的域名/机构空间，并进行大陆网络实测。未得到该资源前，不承诺所有地区直连；当前 Sites 地址仍可用于已有网络条件下的评阅。

## 官方规则

- [GitHub Actions 计费](https://docs.github.com/en/actions/concepts/billing-and-usage)
- [定时任务规则及限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub Pages 工作流](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [EdgeOne Makers 域名规则](https://pages.edgeone.ai/zh/document/domain-overview)
