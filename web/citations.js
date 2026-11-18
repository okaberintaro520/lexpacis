/* Local citation workbench. Bibliographic data never becomes code or a shell command. */
(() => {
  'use strict';
  const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const types={'article-journal':'期刊论文',book:'专著',chapter:'文集篇章',webpage:'网页 / 学术评论',report:'机构报告 / 联合国文件',legal_case:'判例 / 裁判文书',treaty:'条约（需核对法律专用字段）'};
  const styles={
    'chinese-law':{name:'《法学引注手册》第二版 · 社区 CSL',note:'采用 Zotero 中文社区的多语言、完整重复引注、标注页码样式。中文文献请选 zh-CN；英文文献选 en。社区实现不等于官方认证，复杂判例等仍需对照原规范。',url:'https://zotero-chinese.com/styles/法学引注手册（第二版，多语言，重复引用不省略，标注页码）/'},
    oscola:{name:'OSCOLA 第 4 版 · CSL',note:'这是已固定的第 4 版样式。牛津已发布第 5 版；本工具不把旧样式冒称为第 5 版。若目标刊物要求第 5 版，请对照其现行规范。',url:'https://www.law.ox.ac.uk/oscola'},
    bluebook:{name:'Bluebook Law Review · CSL',note:'使用公开 CSL 的 Bluebook Law Review 实现。复杂司法辖区、法律缩写和目标期刊的特殊要求需要复核；不声称完整实现某一版 Bluebook。',url:'https://github.com/citation-style-language/styles/blob/master/bluebook-law-review.csl'},
    chicago:{name:'Chicago 第 18 版 · 脚注与书目',note:'采用公开 CSL 的 Chicago 18th notes and bibliography 样式。清单按实际顺序计算再引，不自动将论文起始页当作你引用的具体页码。',url:'https://github.com/citation-style-language/styles/blob/master/chicago-notes-bibliography.csl'}
  };
  const fresh=()=>({type:'article-journal',language:'en',author:[],title:''});
  let draft=fresh(), notes=[], style='chinese-law', start=1, locator='', label='page', preview='', onToast=()=>{};
  let host,lookupController=null;
  let engineLoad;
  function loadEngine(){
    if(window.CSL&&window.LEXATLAS_CSL)return Promise.resolve();
    if(engineLoad)return engineLoad;
    const files=[];
    if(!window.CSL)files.push('vendor/citeproc.js');
    if(!window.LEXATLAS_CSL)files.push('vendor/citation-styles.js');
    engineLoad=Promise.all(files.map(source=>new Promise((resolve,reject)=>{
      const script=document.createElement('script');script.src=source;
      script.onload=resolve;script.onerror=()=>{script.remove();reject(Error('本地引注组件未加载。请重新打开此页。'));};
      document.head.append(script);
    }))).then(()=>{
      if(!window.CSL||!window.LEXATLAS_CSL)throw Error('本地引注组件未能初始化。');
    }).catch(error=>{engineLoad=null;throw error;});
    return engineLoad;
  }
  try{const stored=JSON.parse(localStorage.getItem('lexatlas.citations.v1')||'null');if(stored&&Array.isArray(stored.notes)){notes=stored.notes.slice(0,80).map(n=>({record:cleanRecord(n.record),locator:String(n.locator||'').slice(0,100),label:['page','paragraph','section','chapter','article'].includes(n.label)?n.label:'page'}));if(styles[stored.style])style=stored.style;}}catch{/* Corrupt or unavailable local storage does not block reading. */}
  function text(v,max=4000){if(typeof v!=='string'&&typeof v!=='number')return '';const doc=new DOMParser().parseFromString(String(v),'text/html');return (doc.body.textContent||'').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g,'').trim().slice(0,max);}
  function cleanRecord(raw){
    if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('每条书目需为 CSL JSON 对象。');
    const out={type:types[raw.type]?raw.type:'article-journal'};
    for(const key of ['title','container-title','container-title-short','title-short','volume','issue','page','publisher','publisher-place','edition','DOI','URL','language','number','authority','genre','status','collection-title','collection-number'])if(raw[key]!==undefined)out[key]=text(raw[key]);
    for(const role of ['author','editor','translator'])if(Array.isArray(raw[role]))out[role]=raw[role].slice(0,80).map(p=>{if(!p||typeof p!=='object')return {literal:''};const n={};for(const k of ['family','given','literal','suffix','non-dropping-particle'])if(p[k])n[k]=text(p[k],300);return n;}).filter(n=>n.family||n.literal||n.given);
    for(const key of ['issued','accessed']){
      const parts=raw[key]?.['date-parts']?.[0];
      if(validDateParts(parts))out[key]={'date-parts':[parts.slice()]};
    }
    if(out.URL&&!/^https?:\/\//i.test(out.URL))delete out.URL;
    if(!out.language)out.language=/[\u3400-\u9fff]/.test(out.title||'')?'zh-CN':'en';
    out.id='r-'+hash(JSON.stringify(out));return out;
  }
  function hash(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}return (h>>>0).toString(16);}
  function fromItem(item){
    const b=item.bibliography||{};let type=item.module==='research'?'article-journal':item.source_id==='icj'?'report':'webpage';
    const date=item.published_at?.slice(0,10).split('-').map(Number);
    return cleanRecord({type,title:item.title,author:(item.authors||[]).map(n=>parseName(n)),DOI:item.doi,URL:item.url,language:/[\u3400-\u9fff]/.test(item.title)?'zh-CN':'en',
      'container-title':(b['container-title']||[])[0],volume:b.volume,issue:b.issue,page:b.page,publisher:b.publisher,issued:date?{'date-parts':[date]}:undefined});
  }
  function parseName(n){n=text(n,300);if(n.includes(',')){const [family,...rest]=n.split(',');return {family:family.trim(),given:rest.join(',').trim()};}if(/[\u3400-\u9fff]/.test(n))return {literal:n};const bits=n.split(/\s+/);return bits.length>1?{family:bits.pop(),given:bits.join(' ')}:{literal:n};}
  function names(v){return v.split(/[;；\n]/).map(s=>s.trim()).filter(Boolean).map(parseName);}
  function namesText(list){return (list||[]).map(n=>n.literal||[n.family,n.given].filter(Boolean).join(', ')).join('\n');}
  function dateText(value){return (value?.['date-parts']?.[0]||[]).map((n,i)=>i?String(n).padStart(2,'0'):n).join('-');}
  function validDateParts(parts){
    if(!Array.isArray(parts)||!parts.length||parts.length>3||!parts.every(Number.isInteger))return false;
    const [year,month,day]=parts;
    if(year<1000||year>2999)return false;
    if(month!==undefined&&(month<1||month>12))return false;
    return day===undefined||(day>=1&&day<=new Date(Date.UTC(year,month,0)).getUTCDate());
  }
  function dateValue(value){
    if(!/^\d{4}(?:-\d{2})?(?:-\d{2})?$/.test(value))return undefined;
    const parts=value.split('-').map(Number);
    return validDateParts(parts)?{'date-parts':[parts]}:undefined;
  }
  function sanitize(html){
    const doc=new DOMParser().parseFromString(html,'text/html');
    const allowed=new Set(['I','B','EM','STRONG','SPAN','SUP','SUB','SMALL','DIV']);
    function visit(parent){for(const child of [...parent.children]){if(!allowed.has(child.tagName)){child.replaceWith(doc.createTextNode(child.textContent||''));continue;}const style=child.getAttribute('style')||'';for(const attr of [...child.attributes])child.removeAttribute(attr.name);if(style){const accepted=style.split(';').filter(s=>/^\s*(font-style\s*:\s*(italic|normal)|font-weight\s*:\s*(bold|normal)|font-variant\s*:\s*small-caps|vertical-align\s*:\s*(super|sub))\s*$/i.test(s));if(accepted.length)child.setAttribute('style',accepted.join(';'));}visit(child);}}
    visit(doc.body);return doc.body.innerHTML;
  }
  function plain(html){return new DOMParser().parseFromString(html,'text/html').body.textContent||'';}
  function format(list,styleId=style,first=start){
    if(!window.CSL||!window.LEXATLAS_CSL)throw Error('本地引注引擎未加载。请保留 vendor 文件夹。');
    const records={},ids=[],registry=new Map();
    list.forEach((n,i)=>{const record=cleanRecord(n.record);delete record.id;const signature=JSON.stringify(record);if(!registry.has(signature))registry.set(signature,'cite-record-'+registry.size);const id=registry.get(signature);record.id=id;records[id]=record;ids.push(id);});
    const bundle=window.LEXATLAS_CSL;
    const sys={retrieveLocale:lang=>bundle.locales[lang]||bundle.locales[lang.startsWith('zh')?'zh-CN':lang==='en-GB'?'en-GB':'en-US'],retrieveItem:id=>records[id]};
    const engine=new CSL.Engine(sys,bundle.styles[styleId]);engine.setOutputFormat('html');engine.updateItems([...new Set(ids)]);
    const results=[],previous=[];
    list.forEach((note,index)=>{
      const citationID='lex-note-'+index;const noteIndex=first+index;
      const citationItem={id:ids[index]};if(note.locator){citationItem.locator=note.locator;citationItem.label=note.label||'page';}
      const output=engine.processCitationCluster({citationID,citationItems:[citationItem],properties:{noteIndex}},previous,[]);
      for(const update of output[1])results[update[0]]=sanitize(update[1]);
      previous.push([citationID,noteIndex]);
    });
    return results;
  }
  function warnings(record){
    const out=[];if(!record.title)out.push('请填写题名。');
    if(!record.author?.length&&!record.authority)out.push('缺少作者或机构，请按原始资料补充。');
    if(!record.issued)out.push('未提供出版日期；不会自动补一个年份。');
    if(record.type==='article-journal'){if(!record['container-title'])out.push('缺少期刊名称。');if(!record.page)out.push('未提供论文起始页或文章编号；可用 DOI 核对。');}
    if(['book','chapter'].includes(record.type)&&!record.publisher)out.push('缺少出版社。');
    if(record.type==='legal_case'&&!record.authority)out.push('判例需补裁判机构、报告集、案号及文书性质等信息。');
    if(record.type==='treaty')out.push('条约的签署/生效日期、条约集和条款定位通常需按所选规范另外核对。');
    return out;
  }
  function save(){try{localStorage.setItem('lexatlas.citations.v1',JSON.stringify({style,notes}));}catch{onToast('浏览器限制存储；本次脚注清单仅在当前页面有效。');}}
  const field=(key,name,placeholder='',wide=false)=>`<label class="cite-field ${wide?'wide':''}"><span>${e(name)}</span><input data-cite-field="${e(key)}" value="${e(draft[key]||'')}" placeholder="${e(placeholder)}" maxlength="4000"></label>`;
  function render(){
    return `<section class="citation-workbench"><div class="tool-intro"><span class="tool-local"><span class="status-dot"></span>本地格式化 · 不调用模型</span><p>从平台条目带入书目信息，或用 DOI、RIS / CSL JSON 导入。补上具体引文页码，再生成可复制的脚注。</p></div><div class="cite-layout"><section class="cite-editor"><div class="tool-section-title"><span>01 / 书目信息</span><button class="text-button" data-cite-reset>清空表单</button></div><form id="doi-form" class="doi-form"><label class="search-box"><input id="cite-doi" aria-label="输入 DOI" placeholder="粘贴 DOI，如 10.1017/ajil.2023.40" maxlength="300"></label><button class="secondary-button" id="doi-button" type="submit">读取 DOI ↗</button></form><p class="tool-fine">仅点击读取时向 Crossref 请求公开元数据。无法连接时，可手动录入或导入文件，其他功能照常使用。</p><p id="doi-result" class="tool-status" role="status"></p><div class="cite-form-grid"><label class="cite-field"><span>资料类型</span><select id="cite-type">${Object.entries(types).map(([v,n])=>`<option value="${v}" ${draft.type===v?'selected':''}>${e(n)}</option>`).join('')}</select></label><label class="cite-field"><span>原文语言</span><select id="cite-language">${[['en','English'],['zh-CN','中文'],['fr','Français'],['de','Deutsch'],['ja','日本語'],['ru','Русский'],['it','Italiano']].map(([v,n])=>`<option value="${v}" ${draft.language===v?'selected':''}>${n}</option>`).join('')}</select></label>${field('title','题名','使用原始题名，不以机器译名替代',true)}<label class="cite-field wide"><span>作者（每行一位；英文建议“姓, 名”）</span><textarea id="cite-authors" rows="2" placeholder="张三&#10;Smith, John" maxlength="20000">${e(namesText(draft.author))}</textarea></label>${field('container-title','期刊 / 文集 / 报告集名称')}${field('container-title-short','期刊 / 报告集缩写（可选）')}<label class="cite-field"><span>出版日期（按来源精度填写）</span><input id="cite-issued" value="${e(dateText(draft.issued))}" placeholder="2026 或 2026-11-18" maxlength="10"></label>${field('volume','卷号')}${field('issue','期号')}${field('page','论文起止页 / 文章编号','如 144-164；不是本次引文页码')}${field('publisher','出版社')}${field('publisher-place','出版地')}${field('edition','版次','如 2')}<label class="cite-field"><span>编者（每行一位）</span><textarea id="cite-editors" rows="2" maxlength="10000">${e(namesText(draft.editor))}</textarea></label><label class="cite-field"><span>译者（每行一位）</span><textarea id="cite-translators" rows="2" maxlength="10000">${e(namesText(draft.translator))}</textarea></label>${field('authority','机构 / 裁判法院')}${field('number','文号 / 案号')}${field('genre','文书性质','如 Judgment / Resolution')}${field('DOI','DOI')}${field('URL','原文网址','https://',true)}<label class="cite-field"><span>访问日期（仅在需要时填写）</span><input id="cite-accessed" value="${e(dateText(draft.accessed))}" placeholder="YYYY-MM-DD" maxlength="10"></label></div><details class="cite-import"><summary>导入 RIS / CSL JSON</summary><label class="cite-field"><span>粘贴结构化书目（不会执行其中的内容）</span><textarea id="cite-import-text" rows="5" maxlength="300000" placeholder="粘贴 Zotero 导出的 CSL JSON 或 RIS"></textarea></label><div class="tool-actions"><button class="secondary-button" data-import-one>读取第一条到表单</button><button class="secondary-button" data-import-all>导入为脚注清单</button></div><p class="tool-fine">最多 80 条。普通自然语言引文无法可靠反向解析，请用 DOI 或手动补全。</p></details></section><aside class="cite-output"><div class="tool-section-title"><span>02 / 引注规范与定位</span></div><label class="cite-field"><span>选择脚注规范</span><select id="citation-style">${Object.entries(styles).map(([v,s])=>`<option value="${v}" ${style===v?'selected':''}>${e(s.name)}</option>`).join('')}</select></label><p class="style-note" id="citation-style-note"></p><div class="cite-locator"><label class="cite-field"><span>定位类型</span><select id="cite-label">${[['page','具体页码'],['paragraph','段落'],['section','节 / 条'],['chapter','章'],['article','条款']].map(([v,n])=>`<option value="${v}" ${label===v?'selected':''}>${n}</option>`).join('')}</select></label><label class="cite-field"><span>本次引文定位</span><input id="cite-locator" value="${e(locator)}" placeholder="如 156-158 或 176" maxlength="100"></label></div><div id="citation-warnings" class="citation-warnings"></div><div class="citation-preview" id="citation-preview" aria-live="polite"></div><div class="tool-actions"><button class="primary-button" data-copy-citation>复制脚注</button><button class="secondary-button" data-add-note>加入清单 ＋</button></div><div class="citation-hint">生成的是可复制的脚注内容，不会直接修改你正在编辑的 Word 文档。不同期刊的专用规则优先于通用样式。</div><div class="citation-attribution">由 <a href="https://github.com/Juris-M/citeproc-js" target="_blank" rel="noopener noreferrer">citeproc-js · Frank Bennett</a> 驱动。<a href="vendor/citeproc.js">引擎源码</a> · <a href="vendor/citeproc-CPAL.txt">许可</a> · <a href="citation-credits.html">样式版本与来源</a></div></aside></div><section class="citation-notes"><div class="tool-section-title"><span>03 / 脚注清单 <b id="note-count"></b></span><label class="start-note">起始序号 <input type="number" id="cite-start" min="1" max="9999" value="${start}" aria-label="脚注起始序号"></label></div><p class="tool-fine">按清单顺序计算引用；同一来源可用不同定位重复加入。清单仅存于当前浏览器。</p><div id="citation-note-list"></div><div class="tool-actions"><button class="secondary-button" data-copy-notes>复制全部脚注</button><button class="secondary-button" data-export-notes>下载 TXT ↓</button><button class="secondary-button" data-export-csl>下载 CSL JSON ↓</button><button class="text-button" data-clear-notes>清空清单</button></div></section></section>`;
  }
  function refresh(){
    if(!host?.querySelector('#citation-preview'))return;
    const s=styles[style];host.querySelector('#citation-style-note').innerHTML=e(s.note)+` <a href="${e(s.url)}" target="_blank" rel="noopener noreferrer">样式说明 ↗</a>`;
    const warn=warnings(draft);host.querySelector('#citation-warnings').innerHTML=warn.length?warn.map(w=>`<div>· ${e(w)}</div>`).join(''):'';
    try{preview=draft.title?format([{record:draft,locator,label}],style,1)[0]:'';host.querySelector('#citation-preview').innerHTML=preview||'<span class="preview-placeholder">填写题名和出版信息后，在这里预览脚注。</span>';}catch(error){preview='';host.querySelector('#citation-preview').textContent='无法生成：'+error.message;}
    let formatted=[];try{formatted=notes.length?format(notes):[];}catch(error){host.querySelector('#citation-note-list').textContent='清单格式化失败：'+error.message;return;}
    host.querySelector('#note-count').textContent=notes.length?`· ${notes.length} 条`:'';
    host.querySelector('#citation-note-list').innerHTML=notes.length?`<ol class="footnote-list" start="${start}">${notes.map((n,i)=>`<li><div class="footnote-text">${formatted[i]||''}</div><div class="note-controls"><button data-note-up="${i}" aria-label="上移第 ${i+1} 条" ${i?'':'disabled'}>↑</button><button data-note-remove="${i}" aria-label="移除第 ${i+1} 条">×</button></div></li>`).join('')}</ol>`:'<div class="notes-empty">还没有脚注。补好书目信息后，点击“加入清单”。</div>';
  }
  function download(name,content,type){const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  async function copy(html){
    if(!html){onToast('请先生成脚注。');return;}
    try{if(navigator.clipboard?.write&&window.ClipboardItem){await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([html],{type:'text/html'}),'text/plain':new Blob([plain(html)],{type:'text/plain'})})]);}else throw Error();onToast('已复制脚注，可粘贴到编辑器。');}
    catch{const area=document.createElement('textarea');area.value=plain(html);document.body.append(area);area.select();const ok=document.execCommand('copy');area.remove();onToast(ok?'已复制纯文本脚注。':'浏览器未允许复制，请选中预览内容复制。');}
  }
  function parseRIS(value){const result=[];let current=null;for(const line of value.replace(/\r/g,'').split('\n')){const match=line.match(/^([A-Z0-9]{2})\s{0,2}-\s?(.*)$/);if(!match)continue;const [,tag,v]=match;if(tag==='TY')current={type:{JOUR:'article-journal',BOOK:'book',CHAP:'chapter',ELEC:'webpage',RPRT:'report',CASE:'legal_case'}[v.trim()]||'article-journal',author:[]};if(!current)continue;if(tag==='AU'||tag==='A1')current.author.push(parseName(v));const fields={TI:'title',T1:'title',JF:'container-title',JO:'container-title',T2:'container-title',VL:'volume',IS:'issue',SP:'page',PB:'publisher',CY:'publisher-place',DO:'DOI',UR:'URL',LA:'language'};if(fields[tag])current[fields[tag]]=v;if(tag==='EP')current.page=(current.page||'')+'-'+v;if(tag==='PY'||tag==='Y1')current.issued=dateValue(v.replaceAll('/','-').replace(/-+$/,''));if(tag==='ER'){result.push(cleanRecord(current));current=null;}}if(current)result.push(cleanRecord(current));return result;}
  function importRecords(){const input=host.querySelector('#cite-import-text').value.trim();if(input.length>300000)throw Error('导入内容过长。');let records;if(input.startsWith('{')||input.startsWith('[')){const parsed=JSON.parse(input);records=Array.isArray(parsed)?parsed:parsed.items&&Array.isArray(parsed.items)?parsed.items:[parsed];records=records.map(r=>r.source_id?fromItem(r):cleanRecord(r));}else records=parseRIS(input);if(!records.length||records.length>80)throw Error('请提供 1—80 条有效 RIS 或 CSL JSON 书目。');return records;}
  async function doiLookup(event){
    event.preventDefault();let doi=host.querySelector('#cite-doi').value.trim().replace(/^https?:\/\/(?:dx\.)?doi\.org\//i,'').replace(/^doi:\s*/i,'');
    const result=host.querySelector('#doi-result');if(!/^10\.\d{4,9}\/\S+$/i.test(doi)){result.textContent='请输入有效 DOI；不能用普通网址替代。';return;}
    if(lookupController)lookupController.abort();lookupController=new AbortController();const timer=setTimeout(()=>lookupController.abort(),18000);const button=host.querySelector('#doi-button');button.disabled=true;result.textContent='正在向 Crossref 读取书目…';
    try{const response=await fetch('https://api.crossref.org/works/'+encodeURIComponent(doi),{signal:lookupController.signal,credentials:'omit',referrerPolicy:'no-referrer'});if(!response.ok)throw Error('Crossref 返回 '+response.status);const json=await response.json();const m=json.message;if(!m||!m.DOI||m.DOI.toLowerCase()!==doi.toLowerCase())throw Error('返回的 DOI 与请求不一致');const dates=m.published||m['published-online']||m['published-print']||m.issued;draft=cleanRecord({type:{'journal-article':'article-journal','book-chapter':'chapter',book:'book',monograph:'book',report:'report'}[m.type]||'article-journal',title:(m.title||[])[0],author:m.author,editor:m.editor,'container-title':(m['container-title']||[])[0],volume:m.volume,issue:m.issue,page:m.page,publisher:m.publisher,'publisher-place':m['publisher-location'],edition:m.edition,DOI:m.DOI,URL:m.URL,issued:dates,language:m.language});locator='';rerender();host.querySelector('#doi-result').textContent='已读取 Crossref 元数据。请补充和核对本次引文定位。';}
    catch(error){result.textContent='读取失败：'+(error.name==='AbortError'?'请求超时或已取消':error.message)+'。可手动填写，不影响本地格式化。';}
    finally{clearTimeout(timer);if(button.isConnected)button.disabled=false;}
  }
  function rerender(){host.innerHTML=render();bind();refresh();}
  function bind(){
    host.querySelector('#doi-form').addEventListener('submit',doiLookup);
    host.oninput=event=>{const t=event.target;if(t.dataset.citeField){draft[t.dataset.citeField]=t.value;}else if(t.id==='cite-authors')draft.author=names(t.value);else if(t.id==='cite-editors')draft.editor=names(t.value);else if(t.id==='cite-translators')draft.translator=names(t.value);else if(t.id==='cite-issued')draft.issued=dateValue(t.value);else if(t.id==='cite-accessed')draft.accessed=dateValue(t.value);else if(t.id==='cite-locator')locator=t.value;else if(t.id==='cite-start')start=Math.max(1,Math.min(9999,Number(t.value)||1));else return;refresh();};
    host.onchange=event=>{const t=event.target;if(t.id==='citation-style'){style=t.value;save();}else if(t.id==='cite-type')draft.type=t.value;else if(t.id==='cite-language')draft.language=t.value;else if(t.id==='cite-label')label=t.value;else return;refresh();};
    host.onclick=event=>{const button=event.target.closest('button');if(!button)return;try{
      if(button.hasAttribute('data-copy-citation'))copy(preview);
      else if(button.hasAttribute('data-add-note')){if(!draft.title)throw Error('请先填写题名。');if(notes.length>=80)throw Error('清单最多 80 条。');notes.push({record:cleanRecord(draft),locator:locator.trim(),label});save();refresh();onToast('已加入脚注清单。');}
      else if(button.hasAttribute('data-cite-reset')){draft=fresh();locator='';rerender();}
      else if(button.hasAttribute('data-note-remove')){notes.splice(Number(button.dataset.noteRemove),1);save();refresh();}
      else if(button.hasAttribute('data-note-up')){const i=Number(button.dataset.noteUp);if(i>0)[notes[i-1],notes[i]]=[notes[i],notes[i-1]];save();refresh();}
      else if(button.hasAttribute('data-clear-notes')){notes=[];save();refresh();}
      else if(button.hasAttribute('data-copy-notes')){if(!notes.length)throw Error('清单为空。');copy(format(notes).map((html,i)=>`<p>${start+i}. ${html}</p>`).join(''));}
      else if(button.hasAttribute('data-export-notes'))download('footnotes.txt',format(notes).map((html,i)=>`${start+i}. ${plain(html)}`).join('\n\n'),'text/plain;charset=utf-8');
      else if(button.hasAttribute('data-export-csl'))download('references.csl.json',JSON.stringify(notes.map(n=>n.record),null,2),'application/json');
      else if(button.hasAttribute('data-import-one')){draft=importRecords()[0];locator='';rerender();onToast('已读取书目信息。');}
      else if(button.hasAttribute('data-import-all')){const records=importRecords();if(notes.length+records.length>80)throw Error('加入后超过 80 条，请先导出已有清单。');notes.push(...records.map(record=>({record,locator:'',label:'page'})));save();refresh();onToast('已导入 '+records.length+' 条书目。');}
    }catch(error){onToast(error.message);}};
  }
  window.CitationWorkbench={render,loadEngine,mount(container,toast){host=container;onToast=toast||(()=>{});bind();refresh();},fromItem,setItem(item){draft=fromItem(item);locator='';},format,cleanRecord,parseRIS,styles,sanitize};
})();
