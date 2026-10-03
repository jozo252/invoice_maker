/* Financial proposals are tested without a browser, provider calls or keys. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'static/crm/receipt-ui.js'),'utf8')
  .replace(/^import[^\n]+\n/,'')+'\nglobalThis.readForTest=read;';
const payment={vendor:'Synthetic seller',receipt_date:null,amount:null,detected_amount:'108.00',
  currency:null,document_type:'payment_instruction',message:'Synthetic payment proposal',source:'openai',cached:false};
const regular={...payment,receipt_date:'2026-09-16',amount:'18.40',detected_amount:'18.40',currency:'EUR',document_type:'receipt'};

class Element{
  constructor(value=''){this.value=value;this.dataset={};this.listeners={};this.checked=false;this.disabled=false;this.hidden=false;this.textContent='';}
  addEventListener(type,handler){(this.listeners[type]??=[]).push(handler);}
  removeAttribute(){}
  emit(type){let prevented=false;for(const handler of this.listeners[type]??[])handler({preventDefault(){prevented=true;}});return prevented;}
}
function harness({receipt='confirmed',auto='no',preserve='no',ai='yes',amount='1000.00',date='2026-07-29',result=payment,fetch,
  browser={vendor:'Browser seller',date:'2026-09-16',amountCents:1840,currency:'EUR',reason:'Synthetic browser proposal'}}={}){
  const names=['receipt-form','ocr-status','ocr-progress','ocr-button','confirmed','save-receipt','vendor','receipt-date','amount',
    'ocr-text','ocr-result','ocr-engine','amount-proposal','date-proposal','amount-apply-wrap','amount-apply'];
  const elements=Object.fromEntries(names.map(name=>[name,new Element()]));
  elements.amount.value=amount;elements['receipt-date'].value=date;elements['amount-apply-wrap'].hidden=true;
  const form=elements['receipt-form'];
  form.dataset={aiAvailable:ai,receiptStatus:receipt,autoOcr:auto,preserveFields:preserve,
    extractUrl:'/remeselnici/crm/receipts/synthetic/extract',imageUrl:'/remeselnici/crm/receipts/synthetic/original'};
  form.elements={revision:new Element('1'),csrf_token:new Element('synthetic-csrf'),job_id:new Element('2')};
  elements['ocr-engine'].dataset.ocrBase='/remeselnici/static/crm/vendor/ocr';
  let submissions=0,workers=0;const requests=[],windowEvents={};
  form.submit=form.requestSubmit=()=>{submissions++;};
  const Tesseract={PSM:{SINGLE_COLUMN:4},async createWorker(){workers++;return{
    async setParameters(){},async recognize(){return{data:{text:'Synthetic browser text'}};},async terminate(){},
  };}};
  const context=vm.createContext({document:{getElementById:name=>elements[name]},
    window:{Tesseract,addEventListener(type,handler){windowEvents[type]=handler;}},Tesseract,
    fetch:async(url,options={})=>{requests.push({url,options});return fetch?fetch(url,options):{ok:true,async json(){return result;}};},
    AbortController,extractReceipt:()=>browser,
  });
  vm.runInContext(source,context);
  return{context,elements,form,requests,windowEvents,submissions:()=>submissions,workers:()=>workers,
    read:(manual=true)=>context.readForTest({manual})};
}
function deferred(){let resolve;const promise=new Promise(value=>{resolve=value;});return{promise,resolve};}
async function settle(){for(let index=0;index<30;index++)await Promise.resolve();}

test('null AI total leaves old 1000 explicitly unverified, not a successful total',async()=>{
  const h=harness({result:{...payment,detected_amount:null,document_type:'invoice'}});await h.read();
  assert.equal(h.elements.amount.value,'1000.00');
  assert.match(h.elements['amount-proposal'].textContent,/nerozpoznala/);
  assert.match(h.elements['amount-proposal'].textContent,/1000,00 €.*nepotvrdilo/);
  assert.equal(h.elements['amount-apply-wrap'].hidden,true);
  assert.equal(h.elements['save-receipt'].disabled,true);assert.equal(h.submissions(),0);
});
test('unknown-currency payment shows 108, provenance and explicit EUR apply without saving',async()=>{
  const h=harness();await h.read();
  assert.equal(h.elements.amount.value,'1000.00');assert.equal(h.elements['amount-apply-wrap'].hidden,false);
  assert.match(h.elements['amount-proposal'].textContent,/108,00/);
  assert.match(h.elements['amount-proposal'].textContent,/nejde o celkovú sumu faktúry/);
  assert.match(h.elements['amount-proposal'].textContent,/Mena.*nebola potvrdená/);
  assert.equal(h.elements['amount-apply'].textContent,'Použiť 108,00 € (potvrdzujem EUR)');
  h.elements.confirmed.checked=true;h.elements['amount-apply'].emit('click');
  assert.equal(h.elements.amount.value,'108,00');assert.equal(h.elements.confirmed.checked,false);
  assert.equal(h.elements['save-receipt'].disabled,true);assert.equal(h.submissions(),0);assert.equal(h.requests.length,1);
  assert.match(h.elements['amount-proposal'].textContent,/výslovne potvrdili EUR/);
});
test('null issue date keeps old date explicitly unverified and warns about maturity',async()=>{
  const h=harness();await h.read();assert.equal(h.elements['receipt-date'].value,'2026-07-29');
  assert.match(h.elements['date-proposal'].textContent,/nenašla dátum vystavenia/);
  assert.match(h.elements['date-proposal'].textContent,/pôvodný.*nepotvrdilo/);
  assert.match(h.elements['date-proposal'].textContent,/splatnosti.*dátum vystavenia/);
});
test('foreign currency never fills or offers EUR despite a detected positive total',async()=>{
  const h=harness({result:{...payment,currency:'CZK',amount:'108.00'}});await h.read();
  assert.equal(h.elements.amount.value,'1000.00');assert.equal(h.elements['amount-apply-wrap'].hidden,true);
  assert.match(h.elements['amount-proposal'].textContent,/108,00 CZK/);
  assert.match(h.elements['amount-proposal'].textContent,/Nie je to návrh sumy v EUR/);
});
test('credits, other and unknown document types offer no cost candidate',async()=>{
  for(const type of ['credit_note','other',null]){
    const h=harness({result:{...regular,document_type:type}});await h.read();
    assert.equal(h.elements.amount.value,'1000.00');assert.equal(h.elements['amount-apply-wrap'].hidden,true);
    assert.match(h.elements['amount-proposal'].textContent,/nie je podporovaný/);
  }
});
test('manual retry may replace old dirty baseline, but protects edits during current request',async()=>{
  const pending=deferred();const h=harness({fetch:()=>pending.promise});
  h.elements.amount.emit('input');const run=h.read();
  h.elements.amount.value='77,50';h.elements.amount.emit('input');
  pending.resolve({ok:true,async json(){return regular;}});await run;
  assert.equal(h.elements.amount.value,'77,50');assert.match(h.elements['ocr-status'].textContent,/zostali zachované/);
  const retry=harness({result:regular});retry.elements.amount.emit('input');await retry.read();
  assert.equal(retry.elements.amount.value,'18,40');assert.equal(retry.elements.confirmed.checked,false);
});
test('automatic reread preserves a posted form, explicit retry can use a fresh snapshot',async()=>{
  const h=harness({receipt:'draft',preserve:'yes',result:regular});await h.read(false);
  assert.equal(h.elements.amount.value,'1000.00');await h.read(true);
  assert.equal(h.elements.amount.value,'18,40');assert.equal(h.submissions(),0);
});
test('new manual input hides an old candidate; revision changes invalidate its apply',async()=>{
  const h=harness();await h.read();h.elements.amount.value='123,00';h.elements.amount.emit('input');
  assert.equal(h.elements['amount-apply-wrap'].hidden,true);h.elements['amount-apply'].emit('click');
  assert.equal(h.elements.amount.value,'123,00');
  const changed=harness();await changed.read();changed.form.elements.revision.value='2';
  changed.elements['amount-apply'].emit('click');assert.equal(changed.elements.amount.value,'1000.00');
});
test('cancel and pagehide prevent delayed results or old EUR candidates from applying',async()=>{
  const pending=deferred();const h=harness({fetch:()=>pending.promise});const run=h.read();await h.read();
  pending.resolve({ok:true,async json(){return payment;}});await run;
  assert.equal(h.elements.amount.value,'1000.00');assert.equal(h.elements['amount-apply-wrap'].hidden,true);
  const hidden=harness();await hidden.read();hidden.windowEvents.pagehide();hidden.elements['amount-apply'].emit('click');
  assert.equal(hidden.elements.amount.value,'1000.00');
});
test('confirmed never autocalls; explicit manual request carries revision and CSRF',async()=>{
  const h=harness({auto:'yes'});await settle();assert.equal(h.requests.length,0);await h.read();
  assert.deepEqual(JSON.parse(h.requests[0].options.body),{revision:1,manual:true});
  assert.equal(h.requests[0].options.headers['X-CSRFToken'],'synthetic-csrf');
  assert.equal(h.requests[0].options.credentials,'same-origin');
});
test('draft automatic call is manual:false and cannot save automatically',async()=>{
  const h=harness({receipt:'draft',auto:'yes',amount:'',date:'',result:regular});await settle();
  assert.equal(h.elements.amount.value,'18,40');assert.deepEqual(JSON.parse(h.requests[0].options.body),{revision:1,manual:false});
  assert.equal(h.elements['save-receipt'].disabled,true);assert.equal(h.elements.confirmed.checked,false);assert.equal(h.submissions(),0);
});
test('stale 409 clears candidates, leaves old values and never starts browser fallback',async()=>{
  const h=harness({fetch:async()=>({ok:false,status:409,async json(){return{message:'Refresh synthetic record'};}})});
  await h.read();assert.equal(h.elements.amount.value,'1000.00');assert.equal(h.elements['amount-apply-wrap'].hidden,true);
  assert.equal(h.workers(),0);assert.equal(h.elements['ocr-status'].textContent,'Refresh synthetic record');
});
test('browser fallback without explicit currency preserves 1000 until explicit EUR click',async()=>{
  const h=harness({browser:{vendor:'Browser seller',date:'',amountCents:10800,currency:null,reason:'Unknown currency'},
    fetch:async url=>url.endsWith('/extract')?{ok:false,status:503,async json(){return{message:'Unavailable'};}}:{ok:true,async blob(){return{};}}});
  await h.read();assert.equal(h.workers(),1);assert.equal(h.elements.amount.value,'1000.00');
  assert.equal(h.elements['amount-apply-wrap'].hidden,false);assert.match(h.elements['amount-proposal'].textContent,/Prehliadač prečítal.*108,00/);
  h.elements['amount-apply'].emit('click');assert.equal(h.elements.amount.value,'108,00');assert.equal(h.submissions(),0);
});
test('known EUR browser OCR still fills the parsed total and remains a proposal',async()=>{
  const h=harness({ai:'no',fetch:async()=>({ok:true,async blob(){return{};}})});await h.read();
  assert.equal(h.elements.amount.value,'18,40');assert.equal(h.elements['save-receipt'].disabled,true);assert.equal(h.submissions(),0);
});
test('invalid/negative/oversized amount or date never becomes a valid candidate',async()=>{
  for(const detected of ['-108.00','1e6','10000000.01','1 08.00']){
    const h=harness({result:{...payment,detected_amount:detected,receipt_date:'2026-02-31'}});await h.read();
    assert.equal(h.elements.amount.value,'1000.00');assert.equal(h.elements['amount-apply-wrap'].hidden,true);
    assert.equal(h.elements['receipt-date'].value,'2026-07-29');
  }
});
