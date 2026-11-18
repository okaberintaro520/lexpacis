# 免费托管与自动发布

本项目不要求租服务器或购买模型 API。网站是普通静态文件，免费套餐以内可托管；具体额度、地域可达性与服务政策可能调整，不保证永久免费或所有地区访问速度。

## 本次可直接使用的结果

- `dist/index.html`：可直接离线打开的当前网站。
- `artifacts/lexatlas-web.zip`：只含公开网站文件，可上传静态托管。
- Codex Sites 的私有在线版本如果已部署，其结果记录在交付报告中。它用于查看本次成果；**不等于 WorkBuddy 已连接，也不作为长期运营的唯一发布入口。**

## 路线一：先手动上传，确认网站能用

在自己的免费 Cloudflare 账户中创建 Pages 的 Direct Upload 项目，上传 `dist/` 内容或静态 ZIP，使用平台提供的 pages.dev 地址，无需购买自定义域名。

上传后，修改 `config/site.json` 的 `base_url` 为实际网站地址，再 build 并重新上传。这样 RSS、站点地图与独立详情页的绝对地址才会指向正式网站。

这一方式只验证网站可访问，后续无人值守更新应继续配置路线二；不要把反复手工上传当作最终自动运营方案。

## 路线二：让 WorkBuddy 自动上传

首次需要完成一次自己的 Cloudflare 官方登录与 Pages 项目创建。无需向 Codex 或 WorkBuddy 对话提供密码。

1. 安装 Node.js 的受支持版本。
2. 在项目根目录安装发布工具：`npm install --save-dev wrangler@4`。这只安装开源工具，不购买 Cloudflare 服务；package.json 和锁文件应保存。
3. 执行 `npx wrangler login`，在官方网页完成一次授权。
4. 使用已创建的 Direct Upload Pages 项目；也可用 `npx wrangler pages project create <你的项目名>` 创建。选择免费计划和免费默认域名，不添加付费产品。
5. 在 site.json 将 deploy 改为：

```json
{
  "provider": "cloudflare",
  "cloudflare_project": "你的-pages-项目名",
  "github_repository": "",
  "github_branch": "gh-pages"
}
```

6. 将 base_url 改为实际 `https://项目名.pages.dev`。
7. 执行 `python scripts/pipeline.py build`，再执行 `python scripts/pipeline.py publish`。发布器使用本机已安装的 Wrangler，不会无人值守下载新工具。
8. 验证托管平台返回的实际地址，以及 `api/status.json` 的数据生成时间。通过后，WorkBuddy 定时任务即可沿用相同登录状态运行。

若登录失效，需要重新官方授权。没有实际登录时，不能宣称此路径已完成验证。

建议本地定时任务由同一 Windows 用户执行，以便使用同一工具配置和登录状态。不要把短期访问令牌写进项目源代码。纯静态发布不需要 Workers Functions、D1、R2 或付费模型网关。

## 免费额度与归档规模

当前默认导出最近 5000 条记录及其独立页面，历史资料继续保存在本机数据库。达到上限后，网页不是完整的本机历史库；界面状态中会列出总归档数与导出数。日后需要更大的公开档案，可分年导出或调整搜索索引结构。

Cloudflare 免费套餐对文件数量、单文件大小等有限制；公开文件总数与 release.json 可在打包时检查。不要通过提高默认上限无条件扩张。

## 更换托管平台

`dist/` 不依赖平台 SDK，也能放到 GitHub Pages 或其他静态主机。当前程序只实现 Cloudflare 自动发布器；其他平台需要另外配置发布命令，不能把接口字段的存在当作该发布器已实现。

## 官方资料

- [Cloudflare Pages Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/)
- [Cloudflare Pages 套餐限制](https://developers.cloudflare.com/pages/platform/limits/)

2026-11-18 查阅。首次账户连接是所有权与登录步骤，不是每天人工编辑或审核资讯。
