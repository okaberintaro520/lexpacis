/* Portable static reader. All user data stays in this browser. No model calls. */
(() => {
  'use strict';
  const data = window.LEXATLAS_DATA;
  const page = document.getElementById('page-content');
  if (!data || !Array.isArray(data.items)) {
    page.textContent = '资讯数据未能加载。请确认 data.js 与网页位于同一目录，或重新运行 build。';
    return;
  }
  const sources = new Map(data.sources.map(s => [s.id, s]));
  const items = new Map(data.items.map(i => [i.id, i]));
  const moduleNames = Object.fromEntries(data.modules.map(m => [m.id, m.name]));
  const topicNames = Object.fromEntries(data.topics.map(t => [t.id, t.name]));
  const contentRoutes = ['latest', ...data.modules.map(m => m.id), 'saved', 'topic'];
  const knownRoutes = [...contentRoutes, 'topics', 'sources', 'about', 'cite', 'cfp'];
  let limit = 18;
  let route = 'latest';
  let params = new URLSearchParams();
  let selectedDay = '';
  let calendarMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
  let toastTimer;
  let searchTimer;
  let lastTrigger;
  let stored = [];
  try { stored = JSON.parse(localStorage.getItem('lexatlas.saved.v1') || '[]'); } catch { /* private browsing */ }
  const saved = new Set(Array.isArray(stored) ? stored.filter(id => typeof id === 'string') : []);
  const e = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const href = value => {
    try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? e(url.href) : '#'; } catch { return '#'; }
  };
  const sourceName = item => sources.get(item.source_id)?.name || item.source_id;
  const title = item => item.title_zh || item.title;
  const icon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h12v18l-6-4-6 4V3Z"/></svg>';
  const shortDate = (value, unknown = '日期未知') => {
    if (!value) return unknown;
    if (/^\d{4}$/.test(value)) return value + ' 年';
    if (/^\d{4}-\d{2}$/.test(value)) return value.replace('-', ' 年 ') + ' 月';
    return value.slice(0, 10).replaceAll('-', '.');
  };
  const localTime = value => value ? new Date(value).toLocaleString('zh-CN', {timeZone:data.site.timezone, hour12:false, year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'}) : '尚无记录';
  const chineseDate = date => date.toLocaleDateString('zh-CN', {year:'numeric', month:'long', day:'numeric', weekday:'long', timeZone:data.site.timezone});
  const isoDay = date => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
  const siteDay = () => new Intl.DateTimeFormat('sv-SE',{timeZone:data.site.timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const currentMonth = () => {
    const [year,month]=siteDay().split('-').map(Number);
    return new Date(year,month-1,1);
  };
  calendarMonth=currentMonth();
  const countTopic = id => data.items.filter(i => i.topics.includes(id)).length;
  const link = (name, values = {}) => '#/' + name + (Object.keys(values).length ? '?' + new URLSearchParams(values) : '');
  const sourceStatus = source => {
    if (source.status === 'ok' && source.success_at && (Date.now() - Date.parse(source.success_at)) > Math.max(source.poll_hours * 3, 48) * 3600000) return 'stale';
    return source.status;
  };
  const statusName = status => ({ok:'最近采集成功',error:'访问异常',candidate:'候选入口',unverified:'尚未验证',stale:'等待刷新',paused:'暂停采集'}[status] || '未验证');
  const empty = (heading, text, button = '') => `<div class="empty-state"><div class="empty-symbol">⌁</div><h3>${e(heading)}</h3><p>${e(text)}</p>${button}</div>`;
  const saveButton = item => `<button class="save-button ${saved.has(item.id) ? 'saved' : ''}" data-save="${e(item.id)}" aria-label="${saved.has(item.id) ? '取消收藏' : '收藏条目'}：${e(title(item))}" aria-pressed="${saved.has(item.id)}">${icon}</button>`;
  const dateChips = item => ['event','deadline'].map(key => item[key] ? `<span class="event-date-chip">${key === 'event' ? '活动' : '截止'} ${e(shortDate(item[key].date))}</span>` : '').join('');

  function toast(message) {
    const el = document.getElementById('toast');
    el.textContent = message; el.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => {el.hidden = true;}, 2800);
  }
  function persistSaved() {
    try { localStorage.setItem('lexatlas.saved.v1', JSON.stringify([...saved])); }
    catch { toast('浏览器限制了本地存储，本次收藏仅在当前页面有效。'); }
    document.getElementById('saved-count').textContent = saved.size;
  }
  function downloadJSON(name,value){
    const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
    const anchor=document.createElement('a');
    anchor.href=url;anchor.download=name;anchor.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  async function restoreSaved(file){
    if(!file)return;
    try{
      if(file.size>10_000_000)throw Error('收藏备份文件过大。');
      const backup=JSON.parse(await file.text());
      if(!Array.isArray(backup?.ids)||backup.ids.length>10000||!backup.ids.every(id=>typeof id==='string'&&/^[a-f0-9]{20}$/.test(id))){
        throw Error('请选择从「我的研究清单」导出的收藏 JSON。');
      }
      const before=saved.size;
      for(const id of backup.ids)saved.add(id);
      persistSaved();
      if(route==='saved')render();
      const unknown=backup.ids.filter(id=>!items.has(id)).length;
      toast(`新增 ${saved.size-before} 条收藏${unknown?`，其中备份有 ${unknown} 条已不在当前索引`:''}。`);
    }catch(error){toast(error instanceof SyntaxError?'无法读取收藏 JSON。':error.message);}
  }
  function navigate(name, values = {}, replace = false) {
    const hash = link(name, values);
    if (replace) { history.replaceState(null, '', hash); render(); }
    else if (location.hash === hash) render();
    else location.hash = hash;
  }
  function updateFilter(name, value) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value); else next.delete(name);
    const focus = document.activeElement?.id;
    const position = focus === 'search-input' ? document.activeElement.selectionStart : null;
    limit = 18;
    navigate(route, Object.fromEntries(next), true);
    if (focus) {
      const input = document.getElementById(focus);
      input?.focus({preventScroll:true});
      if (position !== null && input?.setSelectionRange) input.setSelectionRange(position, position);
    }
  }

  function heading(name, english, description, extra = '') {
    return `<div class="page-heading"><div><div class="eyebrow">${e(english)}</div><h1>${e(name)}</h1><p>${e(description)}</p></div>${extra || `<div class="update-note"><strong><span class="status-dot"></span>公开信源 · 批次采集</strong>数据生成 ${e(localTime(data.generated_at))}</div>`}</div>`;
  }
  function card(item) {
    const dates = dateChips(item);
    return `<article class="article-card" data-item="${e(item.id)}"><div><div class="article-kicker"><a class="type-label ${e(item.module)}" href="${link(item.module)}">${e(moduleNames[item.module])}</a><span>·</span><a href="${link('latest',{source:item.source_id})}">${e(sourceName(item))}</a><span>·</span><time datetime="${e(item.published_at || '')}">${e(shortDate(item.published_at))}</time></div><h3><button class="article-title" data-detail="${e(item.id)}">${e(title(item))}</button></h3>${item.title_zh ? `<p class="article-original">${e(item.title)}</p>` : ''}${item.summary_zh ? `<p class="article-description">${e(item.summary_zh)}</p>` : ''}${dates ? `<div class="event-date-row">${dates}</div>` : ''}<div class="article-bottom">${item.topics.slice(0,2).map(t => `<a class="pill" href="${link('topic',{id:t})}">${e(topicNames[t] || t)}</a>`).join('')}<span class="ai-label">${item.ai ? 'AI 整理 · '+e(item.evidence_basis) : '原始来源索引'}</span><button class="cite-this" data-cite="${e(item.id)}">生成引注</button><a class="read-link" href="${href(item.url)}" target="_blank" rel="noopener noreferrer">原文 ↗</a></div></div>${saveButton(item)}</article>`;
  }
  function filterItems() {
    const sourceFilter=params.get('source');
    const topicFilter=params.get('topic');
    const moduleFilter=params.get('module');
    const range=Number(params.get('range'));
    const tokens=(params.get('q')||'').toLowerCase().trim().split(/\s+/).filter(Boolean);
    const routeIsModule=Object.hasOwn(moduleNames,route);
    const filterNow=Date.now();
    let result = data.items.filter(item => {
      if (route === 'saved' && !saved.has(item.id)) return false;
      if (routeIsModule && item.module !== route) return false;
      if (route === 'topic' && params.get('id') && !item.topics.includes(params.get('id'))) return false;
      if (sourceFilter && item.source_id !== sourceFilter) return false;
      if (moduleFilter && item.module !== moduleFilter) return false;
      if (topicFilter && !item.topics.includes(topicFilter)) return false;
      if (range) {
        if (!item.published_at || !['day','instant'].includes(item.date_precision)) return false;
        const age = (filterNow - Date.parse(item.published_at)) / 86400000;
        if (!Number.isFinite(age) || age < -1 || age > range) return false;
      }
      if (tokens.length) {
        const text = [item.title, item.title_zh, item.summary_zh, item.doi, ...item.authors, sourceName(item), ...item.topics.map(t => topicNames[t])].join(' ').toLowerCase();
        if (!tokens.every(token => text.includes(token))) return false;
      }
      return true;
    });
    const sort = params.get('sort') || 'published';
    if (sort === 'discovered') result.sort((a,b) => b.discovered_at.localeCompare(a.discovered_at));
    else if (sort === 'oldest') result.sort((a,b) => (a.published_at || '9999').localeCompare(b.published_at || '9999'));
    else result.sort((a,b) => (b.published_at || '').localeCompare(a.published_at || '') || b.discovered_at.localeCompare(a.discovered_at));
    return result;
  }
  function options(entries, selected) {
    return entries.map(([value,label]) => `<option value="${e(value)}" ${selected === value ? 'selected' : ''}>${e(label)}</option>`).join('');
  }
  function toolbar() {
    return `<div class="toolbar"><label class="search-box"><span aria-hidden="true">⌕</span><input type="search" id="search-input" aria-label="搜索标题、作者、DOI 或关键词" placeholder="搜索标题、作者、DOI 或关键词…" value="${e(params.get('q') || '')}"><kbd>/</kbd></label><select class="filter-select" id="source-filter" aria-label="按信源筛选">${options([['','全部信源'],...data.sources.filter(s=>s.item_count).map(s=>[s.id,s.name])],params.get('source') || '')}</select><select class="filter-select" id="range-filter" aria-label="按发布日期筛选">${options([['','全部时间'],['7','最近 7 天'],['30','最近 30 天'],['90','最近 90 天']],params.get('range') || '')}</select><select class="filter-select" id="sort-filter" aria-label="排序">${options([['published','发表时间 ↓'],['discovered','收录时间 ↓'],['oldest','发表时间 ↑']],params.get('sort') || 'published')}</select></div>`;
  }
  function newsStatus() {
    const registered=data.sources.filter(s=>s.module==='news'&&s.enabled);
    const good=registered.filter(s=>sourceStatus(s)==='ok').length;
    const bad=registered.filter(s=>sourceStatus(s)==='error').length;
    return `<p class="saved-notice news-status">已接入 ${registered.length} 个新闻入口 · 最近采集成功 ${good} 个${bad?` · 访问异常 ${bad} 个`:''}。${good?'':'自动更新尚未验证成功；现有条目为首次核对的官方目录信息。'}报道保留机构来源，不等于裁判或法律认定。<a href="#/sources">查看信源状态 ↗</a></p>`;
  }
  function emptyStream(hasFilters) {
    if(route==='news'&&!hasFilters){
      const registered=data.sources.filter(s=>s.module==='news'&&s.enabled);
      if(!registered.length)return empty('新闻源尚未接入','该栏目尚未配置可用新闻源。','<a href="#/sources">查看信源目录 ↗</a>');
      if(registered.every(s=>sourceStatus(s)!=='ok'))return empty('新闻采集尚未成功','已配置新闻入口，但尚无可展示记录。请查看具体访问状态。','<a href="#/sources">查看信源状态 ↗</a>');
      return empty('暂无符合收录条件的报道','新闻源已接通，当前暂无可展示条目。');
    }
    return empty(route==='saved'&&!saved.size?'你的研究清单，从这里开始。':'暂时没有匹配的资料',route==='saved'&&!saved.size?'点击条目右侧的书签，即可保存研究线索。':'可以调整关键词、时间或信源，查看其他收录内容。','<a class="secondary-button" href="#/latest">浏览全部资讯 ↗</a>');
  }
  function stream(result) {
    const tabModules = route === 'latest' || route === 'topic' || route === 'saved';
    const tabs = tabModules ? [['','全部'],['research','文献'],['events','活动'],['cases','案件'],['commentary','评论']] : [['',moduleNames[route] || '全部']];
    const active = params.get('module') || '';
    const hasFilters = ['q','source','range','module','topic'].some(k=>params.get(k));
    return `<div class="stream"><div class="stream-top"><div class="stream-tabs" role="group" aria-label="资料类型">${tabs.map(([value,label])=>`<button data-module="${value}" class="${active===value?'selected':''}" aria-pressed="${active===value}">${e(label)}</button>`).join('')}</div><span class="stream-total">${result.length} 条资料</span></div>${toolbar()}<div class="filter-summary">${hasFilters?`<span class="active-filter">已应用筛选</span><button class="text-button" data-clear-filters>清除筛选 ×</button>`:'按原始发布日期排列，日期未知的资料置后。'}</div><div class="article-list">${result.length?result.slice(0,limit).map(card).join(''):emptyStream(hasFilters)}</div>${result.length>limit?`<button class="more-button" data-load-more>继续浏览 · 还有 ${result.length-limit} 条 ↓</button>`:''}</div>`;
  }
  function rail() {
    const events = data.items.filter(i=>i.module==='events'&&(i.deadline||i.event)).map(item=>({item,date:item.deadline?.date||item.event.date})).filter(i=>i.date>=siteDay()).sort((a,b)=>a.date.localeCompare(b.date)).slice(0,3);
    const recentEvents = data.items.filter(i=>i.module==='events').slice(0,2);
    const good = data.sources.filter(s=>sourceStatus(s)==='ok').length;
    return `<aside class="rail"><section class="rail-section"><div class="rail-heading"><h2>学术日历</h2><a href="#/events?view=calendar" aria-label="查看完整日历">↗</a></div><div class="rail-subtitle">ON THE AGENDA</div>${events.length?events.map(({item,date})=>`<div class="rail-event"><div class="rail-event-date">${date.slice(8,10)}<small>${Number(date.slice(5,7))} 月</small></div><div><button class="article-title rail-event-title" data-detail="${e(item.id)}">${e(title(item))}</button><small>${e(sourceName(item))}</small></div></div>`).join(''):`<div class="rail-empty">尚无已确认日期的活动。<br>活动公告可先收录；原文明确日期后再进入日历。</div>${recentEvents.map(item=>`<div class="rail-event"><div><button class="article-title rail-event-title" data-detail="${e(item.id)}">${e(title(item))}</button><small>公告 · ${e(sourceName(item))}</small></div></div>`).join('')}`}</section><section class="rail-section"><div class="rail-heading"><h2>信源观察</h2><a href="#/sources">查看全部 ↗</a></div><div class="rail-subtitle">FROM THE ORIGINAL SOURCE</div><div class="rail-metrics"><div><strong>${data.items.length}</strong><small>已收录资料</small></div><div><strong>${good}<span style="font-size:12px"> / ${data.sources.filter(s=>s.enabled).length}</span></strong><small>最近采集成功 / 已启用</small></div></div>${data.sources.filter(s=>s.enabled).slice(0,6).map(s=>`<a class="source-mini" href="#/sources"><span><span class="status-dot ${sourceStatus(s)==='error'?'error-dot':sourceStatus(s)!=='ok'?'neutral-dot':''}"></span>${e(s.name)}</span><small>${s.item_count} 条</small></a>`).join('')}<p class="rail-note">收录范围以已接通的信源为准。学术评论、索引和官方材料保留不同来源身份。</p></section><section class="rail-subscribe"><h3>把前沿带入研究日常。</h3><p>通过 RSS 订阅新增资料，<br>在自己的阅读器中持续追踪。</p><a href="feed.xml">获取订阅地址 ↗</a></section></aside>`;
  }
  function latestIntro() {
    const lead=data.items.find(i=>i.title_zh)||data.items.find(i=>i.module==='commentary')||data.items[0];
    return `<div class="intro-grid"><section class="lead-card"><div class="lead-kicker"><span></span> RESEARCH RADAR / 研究雷达</div><h2>${lead?`<button class="article-title" data-detail="${e(lead.id)}">${e(title(lead))}</button>`:'追踪国际法，<br>连接研究的下一步。'}</h2><div class="lead-meta">${lead?`<span class="pill">${e(moduleNames[lead.module])}</span><span>${e(sourceName(lead))}</span><span>${e(shortDate(lead.published_at))}</span><button class="lead-arrow" data-detail="${e(lead.id)}" aria-label="查看研究雷达详情">↗</button>`:'公开信源 / 学术线索 / 原始资料'}</div></section><section class="research-note"><div class="eyebrow">A STARTING POINT, ALWAYS.</div><h2>让资料相遇，<br>让研究向前。</h2><p>跨越期刊、机构与案件，<br>沿着专题发现新的连接。</p><a href="#/topics">探索研究专题 ↗</a><div class="compass" aria-hidden="true"><i></i></div></section></div><div class="section-line"><h2>循专题而行<span>RESEARCH PATHWAYS</span></h2><a href="#/topics">全部专题 ↗</a></div><div class="topic-strip">${data.topics.slice(0,3).map((topic,index)=>`<a class="topic-mini" href="${link('topic',{id:topic.id})}"><small>RESEARCH TOPIC / 0${index+1}</small><h3>${e(topic.name)}</h3><div class="topic-meta"><span>${countTopic(topic.id)} 条相关资料</span><span>↗</span></div></a>`).join('')}</div>`;
  }
  function topicDirectory() {
    return heading('循专题而行','RESEARCH PATHWAYS','把不同来源的文献、案件和评论放回同一研究脉络。')+`<div class="topic-grid">${data.topics.map((topic,index)=>`<a class="topic-large" href="${link('topic',{id:topic.id})}"><span class="topic-number">0${index+1} / RESEARCH TOPIC</span><h2>${e(topic.name)}</h2><div class="topic-meta"><span>${countTopic(topic.id)} 条相关资料</span><span>进入专题 ↗</span></div></a>`).join('')}</div>`;
  }
  function sourcesPage() {
    const enabled=data.sources.filter(s=>s.enabled).length;
    const good=data.sources.filter(s=>sourceStatus(s)==='ok').length;
    return heading('从原始来源出发','SOURCE DIRECTORY','查看接入范围、采集状态与机构身份。配置入口不等于已验证覆盖。')+`<div class="source-summary"><div class="metric-block"><strong>${enabled}</strong><span>已启用入口</span></div><div class="metric-block"><strong>${good}</strong><span>最近采集成功</span></div><div class="metric-block"><strong>${data.sources.filter(s=>sourceStatus(s)==='error').length}</strong><span>最近访问异常</span></div><div class="metric-block"><strong>${data.sources.filter(s=>!s.enabled).length}</strong><span>候选入口</span></div></div><div class="source-grid">${data.sources.map(s=>{const status=sourceStatus(s);return `<article class="source-card"><div class="source-card-top"><h3>${e(s.name)}</h3><span class="status-pill ${status}">${statusName(status)}</span></div><div class="organization">${e(s.organization)}</div><p>${e(s.scope)}</p><dl><dt>来源类型</dt><dd>${e({official_institution:'官方机构',official_news_service:'官方机构新闻服务',academic_commentary:'学术评论平台',academic_society:'学术团体',scholarly_index:'学术元数据索引'}[s.authority]||s.authority)}</dd><dt>采集方式</dt><dd>${e(s.kind.toUpperCase())} · ${s.poll_hours} 小时最短间隔</dd><dt>当前收录</dt><dd>${s.item_count} 条</dd><dt>最近尝试</dt><dd>${e(localTime(s.attempted_at))}</dd><dt>最近成功</dt><dd>${e(localTime(s.success_at))}</dd></dl>${s.error?`<p class="source-error">最近异常：${e(s.error)}</p>`:''}<a class="text-button" href="${href(s.homepage)}" target="_blank" rel="noopener noreferrer">访问原始网站 ↗</a></article>`}).join('')}</div>`;
  }
  function aboutPage() {
    const run=data.operations.last_run;
    const effective=data.operations.last_effective_run;
    const attempted=run&&(run.successes||run.failures);
    return heading('为研究，建立清晰的起点。','ABOUT '+data.site.english_name.toUpperCase(),'一份可追溯的国际法资讯索引，也是一张持续生长的研究地图。')+`<div class="about-layout"><article class="prose"><h2>在分散的信息之间，找到联系。</h2><p>${e(data.site.name)}面向高校师生与学术研究者，连接国际法文献、官方资料、案件公告、学术评论与活动信息。平台保留原始标题、出处、时间与资料类型，帮助读者发现线索并回到原始来源。</p><h3>我们收录什么</h3><p>当前版本采集已配置期刊的 Crossref 元数据、学术平台 RSS 和部分官方新闻目录。不同来源的覆盖范围、最新成功时间与访问异常，可在信源目录逐一查看。本平台不承诺全球论文、全部判例或所有机构文件的完整覆盖。</p><h3>原文、元数据与 AI 整理</h3><p>标题、作者、DOI 等书目信息按来源保留。没有足够文本依据的条目，仅提供索引。AI 整理会明确标注依据；程序检查字段、证据片段和日期，但这些检查不能保证语义完全正确，也不替代原文核查。学者观点、官方主张与裁判认定应分别理解。</p><h3>时间如何理解</h3><p>原始发布日期与平台首次发现时间分开保存。来源只提供年份或月份时，保留该精度；日期未知时明确标注。活动公告的发布日期不作为活动日期，截止日期不被虚构为某个时区的午夜。</p><h3>自动运营与可迁移</h3><p>网站阅读、搜索与筛选不调用模型。采集、去重、构建与发布由独立程序完成；翻译和摘要可交给 WorkBuddy 或其他工具。模型额度不足时，元数据仍可更新，AI 任务等待后续处理。</p><h3>你的研究清单</h3><p>收藏保存在当前浏览器，不上传服务器，不会跨设备自动同步。你可以在“我的收藏”导出当前收藏的 JSON 文件。清除浏览器数据可能丢失收藏。</p><h3>公开输出</h3><p><a href="feed.xml">RSS 订阅</a> · <a href="calendar.ics">学术日历 ICS</a> · <a href="api/items.json">资料 JSON</a> · <a href="api/sources.json">信源状态 JSON</a>。这些输出与网页使用同一份发布数据；撤下条目后需重新发布，已被他人下载的副本无法自动收回。</p><h3>设计参考</h3><p>自动采集、筛选与摘要流程参考 <a href="https://github.com/KKKKhazix/AIHOT" target="_blank" rel="noopener noreferrer">AIHOT</a> 的思路。本版本为便于免费静态托管与跨工具交接，使用独立实现，不依赖其运行服务。</p></article><aside class="status-panel"><h3>本次发布状态</h3><p><strong>页面数据生成</strong>${e(localTime(data.generated_at))}</p><p><strong>最近一次采集结束</strong>${e(localTime(run?.finished_at))}</p><p><strong>本轮采集</strong>${attempted?`成功 ${run.successes} · 异常 ${run.failures}`:run?'本轮没有到期信源':'尚未运行'}</p>${!attempted&&effective?`<p><strong>上次实际采集</strong>${e(localTime(effective.finished_at))} · 成功 ${effective.successes} · 异常 ${effective.failures}</p>`:''}<p><strong>归档资料总数</strong>${data.operations.total_archived}</p><p><strong>当前导出上限</strong>${data.operations.visible_in_export} 条</p><p><strong>定时运营</strong>${e(data.operations.scheduler_note)}</p><p><strong>模型依赖</strong>阅读不消耗额度；日常更新可完全脱离 Codex。</p><a class="secondary-button" href="#/sources">查看信源详情 ↗</a></aside></div>`;
  }
  function calendarView() {
    const start=new Date(calendarMonth.getFullYear(),calendarMonth.getMonth(),1);
    const offset=(start.getDay()+6)%7;
    const first=new Date(start); first.setDate(1-offset);
    const dated=[];
    filterItems().forEach(item=>['event','deadline'].forEach(key=>{if(item[key])dated.push({item,key,date:item[key].date});}));
    const dayMap=new Map(); dated.forEach(value=>{if(!dayMap.has(value.date))dayMap.set(value.date,[]);dayMap.get(value.date).push(value);});
    const today=siteDay();
    const cells=Array.from({length:42},(_,index)=>{const day=new Date(first);day.setDate(first.getDate()+index);const iso=isoDay(day);const entries=dayMap.get(iso)||[];return `<button class="calendar-day ${day.getMonth()!==start.getMonth()?'outside':''} ${iso===today?'today':''} ${iso===selectedDay?'selected':''}" data-day="${iso}" aria-label="${iso}，${entries.length} 项活动或截止日期"><span class="day-number">${day.getDate()}</span>${entries.length?`<span class="day-events">${entries.length} 项 ${entries.some(i=>i.key==='deadline')?'· 截止':''}</span>`:''}</button>`;}).join('');
    const selected=selectedDay?dated.filter(d=>d.date===selectedDay):dated.filter(d=>d.date.slice(0,7)===isoDay(start).slice(0,7));
    const unique=[...new Map(selected.map(d=>[d.item.id,d.item])).values()];
    return `${toolbar()}<div class="calendar-layout"><div><div class="calendar"><div class="calendar-top"><h2>${start.getFullYear()} 年 ${start.getMonth()+1} 月</h2><div class="calendar-controls"><button data-month="prev" aria-label="上个月">←</button><button data-month="today">本月</button><button data-month="next" aria-label="下个月">→</button></div></div><div class="calendar-grid">${['一','二','三','四','五','六','日'].map(d=>`<div class="calendar-weekday">周${d}</div>`).join('')}${cells}</div><div class="calendar-legend"><span>仅显示有明确原文日期的活动</span><a class="text-button" href="calendar.ics">订阅 ICS ↗</a></div></div>${!dated.length?`<div class="rail-empty" style="margin-top:15px">当前尚无已确认日期的活动。活动列表仍可浏览已收录公告；不会将公告发布日期填入日历。</div>`:''}</div><section class="calendar-list"><h3>${selectedDay?e(shortDate(selectedDay)):'本月安排'}</h3>${unique.length?unique.map(card).join(''):empty('留一点时间给研究。','所选日期暂无已确认的活动或截止安排。')}${selectedDay?'<button class="text-button" data-clear-day>查看本月全部</button>':''}</section></div>`;
  }
  function openDetail(id, trigger) {
    const item=items.get(id); if(!item)return;
    const source=sources.get(item.source_id);
    lastTrigger=trigger || document.activeElement;
    document.getElementById('detail-content').innerHTML=`<div class="eyebrow">${e(moduleNames[item.module])} / ${e(source.name)}</div><h2 class="detail-heading" id="detail-title">${e(title(item))}</h2>${item.title_zh?`<p class="detail-original">${e(item.title)}</p>`:''}<p class="basis-badge">${item.ai?'AI 自动整理 · 基于'+e(item.evidence_basis):'来源元数据 · 尚无 AI 摘要'}</p><div class="detail-body">${e(item.summary_zh || '本条目提供原始资料索引。当前没有足够的内容依据生成实质摘要，请访问原文。')}</div>${dateChips(item)?`<div class="event-date-row">${dateChips(item)}</div>`:''}<dl class="facts"><dt>原始出处</dt><dd>${e(source.organization)}</dd><dt>作者</dt><dd>${e(item.authors.join('、') || '来源未提供')}</dd><dt>发布日期</dt><dd>${e(shortDate(item.published_at))} ${item.date_precision==='month'?'（精确到月）':item.date_precision==='year'?'（精确到年）':''}</dd><dt>首次发现</dt><dd>${e(localTime(item.discovered_at))}</dd><dt>研究专题</dt><dd>${item.topics.map(t=>e(topicNames[t])).join(' / ') || '综合国际法'}</dd>${item.doi?`<dt>DOI</dt><dd>${e(item.doi)}</dd>`:''}<dt>材料性质</dt><dd>${e(item.material_type || moduleNames[item.module])}</dd><dt>输入依据</dt><dd>${e(item.evidence_basis)}；未核验全文</dd>${item.ai?`<dt>整理模型</dt><dd>${e(item.ai.model)}</dd>`:''}${item.provenance.length>1?`<dt>其他入口</dt><dd>${item.provenance.map(p=>e(sources.get(p.source_id)?.name || p.source_id)).join(' / ')}</dd>`:''}</dl><div class="detail-actions"><a class="primary-button" href="${href(item.url)}" target="_blank" rel="noopener noreferrer">访问原始来源 ↗</a><button class="secondary-button" data-save="${e(id)}" aria-pressed="${saved.has(id)}">${saved.has(id)?'已收藏 · 取消':'加入研究清单'}</button><button class="text-button" data-cite="${e(id)}">生成引注 ↗</button><a class="text-button" href="items/${e(id)}.html">独立页面 ↗</a></div><p class="fine-print">自动整理与字段检查不保证完整性或法律判断准确。官方新闻稿、当事方主张、裁判文件与学术观点具有不同性质，请回到原始资料核查。</p>`;
    const dialog=document.getElementById('detail-dialog'); if(!dialog.open)dialog.showModal();
  }
  function render() {
    const raw=location.hash.replace(/^#\/?/,'') || 'latest';
    const [name,query='']=raw.split('?');
    route=knownRoutes.includes(name)?name:'latest'; params=new URLSearchParams(query);
    if(params.has('module')&&!data.modules.some(m=>m.id===params.get('module')))params.delete('module');
    document.querySelectorAll('[data-route]').forEach(a=>{a.classList.toggle('active',a.dataset.route===route);if(a.dataset.route===route)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
    document.querySelectorAll('[data-topic]').forEach(a=>a.classList.toggle('active',route==='topic'&&params.get('id')===a.dataset.topic));
    let html=''; let pageTitle='最新资讯';
    if(route==='cite'){
      if(items.has(params.get('item')))window.CitationWorkbench.setItem(items.get(params.get('item')));
      html=heading('引注转换工作台','CITATION WORKBENCH','用可追溯的书目信息生成脚注。')
        +'<div id="cite-module"><p role="status">正在加载本地引注组件…</p></div>';
      pageTitle='引注转换';
    }
    else if(route==='cfp'){html=heading('让下一篇研究，找到合适的去处。','CALL FOR PAPERS','中英文期刊、专题征稿与会议征文，分开追踪。')+'<div id="cfp-module">'+window.CFPWorkbench.render(data)+'</div>';pageTitle='CFP 征稿';}
    else if(route==='sources'){html=sourcesPage();pageTitle='信源目录';}
    else if(route==='about'){html=aboutPage();pageTitle='关于与更新状态';}
    else if(route==='topics'){html=topicDirectory();pageTitle='研究专题';}
    else {
      const result=filterItems();
      const descriptions={latest:'期刊、机构与案件之间，发现值得追踪的研究线索。',research:'追踪期刊与著作线索，保留作者、DOI 与原始出版信息。',events:'会议、论坛与征稿公告。日期明确后，再进入你的学术日历。',official:'机构公告、新闻稿与官方资料入口；具体文件性质以原文为准。',cases:'司法与仲裁机构公开发布的案件线索与程序动态。',commentary:'来自学术平台的观点与讨论，保留作者与出处。',news:'从国际动态中发现法律研究线索，明确区分报道与法律认定。',saved:'把重要线索留给下一次研究。收藏仅保存在当前浏览器。'};
      const english={latest:'YOUR RESEARCH, ONE STEP AHEAD.',research:'SCHOLARSHIP & PUBLICATIONS',events:'THE ACADEMIC AGENDA',official:'OFFICIAL MATERIALS',cases:'CASES & PROCEEDINGS',commentary:'IDEAS & COMMENTARY',news:'WORLD & LAW',saved:'YOUR RESEARCH COLLECTION'};
      pageTitle=moduleNames[route] || (route==='saved'?'我的研究清单':route==='topic'?(topicNames[params.get('id')] || '研究专题'):'国际法，持续观察。');
      const extra=route==='events'?`<div class="view-switch"><button data-view="list" class="${params.get('view')!=='calendar'?'active':''}">公告列表</button><button data-view="calendar" class="${params.get('view')==='calendar'?'active':''}">学术日历</button></div>`:'';
      html=heading(pageTitle,english[route] || 'RESEARCH DOSSIER',descriptions[route] || '同一专题下，连接文献、案例、官方资料与学术讨论。',extra);
      if(data.paused_modules?.includes(route)){
        html=heading(pageTitle,english[route],'本站目前收录国际法学术资料。');
        html+=empty('此栏目暂停发布','你仍可浏览学术文献、征稿与司法资料。','<a class="secondary-button" href="#/research">浏览学术文献 ↗</a>');
        page.innerHTML=html;
        document.title=`${pageTitle} — ${data.site.name} ${data.site.english_name}`;
        return;
      }
      if(route==='latest'&&!['q','source','range','module','topic'].some(k=>params.get(k)))html+=latestIntro();
      if(route==='news')html+=newsStatus();
      if(route==='topic')html+=`<div class="topic-hero"><span>TOPIC DOSSIER · ${result.length} 条相关资料</span><a href="feeds/${e(data.topics.some(t=>t.id===params.get('id'))?params.get('id'):'disputes')}.xml">订阅本专题 RSS ↗</a></div>`;
      if(route==='saved'){
        const indexed=data.items.filter(i=>saved.has(i.id)).length;
        html+=`<div class="saved-actions"><button class="secondary-button" data-export-saved ${saved.size?'':'disabled'}>备份收藏 JSON</button><button class="secondary-button" data-import-saved>恢复收藏</button><input id="saved-backup-file" type="file" accept=".json,application/json" hidden><button class="secondary-button" data-export-saved-csl ${indexed?'':'disabled'}>导出 Zotero 书目</button><button class="text-button" data-clear-saved ${saved.size?'':'disabled'}>清空收藏</button></div><p class="saved-notice">已收藏 ${saved.size} 条，${indexed} 条在当前索引中。恢复会合并收藏，文件仅在浏览器内读取。</p>`;
      }
      if(Object.hasOwn(moduleNames,route))html+=`<p class="module-subscribe"><a href="feeds/modules/${e(route)}.xml">订阅本栏 RSS ↗</a></p>`;
      if(route==='events'&&params.get('view')==='calendar')html+=calendarView();
      else html+=`<div class="content-columns">${stream(result)}${rail()}</div>`;
    }
    page.innerHTML=html;
    document.title=`${pageTitle} — ${data.site.name} ${data.site.english_name}`;
    if(route==='cite'){
      const container=document.getElementById('cite-module');
      window.CitationWorkbench.loadEngine().then(()=>{
        if(!container.isConnected)return;
        container.innerHTML=window.CitationWorkbench.render();
        window.CitationWorkbench.mount(container,toast);
      }).catch(error=>{
        if(container.isConnected)container.textContent=error.message;
      });
    }
    if(route==='cfp')window.CFPWorkbench.mount(document.getElementById('cfp-module'));
    if(route!=='cite'&&params.get('item')&&items.has(params.get('item')))openDetail(params.get('item'));
  }

  document.getElementById('topic-nav').innerHTML=data.topics.map(t=>`<a href="${link('topic',{id:t.id})}" data-topic="${e(t.id)}"><span class="topic-dot"></span>${e(t.short)}</a>`).join('');
  document.getElementById('nav-total').textContent=data.items.length;
  document.getElementById('saved-count').textContent=saved.size;
  document.getElementById('edition-date').textContent=chineseDate(new Date(data.generated_at));
  document.getElementById('footer-updated').textContent='数据生成 '+localTime(data.generated_at)+' · 原始资料版权归各来源';

  document.addEventListener('click',event=>{
    const target=event.target.closest('button,a'); if(!target)return;
    if(target.dataset.save){
      const id=target.dataset.save;
      if(saved.has(id))saved.delete(id);else saved.add(id);
      persistSaved();
      const dialog=document.getElementById('detail-dialog');const opened=dialog.open;
      render();
      if(opened)openDetail(id,lastTrigger);
      toast(saved.has(id)?'已加入研究清单':'已取消收藏');
    } else if(target.dataset.cite){const chosen=items.get(target.dataset.cite);if(chosen){document.getElementById('detail-dialog').close();window.CitationWorkbench.setItem(chosen);navigate('cite',{item:chosen.id});}}
    else if(target.dataset.detail)openDetail(target.dataset.detail,target);
    else if(target.hasAttribute('data-module'))updateFilter('module',target.dataset.module);
    else if(target.hasAttribute('data-clear-filters')){const keep={};if(route==='topic')keep.id=params.get('id');navigate(route,keep,true);}
    else if(target.hasAttribute('data-load-more')){limit+=18;const y=scrollY;render();scrollTo(0,y);}
    else if(target.dataset.view)updateFilter('view',target.dataset.view==='list'?'':target.dataset.view);
    else if(target.dataset.month){if(target.dataset.month==='today')calendarMonth=currentMonth();else calendarMonth=new Date(calendarMonth.getFullYear(),calendarMonth.getMonth()+(target.dataset.month==='next'?1:-1),1);selectedDay='';render();}
    else if(target.dataset.day){selectedDay=target.dataset.day;render();}
    else if(target.hasAttribute('data-clear-day')){selectedDay='';render();}
    else if(target.hasAttribute('data-export-saved')){
      const exported={exported_at:new Date().toISOString(),site:data.site.english_name,ids:[...saved],items:data.items.filter(i=>saved.has(i.id))};
      downloadJSON('lexpacis-collection.json',exported);
    } else if(target.hasAttribute('data-import-saved'))document.getElementById('saved-backup-file').click();
    else if(target.hasAttribute('data-export-saved-csl')){
      const records=data.items.filter(item=>saved.has(item.id)).map(item=>({...window.CitationWorkbench.fromItem(item),id:item.id}));
      downloadJSON('lexpacis-zotero.csl.json',records);
    } else if(target.hasAttribute('data-clear-saved')){
      if(!window.confirm('确定清空当前浏览器的全部收藏？建议先备份。'))return;
      saved.clear();persistSaved();render();toast('已清空当前浏览器的收藏');
    }
  });
  document.addEventListener('input',event=>{if(event.target.id==='search-input'){clearTimeout(searchTimer);const value=event.target.value;searchTimer=setTimeout(()=>updateFilter('q',value),220);}});
  document.addEventListener('change',event=>{
    if(event.target.id==='saved-backup-file'){restoreSaved(event.target.files[0]);return;}
    const filters={'source-filter':'source','range-filter':'range','sort-filter':'sort'};
    if(filters[event.target.id])updateFilter(filters[event.target.id],event.target.value);
  });
  const dialog=document.getElementById('detail-dialog');
  document.getElementById('close-dialog').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',event=>{if(event.target===dialog){const bounds=dialog.getBoundingClientRect();if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)dialog.close();}});
  dialog.addEventListener('close',()=>{if(lastTrigger?.isConnected)lastTrigger.focus();});
  document.addEventListener('keydown',event=>{if(event.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)&&!dialog.open){event.preventDefault();if(!document.getElementById('search-input'))navigate('latest');setTimeout(()=>document.getElementById('search-input')?.focus(),0);}});
  document.getElementById('mobile-search').addEventListener('click',()=>{navigate('latest');setTimeout(()=>document.getElementById('search-input')?.focus(),0);});
  window.addEventListener('hashchange',()=>{clearTimeout(searchTimer);limit=18;render();window.scrollTo({top:0,behavior:'instant'});});
  render();
})();
