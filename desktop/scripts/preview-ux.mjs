// Isolated UI fixture. No production credentials, microphone, CRM writes or external navigation.
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const server=http.createServer(async(req,res)=>{
 try {
 const url=new URL(req.url,'http://localhost');
 if(url.pathname==='/renderer/index.html') {
 const scenario=url.searchParams.get('scenario')||'empty';
 const lang=url.searchParams.get('lang')||'es';
 const html=await fs.readFile(path.join(root,'renderer/index.html'),'utf8');
 const bootstrap=`<script>
 const scenario=${JSON.stringify(scenario)},lang=${JSON.stringify(lang)};
 localStorage.clear();localStorage.setItem('vocify_lang',lang);
 if(scenario!=='login'){localStorage.setItem('vocify_access','fixture-only');localStorage.setItem('vocify_email','demo@example.test');}
 let retried=false,approved=false;
 const memo={id:'fixture-note',createdAt:'2026-09-25T09:23:00Z',status:'pending_review',audioDuration:12,transcript:'Conversación de prueba local.',extraction:{contactName:'Ana — prueba local',summary:'Resumen de prueba local.',nextSteps:['Enviar propuesta']}};
 window.vocifyDesktop={platform:'darwin',permissions:{status:async()=>({platform:'darwin',microphone:'authorized',systemAudio:'authorized'})},capture:{pending:async()=>({items:[]})},shell:{setState:()=>{},resize:()=>{},onCommand:()=>{},openExternal:async(url)=>{document.body.dataset.opened=url;return {ok:true};}},saas:{request:async({path,method,body})=>{
 await new Promise(r=>setTimeout(r,30)); let data={};
 if(path==='/auth/me')data={id:'fixture-user'};
 else if(path.startsWith('/memos?'))data=scenario==='empty'?[]:[memo];
 else if(path==='/today'){
 if(scenario==='error'&&!retried){retried=true;return {ok:false,status:503,error:'Fixture unavailable'};}
 data={items:scenario==='cards'?[{id:'fixture-card',version:1,status:'pending',contact_name:'Ana — prueba local',company_name:'Acme',reason:'Enviar la propuesta acordada',open_url:'https://example.test/contact/ana'}]:[],coverage:{crm_tasks:scenario==='partial'?'unavailable':'complete',intelligence:'complete'}};
 } else if(path.endsWith('/preview'))data={selected_contact:{contact_id:'fixture-contact'},matched_deals:[{deal_id:'fixture-deal',deal_name:'Propuesta Acme',match_confidence:.95}],proposed_updates:[{field_name:'budget',field_label:'Presupuesto',new_value:'2000'}]};
 else if(path.endsWith('/followup'))data={status:'unavailable'};
 else if(path.endsWith('/approve')){approved=true;data={status:'approved'};}
 else if(path==='/memos/fixture-note')data={...memo,status:approved?'approved':'pending_review'};
 return {ok:true,status:200,data};}}};
 </script>`;
 res.writeHead(200,{'Content-Type':'text/html'});res.end(html.replace('<script type="module"',bootstrap+'<script type="module"'));return;
 }
 const base=url.pathname.startsWith('/shared/')?path.resolve(root,'../shared'):root;
 const rel=url.pathname.startsWith('/shared/')?url.pathname.slice('/shared'.length):url.pathname;
 const file=path.resolve(base,'.'+decodeURIComponent(rel));
 if(!file.startsWith(base+path.sep))throw Error('path');
 const data=await fs.readFile(file);const ext=path.extname(file);
 res.writeHead(200,{'Content-Type':({'.js':'text/javascript','.css':'text/css','.png':'image/png','.woff2':'font/woff2'})[ext]||'application/octet-stream'});res.end(data);
 }catch{res.writeHead(404);res.end('Not found');}
});
server.listen(0,'127.0.0.1',()=>console.log(`Fixture only: http://127.0.0.1:${server.address().port}/renderer/index.html?scenario=empty`));
