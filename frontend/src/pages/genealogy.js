import {genealogy, datasets} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {esc,fmt,date,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {LotStatus,GenealogyEvent,RecallStatus} from '../constants/enums.js';
const canWrite=()=>session.user.role!=='viewer';
const isAdmin=()=>session.user.role==='admin';
const lotBadge=l=>l.status==='quarantined'
 ?'<span class="badge danger">'+esc(LotStatus.quarantined)+'</span>'
 :'<span class="badge ok">'+esc(LotStatus.active)+'</span>';
const recallBadge=r=>r.status==='completed'
 ?'<span class="badge ok">'+esc(RecallStatus.completed)+'</span>'
 :'<span class="badge warn">'+esc(RecallStatus.propagating)+'</span>';
function lotOptions(lots, exclude){
 const usable=lots.filter(l=>!exclude||!exclude.includes(l.id));
 if(!usable.length)return '<option value="" disabled selected>暂无在库可用货批，请先登记</option>';
 return usable
  .map(l=>'<option value="'+l.id+'">'+esc(l.code+' · '+l.name)+'（可用 '+fmt(l.available_quantity)+' '+esc(l.unit)+(l.status==='quarantined'?' · 已隔离':'')+'）</option>').join('');
}
async function lotPanel(id){
 const [lot,allLots]=await Promise.all([genealogy.lot(id),genealogy.lots()]);
 workspace.lots=allLots;
 const eventRows=lot.genealogy.map(e=>{
  const ins=e.lines.filter(x=>x.direction==='in').map(x=>{
   const l=allLots.find(z=>z.id===x.lot_id);
   return esc(l?l.code:x.lot_id)+' '+fmt(x.quantity)+(x.destination?' → '+esc(x.destination):'');
  }).join('；');
  const outs=e.lines.filter(x=>x.direction==='out').map(x=>{
   const l=allLots.find(z=>z.id===x.lot_id);
   return esc(l?l.code:x.lot_id)+' '+fmt(x.quantity);
  }).join('；');
  return '<tr><td>'+date(e.created_at)+'</td><td><span class="tag">'+esc(GenealogyEvent[e.type]||e.type)+'</span></td><td>'+(ins||'—')+'</td><td>'+(outs||'—')+'</td><td>'+(e.order_code?esc(e.order_code):'—')+'</td></tr>';
 }).join('');
 return '<section class="panel"><div class="section-title"><h2>'+esc(lot.code+' · '+lot.name)+'</h2>'+lotBadge(lot)+'</div>'
  +'<div class="metrics compact-metrics">'
  +[['登记数量',fmt(lot.registered_quantity),lot.unit],['当前可用',fmt(lot.available_quantity),lot.unit],['状态',LotStatus[lot.status],''],['登记时间',date(lot.created_at),'']]
   .map(([k,v,u])=>'<div><span>'+esc(k)+'</span><strong>'+esc(v)+(u?'<small>'+esc(u)+'</small>':'')+'</strong></div>').join('')
  +'</div>'
  +'<h3 class="compact">谱系追查（上下游拆合与出库）</h3>'
  +'<div class="table-wrap"><table><thead><tr><th>时间</th><th>事件</th><th>来源/去向（in）</th><th>产出（out）</th><th>出库单号</th></tr></thead><tbody>'
  +(eventRows||'<tr><td colspan="5">暂无谱系事件</td></tr>')+'</tbody></table></div>'
  +'<p class="hint">沿事件 in→out 边可向上回溯测温登记、向下追踪拆分/合批/出库的全部流向。</p></section>';
}
export async function genealogyPage(id){
 const [lots,events,recalls,dsList]=await Promise.all([
  genealogy.lots(),genealogy.events(),genealogy.recalls(),datasets.list().catch(()=>[])]);
 workspace.lots=lots;
 const activeLots=lots.filter(l=>l.status==='active');
 const lotTable='<div class="table-wrap"><table><thead><tr>'
  +['货批号','名称','登记数量','可用数量','单位','状态','登记时间','追查'].map(h=>'<th>'+h+'</th>').join('')
  +'</tr></thead><tbody>'+lots.map(l=>'<tr'+(l.status==='quarantined'?' class="row-quarantine"':'')+'><td><strong>'+esc(l.code)+'</strong></td><td>'+esc(l.name)+'</td><td>'+fmt(l.registered_quantity)+'</td><td>'+fmt(l.available_quantity)+'</td><td>'+esc(l.unit)+'</td><td>'+lotBadge(l)+'</td><td>'+date(l.created_at)+'</td><td><a class="text-link" href="#/genealogy/'+l.id+'">查看谱系 ↗</a></td></tr>').join('')
  +'</tbody></table></div>';
 const dsOptions=dsList.map(d=>'<option value="'+d.id+'">'+esc(d.name)+'（'+d.rows+' 条测温）</option>').join('');
 const forms='<div class="genealogy-grid">'
  // 登记
  +'<section class="panel"><div class="section-title"><h2>登记测温批次货批</h2></div><form id="lot-form">'
  +'<label>货批名称<input name="name" required minlength="2" placeholder="例如：沪东B线 11 月试剂批"></label>'
  +'<label>货批号（留空自动生成）<input name="code" maxlength="60" placeholder="LOT-…"></label>'
  +'<label>关联测温批次<select name="dataset_id"><option value="">不关联</option>'+dsOptions+'</select></label>'
  +'<div class="parameter-grid"><label>数量<input name="quantity" type="number" step="0.001" min="0.001" required></label>'
  +'<label>单位<input name="unit" value="件" required></label></div>'
  +'<button class="primary" '+(canWrite()?'':'disabled')+'>登记入谱</button></form></section>'
  // 拆分
  +'<section class="panel"><div class="section-title"><h2>拆分</h2><span>从源货批占用可用量</span></div><form id="split-form">'
  +'<label>源货批<select name="source_lot_id" required>'+lotOptions(activeLots)+'</select></label>'
  +'<div id="split-lines" class="line-stack"><div class="qty-line"><select name="target" required>'+lotOptions(activeLots)+'</select><input name="qty" type="number" step="0.001" min="0.001" required placeholder="数量"></div></div>'
  +'<button type="button" class="button small" id="add-split">+ 增加拆分行</button>'
  +'<label class="compact-label">备注<input name="note" placeholder="可选"></label>'
  +'<button class="primary" '+(canWrite()?'':'disabled')+'>执行拆分（超额整单拒绝）</button></form></section>'
  // 合批
  +'<section class="panel"><div class="section-title"><h2>合批</h2><span>合批货物整体隔离</span></div><form id="merge-form">'
  +'<label>新合批名称<input name="output_name" required minlength="2" placeholder="例如：合批 M-07"></label>'
  +'<div class="parameter-grid"><label>新货批号（可选）<input name="output_code" placeholder="MRG-…"></label>'
  +'<label>单位<input name="unit" value="件"></label></div>'
  +'<div id="merge-lines" class="line-stack"><div class="qty-line"><select name="source" required>'+lotOptions(activeLots)+'</select><input name="qty" type="number" step="0.001" min="0.001" required placeholder="数量"></div></div>'
  +'<button type="button" class="button small" id="add-merge">+ 增加来源行</button>'
  +'<label class="compact-label">备注<input name="note" placeholder="可选"></label>'
  +'<button class="primary" '+(canWrite()?'':'disabled')+'>执行合批（超额整单拒绝）</button></form></section>'
  // 出库
  +'<section class="panel"><div class="section-title"><h2>出库</h2><span>与拆合共用可用数量</span></div><form id="outbound-form">'
  +'<label>出库单号<input name="order_code" required minlength="2" placeholder="OUT-…"></label>'
  +'<div id="outbound-lines" class="line-stack"><div class="qty-line"><select name="lot" required>'+lotOptions(activeLots)+'</select><input name="qty" type="number" step="0.001" min="0.001" required placeholder="数量"><input name="destination" required placeholder="去向（医院/仓库）"></div></div>'
  +'<button type="button" class="button small" id="add-outbound">+ 增加出库行</button>'
  +'<label class="compact-label">备注<input name="note" placeholder="可选"></label>'
  +'<button class="primary" '+(canWrite()?'':'disabled')+'>整单出库（超额整单拒绝）</button></form></section>'
  +'</div>';
 // 召回区
 const recallForm='<section class="panel recall-panel"><div class="section-title"><h2>按调查发起召回</h2><span>仅业务负责人</span></div><form id="recall-form">'
  +'<label>召回原因（关联温区调查结论）<input name="reason" required minlength="2" placeholder="例如：沪东B线温区偏离，KS 检验显著"></label>'
  +'<label>涉及货批（可多选，Ctrl/⌘ 多选）<select name="lot_ids" multiple size="5" required>'+lots.map(l=>'<option value="'+l.id+'">'+esc(l.code+' · '+l.name)+(l.status==='quarantined'?' · 已隔离':'')+'</option>').join('')+'</select></label>'
  +'<button class="primary danger" '+(isAdmin()?'':'disabled')+'>确认召回并隔离全部后代</button>'
  +'<p class="hint">确认瞬间冻结涉及货批与当时已出库去向，再沿拆合关系隔离全部后代；合批货物整体隔离。中断后可恢复，重试不重复冻结或通知。</p></form></section>';
 const recallCards=recalls.map(r=>{
  const s=r.summary||{};
  return '<article class="recall-card"><div class="recall-head"><strong>#'+r.id+' '+esc(r.reason)+'</strong>'+recallBadge(r)+'</div>'
   +'<p class="hint">发起 '+esc(r.created_by)+' · '+date(r.created_at)+(r.finished_at?' · 完成 '+date(r.finished_at):' · 传播中')+'</p>'
   +'<div class="metrics compact-metrics">'
   +[['后代货批',s.total_descendants??'—',''],['已隔离',s.quarantined_lots??'—',''],['隔离进度',s.isolation_progress!=null?Math.round(s.isolation_progress*100)+'%':'—',''],['隔离数量',s.quarantined_quantity??'—',''],['出库通知',s.outbound_notifications??'—',''],['通知数量',s.outbound_quantity??'—','']]
    .map(([k,v,u])=>'<div><span>'+esc(k)+'</span><strong>'+esc(v)+(u?'<small>'+esc(u)+'</small>':'')+'</strong></div>').join('')
   +'</div>'
   +(s.destinations&&s.destinations.length?'<p class="hint">已出库去向：'+s.destinations.map(d=>'<span class="tag">'+esc(d)+'</span>').join(' ')+'</p>':'')
   +'<div class="card-actions"><a class="button small" href="#/recalls/'+r.id+'">追查详情 ↗</a>'
   +(r.status!=='completed'?'<button class="button small" data-retry="'+r.id+'">恢复/重试</button>':'')+'</div></article>';
 }).join('');
 const eventTable='<section class="panel"><div class="section-title"><h2>谱系事件流水</h2><span>'+events.length+' 条</span></div><div class="table-wrap"><table><thead><tr><th>时间</th><th>类型</th><th>单号</th><th>明细</th><th>操作人</th></tr></thead><tbody>'
  +events.map(e=>'<tr><td>'+date(e.created_at)+'</td><td><span class="tag">'+esc(GenealogyEvent[e.type]||e.type)+'</span></td><td>'+(e.order_code?esc(e.order_code):'—')+'</td><td>'+e.lines.map(x=>(x.direction==='in'?'占用 ':'产出 ')+fmt(x.quantity)+(x.destination?' → '+esc(x.destination):'')).join('；')+'</td><td>'+esc(e.actor)+'</td></tr>').join('')
  +'</tbody></table></div></section>';
 const detail=id?await lotPanel(Number(id)):'';
 return heading('06 / GOODS GENEALOGY','货物谱系与召回追溯','登记测温批次对应货批，支持拆分、合批与出库共用可用数量；按调查发起召回，冻结当时货批与出库去向并隔离全部后代。')
  +(detail||'')+forms+recallForm
  +'<section class="panel"><div class="section-title"><h2>召回档案</h2><span>'+recalls.length+' 次召回 · 全部后代核对完才显示完成</span></div><div class="recall-list">'+(recallCards||'<p class="empty">尚无召回。由业务负责人从下方选择涉及货批发起。</p>')+'</div></section>'
  +eventTable+lotTableWrap(lotTable);
}
function lotTableWrap(inner){return '<section class="panel"><div class="section-title"><h2>货批台账</h2><span>'+(workspace.lots?.length||0)+' 批</span></div>'+inner+'</section>';}
export async function recallDetailPage(rid){
 const r=await genealogy.recall(rid);
 const lotRows=r.lots.map(x=>{
  const l=x.lot||{};
  return '<tr'+(l.status==='quarantined'?' class="row-quarantine"':'')+'><td>'+esc(l.code||x.lot_id)+'</td><td>'+esc(l.name||'')+'</td><td><span class="tag">'+(x.stage==='root'?'涉及货批':'后代隔离')+'</span></td><td>'+fmt(x.frozen_available)+' '+(l.unit?esc(l.unit):'')+'</td><td>'+(x.quarantined_at?date(x.quarantined_at):'未隔离')+'</td><td>'+lotBadge(l||{})+'</td></tr>';
 }).join('');
 const noteRows=r.notifications.map(n=>'<tr><td>'+date(n.created_at)+'</td><td>'+esc(n.lot_code)+'</td><td>'+(n.order_code?esc(n.order_code):'—')+'</td><td>'+esc(n.destination)+'</td><td>'+fmt(n.quantity)+'</td></tr>').join('');
 return heading('RECALL #'+rid,'召回隔离与出库通知追查','冻结发起瞬间的涉及货批和已出库去向；沿拆合关系隔离全部后代，合批货物整体隔离。','<a class="button" href="#/genealogy">返回谱系 ↩</a>')
  +'<section class="panel"><div class="section-title"><h2>'+esc(r.reason)+'</h2>'+recallBadge(r)+'</div>'
  +'<div class="metrics compact-metrics">'
  +[['状态',RecallStatus[r.status],''],['涉及货批',(r.root_lot_ids||[]).length,''],['后代总数',r.summary.total_descendants,''],['已隔离货批',r.summary.quarantined_lots,''],['隔离进度',Math.round(r.summary.isolation_progress*100)+'%',''],['受影响隔离数量',r.summary.quarantined_quantity,''],['已出库通知',r.summary.outbound_notifications,'条'],['通知出库数量',r.summary.outbound_quantity,'']]
   .map(([k,v,u])=>'<div><span>'+esc(k)+'</span><strong>'+esc(v)+(u?'<small>'+esc(u)+'</small>':'')+'</strong></div>').join('')
  +'</div>'
  +(r.status!=='completed'?'<button class="button" data-retry="'+r.id+'">恢复/重试召回</button>':'<p class="hint">全部后代核对完成，无待隔离货批；重试不会重复冻结或通知。</p>')
  +'</section>'
  +'<section class="panel"><h3>隔离货批与进度</h3><div class="table-wrap"><table><thead><tr><th>货批号</th><th>名称</th><th>层级</th><th>冻结可用量</th><th>隔离时间</th><th>状态</th></tr></thead><tbody>'+lotRows+'</tbody></table></div></section>'
  +'<section class="panel"><h3>已出库去向通知</h3><div class="table-wrap"><table><thead><tr><th>通知时间</th><th>货批号</th><th>出库单号</th><th>去向</th><th>数量</th></tr></thead><tbody>'+(noteRows||'<tr><td colspan="5">无已出库去向</td></tr>')+'</tbody></table></div></section>';
}
function addLine(containerId, html){
 const c=document.querySelector(containerId);
 const div=document.createElement('div');div.className='qty-line';div.innerHTML=html;c.appendChild(div);
}
export function bindGenealogy(refresh){
 const lotSel=()=>lotOptions(workspace.lots||[],[]);
 const addBtn=document.querySelector('#add-split');
 if(addBtn)addBtn.onclick=()=>addLine('#split-lines','<select name="target" required>'+lotSel()+'</select><input name="qty" type="number" step="0.001" min="0.001" required placeholder="数量"><button type="button" class="text-button" data-remove>移除</button>');
 const mergeBtn=document.querySelector('#add-merge');
 if(mergeBtn)mergeBtn.onclick=()=>addLine('#merge-lines','<select name="source" required>'+lotSel()+'</select><input name="qty" type="number" step="0.001" min="0.001" required placeholder="数量"><button type="button" class="text-button" data-remove>移除</button>');
 const outBtn=document.querySelector('#add-outbound');
 if(outBtn)outBtn.onclick=()=>addLine('#outbound-lines','<select name="lot" required>'+lotSel()+'</select><input name="qty" type="number" step="0.001" min="0.001" required placeholder="数量"><input name="destination" required placeholder="去向"><button type="button" class="text-button" data-remove>移除</button>');
 if(!window.__genealogyRemoveBound){
  window.__genealogyRemoveBound=true;
  document.addEventListener('click',e=>{
   const rm=e.target.closest('[data-remove]');
   if(rm)rm.closest('.qty-line').remove();
  });
 }
 const lotForm=document.querySelector('#lot-form');
 if(lotForm)submit(lotForm,async f=>{
  const ds=f.get('dataset_id');
  await genealogy.registerLot({name:f.get('name'),code:f.get('code')||null,dataset_id:ds?Number(ds):null,quantity:Number(f.get('quantity')),unit:f.get('unit')});
  notify('货批已登记入谱');await refresh();
 });
 const splitForm=document.querySelector('#split-form');
 if(splitForm)submit(splitForm,async f=>{
  const targets=f.getAll('target'),qtys=f.getAll('qty');
  await genealogy.split({source_lot_id:Number(f.get('source_lot_id')),outputs:targets.map((t,i)=>({lot_id:Number(t),quantity:Number(qtys[i])})),note:f.get('note')||''});
  notify('拆分完成');await refresh();
 });
 const mergeForm=document.querySelector('#merge-form');
 if(mergeForm)submit(mergeForm,async f=>{
  const srcs=f.getAll('source'),qtys=f.getAll('qty');
  await genealogy.merge({sources:srcs.map((s,i)=>({lot_id:Number(s),quantity:Number(qtys[i])})),output_name:f.get('output_name'),output_code:f.get('output_code')||null,unit:f.get('unit'),note:f.get('note')||''});
  notify('合批完成');await refresh();
 });
 const outForm=document.querySelector('#outbound-form');
 if(outForm)submit(outForm,async f=>{
  const lots2=f.getAll('lot'),qtys=f.getAll('qty'),dests=f.getAll('destination');
  await genealogy.outbound({order_code:f.get('order_code'),lines:lots2.map((l,i)=>({lot_id:Number(l),quantity:Number(qtys[i]),destination:dests[i]})),note:f.get('note')||''});
  notify('出库完成');await refresh();
 });
 const recallForm=document.querySelector('#recall-form');
 if(recallForm)submit(recallForm,async f=>{
  const ids=Array.from(f.getAll('lot_ids')).map(Number);
  if(!ids.length){notify('请选择至少一个涉及货批',true);return;}
  const r=await genealogy.createRecall({reason:f.get('reason'),lot_ids:ids});
  notify(r.status==='completed'?'召回完成，全部后代已隔离':'召回已确认，隔离传播中（可恢复）');
  await refresh();
 });
 document.querySelectorAll('[data-retry]').forEach(b=>b.onclick=async()=>{
  try{const r=await genealogy.retryRecall(b.dataset.retry);notify('重试完成：'+RecallStatus[r.status]);await refresh();}
  catch(e){notify(e.message,true);}
 });
}
