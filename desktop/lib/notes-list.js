import {resolveUiLang} from '../renderer/shared/ui/i18n.js';
const PENDING = new Set(['pending_review', 'uploading', 'transcribing', 'extracting', 'pending_transcript']);
export function noteRows(memos, {lang = 'es'} = {}) {
 const en=resolveUiLang(lang)==='en';
 return (Array.isArray(memos)?memos:[]).map(m=>{
  const x=m.extraction||{};
  const duration=Number(m.audioDuration);
  const hasDuration=m.audioDuration!=null && Number.isFinite(duration) && duration>0;
  const date=new Date(m.createdAt);
  const status=String(m.status||'');
  const statusLabel=status==='pending_review'?(en?'Needs review':'Por revisar'):
   PENDING.has(status)?(en?'Processing':'Procesando'):
   status==='failed'?(en?'Processing failed':'Error al procesar'):
   status==='approved'?(en?'Saved':'Guardada'):'';
  return {id:String(m.id), title:String(x.contactName||x.companyName||'').trim()||(en?'Untitled meeting':'Reunión sin título'),
   when:Number.isNaN(date.getTime())?'':date.toLocaleString(en?'en-GB':'es-ES',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}),
   minutes:hasDuration?Math.round(duration/60):null,
   durationLabel:hasDuration?(duration<60?`${Math.round(duration)} s`:`${Math.round(duration/60)} min`):'',
   pending:PENDING.has(status),status,statusLabel};
 });
}
export function notesRequestPath(){return '/memos?limit=50';}
