(function(){
'use strict';
const data=window.CEC_INSPECTION_MANIFEST, V=window.CECViewport, NS='http://www.w3.org/2000/svg';
const $=id=>document.getElementById(id), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,n=2)=>typeof v==='number'?v.toLocaleString(undefined,{maximumFractionDigits:n}):'—';
function nativeMeasured(board){return board.native_verification?.measured_at||'Not recorded';}
const checklist=['Interfaces, mating keys and mounting clearance inspected','Power pours, necks and layer transfers inspected','Decouplers and immediate Ground returns inspected','Signal escapes, bends and unwanted stubs inspected','Back-side markings and dense reference maps inspected','Electrical findings and qualification gaps reviewed'];
let board=null, box=null, selected=null, selectedNet='', token=0, storageOK=true, saveTimer=null;
let reviews={};try{reviews=JSON.parse(localStorage.getItem('cec-board-review-v1')||'{}');}catch(_){storageOK=false;}
const state=()=>reviews[board.sha256]||(reviews[board.sha256]={board:board.board,sha256:board.sha256,reviewed:false,checks:[],notes:''});
function persist(){try{localStorage.setItem('cec-board-review-v1',JSON.stringify(reviews));storageOK=true;}catch(_){storageOK=false;}
  $('note-status').textContent=storageOK?'Saved locally for this exact PCB identity.':'Browser storage is unavailable. Export notes before closing.';}
function svg(name,attrs,parent){const el=document.createElementNS(NS,name);for(const [key,value]of Object.entries(attrs))el.setAttribute(key,value);if(parent)parent.appendChild(el);return el;}
function table(headers,rows){return '<div class="table-scroll"><table><thead><tr>'+headers.map(h=>'<th>'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';}
function setTab(name){for(const button of document.querySelectorAll('[data-tab]'))button.setAttribute('aria-selected',String(button.dataset.tab===name));for(const panel of document.querySelectorAll('.analysis-panel'))panel.hidden=panel.id!==name;}
function bounds(points,pad=1){const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);return{x:Math.min(...xs)-pad,y:Math.min(...ys)-pad,w:Math.max(...xs)-Math.min(...xs)+2*pad,h:Math.max(...ys)-Math.min(...ys)+2*pad};}
function fitRect(rect){const r=$('viewer').getBoundingClientRect(),aspect=Math.max(.1,r.width/r.height),cx=rect.x+rect.w/2,cy=rect.y+rect.h/2;
  let w=Math.max(rect.w,1),h=Math.max(rect.h,1);if(w/h<aspect)w=h*aspect;else h=w/aspect;writeBox({x:cx-w/2,y:cy-h/2,w,h});}
function fit(){if(!board)return;const [x,y,w,h]=board.outline;fitRect({x:x-2,y:y-2,w:w+4,h:h+4});}
function writeBox(next){box=next;$('viewer').setAttribute('viewBox',[box.x,box.y,box.w,box.h].join(' '));
  $('view-state').textContent=fmt($('viewer').clientWidth/box.w,1)+' px/mm · '+$('layer').value+($('mirror').checked?' · physical bottom':' · top coordinates');drawAnnotations();}
function mirrorX(x){return $('mirror').checked?2*board.outline[0]+board.outline[2]-x:x;}
function nativePoint(p){return {x:mirrorX(p.x),y:p.y};}
function focusNative(rect){const x=$('mirror').checked?mirrorX(rect.x+rect.w):rect.x;fitRect({...rect,x});$('viewer').scrollIntoView({block:'center',behavior:'auto'});}
function centerZoom(factor){if(box)writeBox(V.zoomBox(box,factor,{x:box.x+box.w/2,y:box.y+box.h/2},{min:.7,max:1000}));}
function historyState(){const params=new URLSearchParams();params.set('board',board.slug);params.set('layer',$('layer').value);if(selected?.kind==='finding')params.set('finding',selected.id);history.replaceState(null,'','#'+params.toString());}
function updateModel(){const cx=board.outline[0]+board.outline[2]/2;$('model').setAttribute('transform',$('mirror').checked?'translate('+(2*cx)+' 0) scale(-1 1)':'');drawAnnotations();}
function imageFrame(el){const [x,y,w,h]=board.frame;for(const [k,v]of Object.entries({x,y,width:w,height:h}))el.setAttribute(k,v);}
function loadLayers(){if(!board)return;const current=++token,layer=$('layer').value,other=$('compare').value,guide=$('guide').value;
  $('loading').hidden=false;$('loading').textContent='Loading '+layer+' from the verified snapshot…';$('viewer').style.visibility='hidden';
  const entries=[['copper',layer],['comparison',other],['drawing-guide',guide]];
  const pending=entries.filter(([,name])=>name);let loaded=0,failed=false;
  for(const [id,name]of entries){const el=$(id);imageFrame(el);if(!name){el.removeAttribute('href');continue;}
    const source=board.plots[name];if(!source){failed=true;$('loading').textContent='This native plot is not available: '+name;continue;}
    const probe=new Image();probe.onload=()=>{if(current!==token)return;el.setAttribute('href',source);loaded++;if(loaded===pending.length&&!failed){$('loading').hidden=true;$('viewer').style.visibility='visible';}};
    probe.onerror=()=>{if(current!==token)return;failed=true;$('loading').textContent='Native layer failed to load. Reopen index.html from the extracted bundle.';};probe.src=source;
  }
  updateModel();historyState();
}
function drawAnnotations(){if(!board||!box)return;
  const highlight=$('net-highlight'),selection=$('selection'),marks=$('issue-markers'),refs=$('reference-labels');
  highlight.replaceChildren();selection.replaceChildren();marks.replaceChildren();refs.replaceChildren();
  const active=new Set([$('layer').value,$('compare').value]),scale=box.w/Math.max(1,$('viewer').clientWidth);
  if(selectedNet){for(const t of board.tracks){if(t.net!==selectedNet||!active.has(t.layer))continue;
    if(t.kind==='arc'){svg('rect',{x:t.bounds[0],y:t.bounds[1],width:t.bounds[2],height:t.bounds[3],fill:'none',stroke:'#bd244c','stroke-width':1.7,'vector-effect':'non-scaling-stroke'},highlight);}
    else svg('line',{x1:t.a[0],y1:t.a[1],x2:t.b[0],y2:t.b[1],stroke:'#bd244c','stroke-width':t.width,'stroke-opacity':.65},highlight);
  }for(const c of board.components)for(const p of c.pads)if(p.net===selectedNet)svg('circle',{cx:p.at[0],cy:p.at[1],r:4*scale,fill:'none',stroke:'#bd244c','stroke-width':1.8,'vector-effect':'non-scaling-stroke'},highlight);}
  if(selected?.bounds){const [x,y,w,h]=selected.bounds;svg('rect',{x:x-.3,y:y-.3,width:w+.6,height:h+.6,fill:'none',stroke:'#bd244c','stroke-width':2,'stroke-dasharray':'4 3','vector-effect':'non-scaling-stroke'},selection);}
  const visible=board.findings.filter(f=>f.kind==='coupling'||f.severity==='error'||f.kind==='craft'&&$('craft-markers').checked||f.severity==='warning'&&$('warning-markers').checked);
  for(const issue of visible){const locus=issuePoint(issue);if(!locus)continue;const color=issue.kind==='craft'?'#1167aa':issue.kind==='coupling'?'#9b35d0':issue.severity==='warning'?'#a86500':'#b51f3d';
    svg('circle',{cx:locus[0],cy:locus[1],r:7*scale,fill:color,'fill-opacity':.16,stroke:color,'stroke-width':1.8,'vector-effect':'non-scaling-stroke'},marks);}
  if($('labels').checked){for(const c of board.components){const x=mirrorX(c.at[0]),y=c.at[1];if(x<box.x||x>box.x+box.w||y<box.y||y>box.y+box.h)continue;
    const text=svg('text',{x,y,'font-size':11*scale,fill:'#153b36',stroke:'#fff','stroke-width':2.5*scale,'paint-order':'stroke','text-anchor':'middle'},refs);text.textContent=c.ref;}}
}
function issuePoint(issue){
  if(issue.kind==='coupling'&&issue.uuids?.length===2){const a=board.tracks.find(t=>t.uuid===issue.uuids[0]),b=board.tracks.find(t=>t.uuid===issue.uuids[1]);
    if(a&&b){const ux=a.b[0]-a.a[0],uy=a.b[1]-a.a[1],vx=b.b[0]-b.a[0],vy=b.b[1]-b.a[1],den=ux*vy-uy*vx;
      if(Math.abs(den)>1e-9){const dx=b.a[0]-a.a[0],dy=b.a[1]-a.a[1],t=(dx*vy-dy*vx)/den,s=(dx*uy-dy*ux)/den;if(t>=0&&t<=1&&s>=0&&s<=1)return[a.a[0]+t*ux,a.a[1]+t*uy];}
      return[(a.a[0]+a.b[0]+b.a[0]+b.b[0])/4,(a.a[1]+a.b[1]+b.a[1]+b.b[1])/4];}}
  return issue.loci?.[0]||null;
}
function renderBoards(){ $('boards').innerHTML=data.boards.map(b=>'<button type="button" data-board="'+esc(b.slug)+'" aria-current="'+(board?.slug===b.slug)+'">'+esc(b.name)+'<small>'+fmt(b.outline[2])+' × '+fmt(b.outline[3])+' mm · '+b.counts.opens+' opens / '+b.counts.errors+' errors</small></button>').join('');}
function renderOverview(){ $('suite-table').innerHTML=table(['Board','Dimensions · mm','Layers','Parts','Nets','Opens','Errors','Warnings','Electrical status'],data.boards.map(b=>[
  '<button type="button" data-board="'+esc(b.slug)+'">'+esc(b.name)+'</button>',fmt(b.outline[2])+' × '+fmt(b.outline[3]),String(b.layers.length),String(b.stats.components),String(b.stats.nets),String(b.counts.opens),String(b.counts.errors),String(b.counts.warnings),esc(b.field_status)]));}
function renderDetails(){const s=board.stats,c=board.counts;
  $('details').innerHTML='<div class="detail-grid"><dl><dt>Native outline dimensions</dt><dd>'+fmt(board.outline[2],3)+' × '+fmt(board.outline[3],3)+' mm; '+fmt(board.thickness_mm,3)+' mm saved board thickness</dd><dt>Physical objects</dt><dd>'+s.components+' components ('+s.populated_components+' populated), '+s.pads+' pads, '+s.nets+' named nets</dd><dt>Routing and copper</dt><dd>'+s.tracks+' track/arc objects, '+s.vias+' vias, '+s.zones+' non-rule copper zones</dd><dt>Track length (does not rate conductors)</dt><dd>'+fmt(s.track_length_mm)+' mm total; '+fmt(s.ground_track_length_mm)+' mm GND trace sum. Plane paths and via barrels are not included.</dd><dt>Saved drill range</dt><dd>'+fmt(s.min_drill_mm,3)+'–'+fmt(s.max_drill_mm,3)+' mm (vias and drilled pads)</dd></dl><dl><dt>Raw native verification</dt><dd>'+c.opens+' opens / '+c.errors+' errors / '+c.warnings+' warnings / '+c.exclusions+' exclusions; measured '+esc(nativeMeasured(board))+'</dd><dt>Electrical coupling</dt><dd>'+esc(board.field_status)+'</dd><dt>Fabrication status</dt><dd>'+esc(board.qualification)+'</dd><dt>Declared process (not a measured qualification)</dt><dd>'+esc(board.declared_profile||'Not declared')+'<br>'+esc(board.properties.CEC_VENDOR_STACKUP||'')+'<br>'+esc(board.properties.CEC_VIA_PROTECTION||'')+'</dd></dl></div><h3>Physical layer stack — source-declared, not re-qualified</h3>'+table(['Layer','Saved label','Declared role','Declared copper · µm','Tracks','Track length · mm','Saved fill islands'],board.layers.map(l=>[esc(l.name),esc(l.label),esc(l.declared_role||'Not declared'),fmt(l.declared_copper_um,2),String(l.tracks),fmt(l.length_mm),String(l.filled_islands)]))+'<details><summary>Board default manufacturing limits (exact-object local rules may override these)</summary><pre>'+esc(JSON.stringify(board.board_default_limits_mm,null,2))+'</pre></details><details><summary>Source provenance and raw native report</summary><p><code>'+esc(board.source)+'</code></p><p>PCB SHA-256 <code>'+esc(board.sha256)+'</code></p><p>Native report SHA-256 <code>'+esc(board.native_report_sha256)+'</code></p><p><a href="'+esc(board.native_report_asset||'')+'" target="_blank" rel="noopener">Raw native DRC JSON</a></p></details>';
  const v=board.native_verification||{},ignored=v.ignored_checks||[];
  const groups={};for(const f of board.findings){const key=f.severity+' / '+f.type;groups[key]=(groups[key]||0)+1;}
  $('details').insertAdjacentHTML('beforeend','<h3>Finding breakdown</h3>'+table(['Severity / type','Count'],Object.entries(groups).sort().map(([key,count])=>[esc(key),String(count)])));
  $('details').insertAdjacentHTML('beforeend','<h3>Native check configuration</h3><p>KiCad '+esc(v.kicad_version||'Not recorded')+' · report timestamp '+esc(v.measured_at||'Not recorded')+' · included severities: '+esc((v.included_severities||[]).join(', ')||'Not recorded')+'</p><p>Zero native errors applies to the saved configuration, not every available check. Configured ignored checks are distinct from explicit DRC exclusions.</p>'+(ignored.length?table(['Configured ignored check','Description'],ignored.map(i=>[esc(typeof i==='string'?i:i.key),esc(i.description||'')])):'<p>No ignored checks recorded in the native report.</p>'));
  const refinement=(data.review_refinements||[]).find(r=>r.board===board.board&&r.candidate_sha256===board.sha256);
  if(refinement)$('details').insertAdjacentHTML('beforeend','<h3>Agent-directed refinement — actual native before / after</h3><p>'+esc(refinement.intent)+'</p><p>Saved centerline: '+fmt(refinement.saved_centerline_mm,6)+' mm. Independent review nonregression only; not fabrication or current-capacity approval.</p><div class="refinement-plots">'+['before','after'].filter(side=>refinement.plots[side]).map(side=>'<figure><figcaption>'+esc(side==='before'?'Before — immutable parent':'After — selected review child')+'</figcaption><img src="'+esc(refinement.plots[side])+'" alt="'+esc(side)+' native copper detail"></figure>').join('')+'</div>');
}
function renderFindings(){const kind=$('finding-filter').value,q=$('finding-search').value.toLowerCase();const rows=board.findings.filter(f=>(kind==='all'||kind==='coupling'&&f.kind==='coupling'||kind==='craft'&&f.kind==='craft'||kind===f.severity)&&JSON.stringify(f).toLowerCase().includes(q));
  $('finding-table').innerHTML=rows.length?table(['Inspect','Class','Finding','Implicated nets / details'],rows.map(f=>['<button type="button" data-finding="'+esc(f.id)+'">Focus</button>','<span class="pill '+(f.kind==='coupling'?'field':f.severity)+'">'+esc(f.kind==='coupling'?'Electrical blocker':f.kind==='craft'?'Route/copper review':f.severity)+'</span>',esc(f.type)+'<br>'+esc(f.description),f.kind==='coupling'?esc(f.nets.join(' ↔ '))+'<br>'+esc(f.layers.join(' / '))+' · '+fmt(f.angle)+'° · parallel '+fmt(f.parallel_mm,3)+' mm':esc(f.items.map(i=>i.description).join(' · '))])):'<p>No matching findings. This does not establish unmeasured electrical or fabrication checks.</p>';
}
function renderComponents(){const q=$('component-search').value.trim().toLowerCase();const refs=board.components.filter(c=>c.ref.toLowerCase().startsWith(q));const rows=q&&refs.length?refs:board.components.filter(c=>[c.ref,c.value,c.footprint,...Object.values(c.fields),...c.pads.map(p=>p.net)].join(' ').toLowerCase().includes(q));
  $('component-table').innerHTML=table(['Reference','Value / part','Footprint','Side / position · mm','Pads'],rows.map(c=>['<button type="button" data-ref="'+esc(c.ref)+'">'+esc(c.ref)+'</button>',esc(c.value)+(c.dnp?' · DNP':'')+'<br><span class="subtle">'+esc(c.fields.MPN||c.fields['Manufacturer Part Number']||c.fields.LCSC||'')+'</span>',esc(c.footprint),c.side+' · '+c.at.map(v=>fmt(v,3)).join(', '),String(c.pads.length)]));}
function renderNets(){const q=$('net-search').value.toLowerCase();const rows=board.nets.filter(n=>JSON.stringify(n).toLowerCase().includes(q));
  $('net-table').innerHTML=table(['Net','Pads','Tracks / vias / zones','Saved track length · mm','Saved width range · mm','Copper layers'],rows.map(n=>['<button type="button" data-net="'+esc(n.name)+'">'+esc(n.name)+'</button>',String(n.pads.length),n.tracks+' / '+n.vias+' / '+n.zones,fmt(n.length_mm),n.widths.length?fmt(n.widths[0],3)+'–'+fmt(n.widths.at(-1),3):'Plane/pads only',esc(n.layers.join(', '))]));}
function pickComponent(ref){const c=board.components.find(c=>c.ref===ref);if(!c)return;selected={kind:'component',ref,bounds:c.bounds};selectedNet='';
  if(c.side==='B'&&$('layer').value==='F.Cu'){$('layer').value='B.Cu';$('mirror').checked=true;loadLayers();}
  $('selection-detail').textContent=c.ref+' · '+c.value+' · '+c.footprint+' · '+c.side+' side';
  $('pin-detail').innerHTML='<h3>'+esc(c.ref)+' · exact saved pinout</h3>'+table(['Pin','Net','Native x, y · mm','Pad size · mm','Drill · mm'],c.pads.map(p=>[esc(p.pin),p.net?'<button type="button" data-net="'+esc(p.net)+'">'+esc(p.net)+'</button>':'Unassigned / no net',p.at.map(v=>fmt(v,4)).join(', '),p.size.map(v=>fmt(v,3)).join(' × '),p.drill.map(v=>fmt(v,3)).join(' × ')]))+'<details><summary>All saved component fields</summary><pre>'+esc(JSON.stringify(c.fields,null,2))+'</pre></details>';
  focusNative({x:c.bounds[0]-3,y:c.bounds[1]-3,w:c.bounds[2]+6,h:c.bounds[3]+6});}
function pickNet(name){const n=board.nets.find(n=>n.name===name);if(!n)return;selected=null;selectedNet=name;
  if(!n.layers.includes($('layer').value)&&n.layers.length){$('layer').value=n.layers.includes('F.Cu')?'F.Cu':n.layers[0];$('mirror').checked=$('layer').value==='B.Cu';loadLayers();}
  $('selection-detail').textContent=name+' · '+n.pads.length+' pads · '+n.tracks+' tracks / '+n.vias+' vias / '+n.zones+' zones. Highlight is a selection aid, not current-capacity proof.';
  $('net-detail').innerHTML='<h3>'+esc(name)+' · saved terminals</h3>'+table(['Component','Pin','Native x, y · mm'],n.pads.map(p=>['<button type="button" data-ref="'+esc(p.ref)+'">'+esc(p.ref)+'</button>',esc(p.pin),p.at.map(v=>fmt(v,4)).join(', ')]));
  const points=n.pads.map(p=>p.at);if(points.length)focusNative(bounds(points,3));else drawAnnotations();}
function pickFinding(id){const f=board.findings.find(f=>f.id===id);if(!f)return;selected={kind:'finding',id};selectedNet='';
  if(f.layers?.length){$('layer').value=f.layers[0];$('compare').value=f.layers[1]||'';$('mirror').checked=$('layer').value==='B.Cu';loadLayers();}
  else if(f.kind==='craft')$('craft-markers').checked=true;
  else if(f.severity==='warning')$('warning-markers').checked=true;
  const focus=issuePoint(f);if(focus)focusNative(bounds([focus],4));
  for(const uid of f.uuids||[]){const t=board.tracks.find(t=>t.uuid===uid);if(t&&t.a&&t.b)svg('line',{x1:t.a[0],y1:t.a[1],x2:t.b[0],y2:t.b[1],stroke:'#9b35d0','stroke-width':2.5,'vector-effect':'non-scaling-stroke'},$('selection'));}
  $('selection-detail').textContent=(f.kind==='coupling'?f.nets.join(' ↔ ')+' · ':'')+f.description+(f.kind==='coupling'?' · '+fmt(f.angle)+'°; projected gap '+fmt(f.gap_mm,3)+' mm (not a native same-layer clearance)':'');historyState();}
function choose(slug,layer){const b=data.boards.find(b=>b.slug===slug)||data.boards[0];board=b;selected=null;selectedNet='';
  $('board-name').textContent=b.name;$('board-role').textContent=b.role;
  $('board-counts').innerHTML=[[b.counts.opens,'opens'],[b.counts.errors,'native errors'],[b.counts.warnings,'warnings'],[b.layers.length,'copper layers'],[b.stats.components,'components'],[b.stats.nets,'nets']].map(([n,label])=>'<div class="metric"><strong>'+n+'</strong><span>'+label+'</span></div>').join('');
  $('layer').innerHTML=b.layers.map(l=>'<option value="'+esc(l.name)+'">'+esc(l.name)+(l.label!==l.name?' · '+esc(l.label):'')+'</option>').join('');
  $('layer').value=b.plots[layer]?layer:'F.Cu';$('mirror').checked=$('layer').value==='B.Cu';
  $('compare').innerHTML='<option value="">None</option>'+b.layers.map(l=>'<option>'+esc(l.name)+'</option>').join('');$('guide').value='';
  $('board-reviewed').checked=Boolean(state().reviewed);$('notes-text').value=state().notes||'';
  $('checklist').innerHTML=checklist.map((label,i)=>'<label><input type="checkbox" data-check="'+i+'" '+(state().checks?.[i]?'checked':'')+'>'+esc(label)+'</label>').join('');
  $('component-search').value='';$('net-search').value='';$('pin-detail').replaceChildren();$('net-detail').replaceChildren();
  $('identity').innerHTML='Exact PCB SHA-256 <code>'+esc(b.sha256)+'</code> · inspection '+esc(data.inspection_date)+' · native verification '+esc(nativeMeasured(b));
  $('selection-detail').textContent='Select a component, net, or finding below. Selection outlines are annotations, not copper.';
  renderBoards();renderDetails();renderFindings();renderComponents();renderNets();fit();loadLayers();}
function clickView(point){const p=nativePoint(point),candidates=board.components.filter(c=>p.x>=c.bounds[0]-.3&&p.x<=c.bounds[0]+c.bounds[2]+.3&&p.y>=c.bounds[1]-.3&&p.y<=c.bounds[1]+c.bounds[3]+.3).sort((a,b)=>a.bounds[2]*a.bounds[3]-b.bounds[2]*b.bounds[3]);if(candidates[0]){setTab('components');pickComponent(candidates[0].ref);}}
function download(name,value){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
try{
  if(!data?.boards?.length||!V)throw new Error('Inspection data or viewport runtime is missing. Extract the complete bundle before opening index.html.');
  $('snapshot').textContent='Inspection '+data.inspection_date+' · native verification '+data.native_verification_date+' · exact saved inputs rechecked';
  $('scope').textContent=data.boards.length+' boards · '+data.totals.opens+' opens · '+data.totals.errors+' native errors · '+data.totals.warnings+' deferred warnings · '+data.boards.reduce((n,b)=>n+b.findings.filter(f=>f.kind==='coupling').length,0)+' recorded EPS coupling blockers. Review snapshot only — not fab approval.';
  renderOverview();
  document.addEventListener('click',event=>{const target=event.target.closest('button');if(!target)return;
    if(target.dataset.board){choose(target.dataset.board);$('board-name').scrollIntoView({block:'start',behavior:'auto'});}
    if(target.dataset.tab)setTab(target.dataset.tab);
    if(target.dataset.ref)pickComponent(target.dataset.ref);
    if(target.dataset.net){setTab('nets');pickNet(target.dataset.net);}
    if(target.dataset.finding)pickFinding(target.dataset.finding);
  });
  $('overview-button').onclick=()=>{$('suite-overview').hidden=!$('suite-overview').hidden;};
  $('layer').onchange=()=>{$('mirror').checked=$('layer').value==='B.Cu';loadLayers();};$('compare').onchange=loadLayers;$('guide').onchange=loadLayers;
  $('mirror').onchange=()=>{updateModel();fit();};$('labels').onchange=drawAnnotations;$('warning-markers').onchange=drawAnnotations;$('craft-markers').onchange=drawAnnotations;
  $('fit').onclick=fit;$('zoom-in').onclick=()=>centerZoom(1.25);$('zoom-out').onclick=()=>centerZoom(.8);
  $('expand').onclick=()=>{document.body.classList.toggle('expanded');$('expand').textContent=document.body.classList.contains('expanded')?'Exit expanded view':'Expand view';requestAnimationFrame(fit);};
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.classList.contains('expanded'))$('expand').click();});
  $('finding-filter').onchange=renderFindings;$('finding-search').oninput=renderFindings;$('component-search').oninput=renderComponents;$('net-search').oninput=renderNets;
  $('board-reviewed').onchange=()=>{state().reviewed=$('board-reviewed').checked;persist();};
  $('checklist').onchange=event=>{if(event.target.dataset.check!==undefined){state().checks[Number(event.target.dataset.check)]=event.target.checked;persist();}};
  $('notes-text').oninput=()=>{state().notes=$('notes-text').value;clearTimeout(saveTimer);saveTimer=setTimeout(persist,300);};
  $('export-notes').onclick=()=>download('cec-suite-review-notes.json',{schema:1,source_receipt_sha256:data.source_receipt_sha256,exported:new Date().toISOString(),reviews});
  V.bind($('viewer'),{read:()=>box,write:writeBox,fit,limits:{min:.7,max:1000},wheelZoom:()=>$('wheel-zoom').checked,
    click:clickView,hover:p=>{p=nativePoint(p);$('coordinates').textContent='Native x '+fmt(p.x,3)+' / y '+fmt(p.y,3)+' mm';}});
  let resizeTimer;new ResizeObserver(()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(box){const r=$('viewer').getBoundingClientRect();writeBox({...box,h:box.w*r.height/r.width});}},80);}).observe($('viewer'));
  const initial=new URLSearchParams(location.hash.slice(1));choose(initial.get('board'),initial.get('layer'));
  if(initial.get('finding')){setTab('findings');pickFinding(initial.get('finding'));}
}catch(error){$('fatal').hidden=false;$('fatal').textContent='Inspection could not start: '+error.message;}
})();
