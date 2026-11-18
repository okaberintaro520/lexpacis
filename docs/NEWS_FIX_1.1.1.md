# 国际动态接入修复（2026-11-18）

原先栏目为空的原因：配置中没有 news 信源，数据库也没有 news 条目。此次登记联合国日内瓦新闻目录、新闻发布 RSS 和会议报道 RSS 三个入口，最短采集间隔为六小时；沿用现有更新任务，不另装软件。

首次接入核对了官方目录的六条报道标题、日期、链接，并提供中文译名；未读取完整报道正文，未生成实质摘要，也未把首次导入记作自动采集成功。目录：https://www.ungeneva.org/en/news-media/news 。官方 RSS 说明：https://www.ungeneva.org/en/news-media/rss 。

后续使用 `python scripts/pipeline.py update` 沿用现有 WorkBuddy 更新流程。只检查新闻入口可用 `collect --force --source un-geneva-news --source un-geneva-press --source un-geneva-meetings`，之后单独 build。更新任务尚未安装；新增配置不会自行创建定时任务。

网络连接继续检查公开地址、登记主机及重定向；不引入代理、隧道或远程控制。当前机器拒绝非公开目的地址时，保留失败记录，不绕过检查。栏目显示新闻入口数、采集异常，并区分未配置、采集未成功、暂无条目和筛选无结果。

报道来源标为官方机构新闻服务，不允许模型将其升级为案件原始材料。解析器不将页面级日期分配给所有报道，日期无法定位到独立条目时保留未知。
