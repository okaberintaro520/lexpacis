/* CFP publication board: directories, dated calls, and unverified leads remain distinct. */
(() => {
  'use strict';
  const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const url=v=>{try{const u=new URL(v);return /^https?:$/.test(u.protocol)?e(u.href):'#';}catch{return '#';}};
  let host,source,topics,view='journal',language='',topic='',query='',dateFilter='upcoming';
  const kindName={journal_special:'期刊专题征稿',journal_notice:'常规征稿公告',conference:'会议征文',discovery:'待确认线索'};
  const date=v=>v?v.slice(0,10).replaceAll('-','.'):'';
  const today=()=>new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Shanghai'});
  const isPast=call=>Boolean(call.deadline&&call.deadline<today());
  const languages={zh:'中文',en:'英文',bilingual:'中英文'};
  const filtered=list=>list.filter(item=>(!language||item.language===language||(language==='zh'&&item.language==='bilingual'))&&(!topic||item.topics?.includes(topic))&&(!query||[item.name,item.title,item.original_title,item.scope,item.publisher,item.description].join(' ').toLowerCase().includes(query.toLowerCase())));
  const options=(list,value)=>list.map(([v,n])=>`<option value="${e(v)}" ${v===value?'selected':''}>${e(n)}</option>`).join('');
  function render(data){
    source=data.cfp||{calls:[],journals:[]};topics=data.topics;
    const cn=source.journals.filter(j=>['zh','bilingual'].includes(j.language)).length;
    const en=source.journals.filter(j=>j.language==='en').length;
    const confirmed=source.calls.filter(c=>c.kind!=='discovery');
    return `<section class="cfp-workbench"><div class="tool-intro"><span class="tool-local">CALL FOR PAPERS</span><p>期刊征稿与学术会议分开追踪。导航提供投稿入口，明确的截止日期才进入订阅日历。</p></div><div class="cfp-summary"><div class="metric-block"><strong>${cn}</strong><span>中文 / 中英文刊物入口</span></div><div class="metric-block"><strong>${en}</strong><span>英文刊物入口</span></div><div class="metric-block"><strong>${confirmed.filter(c=>c.kind!=='conference').length}</strong><span>有来源依据的期刊公告</span></div><div class="metric-block"><strong>${confirmed.filter(c=>c.kind==='conference').length}</strong><span>有来源依据的会议征文</span></div></div><div class="cfp-nav" role="group" aria-label="CFP 分类">${[['journal','期刊征稿'],['conference','会议征文'],['directory','期刊投稿导航'],['discovery','待确认线索']].map(([v,n])=>`<button data-cfp-view="${v}" class="${view===v?'active':''}">${n}</button>`).join('')}<a class="text-button" href="cfp.ics" style="margin-left:auto">截止日期 ICS ↗</a></div><div class="cfp-toolbar"><label class="search-box"><span aria-hidden="true">⌕</span><input id="cfp-search" type="search" aria-label="搜索期刊和征稿" placeholder="搜索刊名、征稿主题或机构…" value="${e(query)}"></label><select id="cfp-language" class="filter-select" aria-label="按征稿语言筛选">${options([['','全部语言'],['zh','中文 / 中英文'],['en','英文'],['bilingual','中英文刊物']],language)}</select><select id="cfp-topic" class="filter-select" aria-label="按研究方向筛选">${options([['','全部研究方向'],...topics.map(t=>[t.id,t.short])],topic)}</select><select id="cfp-date" class="filter-select" aria-label="按截止日期筛选" ${view==='directory'?'disabled':''}>${options([['upcoming','日期未过 / 未注明期限'],['all','包括历史公告'],['dated','仅有明确截止日']],dateFilter)}</select></div><div id="cfp-results"></div><p class="cfp-footer">${e(source.coverage_note||'')} <a href="api/cfp.json">公开数据 ↗</a> · <a href="cfp-policy.html">覆盖与核对规则 ↗</a></p></section>`;
  }
  function journalCard(j){
    const status={identity_matched:'最近读取页面包含刊名',reachable_unconfirmed:'页面可读，期刊身份待确认',error:'本次访问异常，未更新验证',unverified:'尚未运行入口检查'}[j.check_status]||'待确认';
    const href=j.identity_source||j.homepage;
    const labels=(j.topics||[]).map(id=>topics.find(t=>t.id===id)?.short).filter(Boolean).join(' / ');
    return `<article class="journal-card"><div class="journal-labels"><span>${languages[j.language]||j.language}</span><span>${e(labels)}</span></div><h2>${e(j.name)}</h2><div class="journal-publisher">${e(j.publisher)}</div><div class="journal-scope">${e(j.scope)}</div>${j.note?`<p class="tool-fine" style="margin:0">${e(j.note)}</p>`:''}<div class="journal-state">${status}${j.checked_at?' · '+date(j.checked_at):''}${j.changed?' · 页面有变化，待更新稿约信息':''}<br>这是期刊入口，不表示当前有专题 CFP 或保证投稿窗口开放。</div><div class="journal-links"><a href="${url(href)}" target="_blank" rel="noopener noreferrer">主办 / 出版机构来源 ↗</a><a href="${url(j.submissions_url)}" target="_blank" rel="noopener noreferrer">${j.check_status==='identity_matched'?'稿约 / 投稿入口':'查看登记入口（待核对）'} ↗</a></div></article>`;
  }
  function callCard(call){
    const j=source.journals.find(j=>j.id===call.journal_id);
    const state=call.deadline?(isPast(call)?'已过公告截止日':'公告截止日未到'):'原文未注明固定截止日';
    return `<article class="cfp-call"><div class="cfp-call-top"><span class="cfp-kind">${kindName[call.kind]||'征稿公告'} · ${languages[call.language]||call.language}</span><span class="cfp-state ${isPast(call)?'past':''}">${state}</span></div><h2>${e(call.title)}</h2>${call.original_title!==call.title?`<p class="cfp-original">${e(call.original_title)}</p>`:''}<p>${e(call.description)}</p><div class="cfp-deadline">${call.deadline?`${e(call.deadline_label||'截止日期')}：${date(call.deadline)}`:'未把发布日期或会议日期当作投稿截止日'}</div><div class="cfp-call-meta">${call.deadline_timezone?`原文时区：${e(call.deadline_timezone)}<br>`:call.deadline?'原文未给出精确时区；不提供精确到小时的倒计时。<br>':''}${e(j?.name||call.organization||'已接通信源')}<br>${call.verification==='discovered_title'?'尚未核对完整公告':'依据原始公告整理'} · ${date(call.checked_at)}${call.source_changed?' · 来源页面有变化，请核对最新版':''}</div><div class="cfp-call-actions"><a class="text-button" href="${url(call.url)}" target="_blank" rel="noopener noreferrer">阅读原始公告 ↗</a>${call.kind==='conference'?'<span class="tool-fine" style="margin:0">参会不等于期刊录用</span>':''}</div></article>`;
  }
  function refresh(){
    if(!host)return;const output=host.querySelector('#cfp-results');
    if(view==='directory'){
      const list=filtered(source.journals);
      output.innerHTML=`<p class="cfp-watch-note">当前导航包含 ${source.journals.length} 种国际法及部分综合法刊物，非排名或收录保证。仅保留出版机构、编辑部或主办高校入口；请从其正式公告进入投稿系统。历史链接、访问异常和页面可读但身份待确认的入口均明确标注。</p><div class="stream-total">找到 ${list.length} 种刊物</div><div class="journal-grid">${list.length?list.map(journalCard).join(''):'<div class="cfp-grid-empty">没有匹配刊物，可调整语言、研究方向或关键词。</div>'}</div>`;
    }else{
      let list=filtered(source.calls).filter(c=>view==='journal'?['journal_special','journal_notice'].includes(c.kind):c.kind===view);
      if(dateFilter==='upcoming')list=list.filter(c=>!isPast(c));
      if(dateFilter==='dated')list=list.filter(c=>c.deadline);
      list.sort((a,b)=>(a.deadline||'9999').localeCompare(b.deadline||'9999'));
      output.innerHTML=`${view==='discovery'?'<p class="cfp-watch-note">此处是已接通信源自动发现的线索，不是已核对的投稿承诺。期限、刊物归属和投稿资格确认后，才能转入相应公告区。</p>':'<p class="cfp-watch-note">截止日以原文为准。日期筛选按公告日历日期，不保证当地精确截止时刻；常规征稿公告不等于一个带截止日的专题 CFP。</p>'}<div class="stream-total">${list.length} 条公告 / 线索</div><div class="cfp-call-grid">${list.length?list.map(callCard).join(''):'<div class="cfp-grid-empty">当前筛选下没有已收录公告。可查看期刊投稿导航，或选择“包括历史公告”。不会为填充页面虚构征稿。</div>'}</div>`;
    }
  }
  function mount(container){host=container;refresh();let timer;
    host.onclick=event=>{const b=event.target.closest('[data-cfp-view]');if(!b)return;view=b.dataset.cfpView;const focus=host.querySelector('#cfp-search')?.value||'';host.innerHTML=render({cfp:source,topics});mount(host);host.querySelector('#cfp-search').value=focus;};
    host.querySelector('#cfp-search').addEventListener('input',event=>{query=event.target.value;clearTimeout(timer);timer=setTimeout(refresh,140);});
    for(const [id,setter] of [['cfp-language',v=>language=v],['cfp-topic',v=>topic=v],['cfp-date',v=>dateFilter=v]])host.querySelector('#'+id).addEventListener('change',event=>{setter(event.target.value);refresh();});
  }
  window.CFPWorkbench={render,mount};
})();
