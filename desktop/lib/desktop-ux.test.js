import {test} from 'node:test';
import assert from 'node:assert/strict';
import {noteRows} from './notes-list.js';
import {todayItemToCard} from './home-hoy.js';
test('history preserves unknown duration and resolves the actual locale input', () => {
 const [row] = noteRows([{id:'x',createdAt:'2026-09-25T09:00:00Z',status:'extracting'}], {lang:{navigatorLanguage:'en-US'}});
 assert.equal(row.minutes,null);
 assert.equal(row.title,'Untitled meeting');
 assert.match(row.when,/Sept/);
 assert.equal(row.statusLabel,'Processing');
});
test('short recordings show seconds instead of zero minutes', () => {
 assert.equal(noteRows([{id:'x',audioDuration:12}],{lang:'es'})[0].durationLabel,'12 s');
});
test('today preserves the person and real action target', () => {
 const card=todayItemToCard({id:'a',contact_name:'Ana',company_name:'Acme',open_url:'https://app.hubspot.com/contacts/123/contact/456',reason:'Enviar propuesta'});
 assert.equal(card.contactName,'Ana'); assert.equal(card.companyName,'Acme'); assert.equal(card.openUrl,'https://app.hubspot.com/contacts/123/contact/456');
});
test('today does not turn unsafe links or CRM task rows into actionable dismissals', () => {
 const card=todayItemToCard({open_url:'javascript:alert(1)',reason:'Call'});
 assert.equal(card.openUrl,null); assert.equal(card.canDismiss,false);
});
