import {test} from 'node:test';
import assert from 'node:assert/strict';
import {reserveDesktopCapture,completeDesktopCapture} from './capture-upload.js';
test('reserve and retry completion keep the server identity and unchanged final content', async()=>{
 const calls=[];let fail=true;
 const request=async(path,options)=>{calls.push({path,body:options.body});if(path==='/captures')return {capture_id:'remote',memo_id:'remote'};if(fail){fail=false;throw Error('offline');}return {memo_id:'remote'};};
 const capture={clientCaptureId:'local',startedAt:'2026-09-25T10:00:00Z',transcript:'Hello',duration:12,turns:[]};
 await Promise.all([reserveDesktopCapture(request,capture),reserveDesktopCapture(request,capture)]);
 await assert.rejects(completeDesktopCapture(request,capture));
 assert.equal((await completeDesktopCapture(request,capture)).memo_id,'remote');
 assert.equal(calls.filter(x=>x.path==='/captures').length,1);
 assert.deepEqual(calls[1],calls[2]);assert.equal(calls[1].path,'/captures/remote/complete');assert.equal(calls[1].body.audio_duration,12);
});
