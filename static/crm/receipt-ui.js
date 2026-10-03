import {extractReceipt} from './receipt-parser.mjs';

const form=document.getElementById('receipt-form');
const status=document.getElementById('ocr-status');
const progress=document.getElementById('ocr-progress');
const button=document.getElementById('ocr-button');
const confirmed=document.getElementById('confirmed');
const save=document.getElementById('save-receipt');
const amountNote=document.getElementById('amount-proposal');
const dateNote=document.getElementById('date-proposal');
const applyWrap=document.getElementById('amount-apply-wrap');
const applyButton=document.getElementById('amount-apply');
const fields=[document.getElementById('vendor'),document.getElementById('receipt-date'),document.getElementById('amount'),form.elements.job_id];
const canUseAI=form.dataset.aiAvailable==='yes';
const edits=new WeakMap(fields.map(field=>[field,0]));
const supportedTypes=new Set(['receipt','invoice','payment_instruction']);
let worker=null,controller=null,running=false,generation=0,saving=false,candidate=null,amountReading='';

function resetConfirmation(){confirmed.checked=false;save.disabled=true;}
function money(value){
  if(typeof value!=='string'||!/^\d{1,8}(?:[.,]\d{1,2})?$/.test(value))return null;
  const [whole,fraction='']=value.replace(',','.').split('.');
  const cents=Number(whole)*100+Number(fraction.padEnd(2,'0'));
  if(cents<=0||cents>1_000_000_000)return null;
  return `${Math.floor(cents/100)},${String(cents%100).padStart(2,'0')}`;
}
function validDate(value){
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value)||value.startsWith('0000'))return null;
  const parsed=new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime())&&parsed.toISOString().slice(0,10)===value?value:null;
}
function originalAmountNote(){
  const value=money(fields[2].value);
  return value?`Vo formulári zostala pôvodná alebo ručne zadaná suma ${value} €; aktuálne čítanie ju nepotvrdilo.`:'Sumu vo formulári aktuálne čítanie nepotvrdilo. Zadajte ju podľa originálu.';
}
function invalidateCandidate(){candidate=null;applyWrap.hidden=true;applyButton.disabled=true;}
function clearProposal(){
  invalidateCandidate();amountReading='';amountNote.textContent=originalAmountNote();
  dateNote.textContent='Dátum vo formulári aktuálne čítanie ešte nepotvrdilo.';
}
for(const field of fields){
  if(form.dataset.preserveFields==='yes')field.dataset.userEdited='yes';
  const edited=()=>{
    edits.set(field,edits.get(field)+1);field.dataset.userEdited='yes';resetConfirmation();
    if(field===fields[2]){
      invalidateCandidate();
      amountNote.textContent=(amountReading?amountReading+' ':'')+'Suma vo formulári bola ručne upravená. Skontrolujte ju podľa originálu.';
    }
    if(field===fields[1])dateNote.textContent='Dátum vo formulári bol ručne upravený. Skontrolujte dátum vystavenia; splatnosť je iný údaj.';
  };
  field.addEventListener('input',edited);field.addEventListener('change',edited);
}
confirmed.addEventListener('change',()=>{save.disabled=!confirmed.checked||running;});
form.addEventListener('submit',event=>{
  if(saving||running||!confirmed.checked){event.preventDefault();return;}
  saving=true;save.disabled=true;save.textContent='Ukladám…';invalidateCandidate();
});

function snapshotFields(){return fields.map(field=>({value:field.value,edit:edits.get(field)}));}
function fillProposal(values,snapshot,manual){
  const written=[false,false,false];let preserved=false;
  for(let index=0;index<3;index++){
    const field=fields[index],value=values[index];
    if(value===null||value===undefined)continue;
    if((!manual&&field.dataset.userEdited==='yes')||edits.get(field)!==snapshot[index].edit||field.value!==snapshot[index].value){preserved=true;continue;}
    field.value=value;written[index]=true;
  }
  resetConfirmation();return {preserved,written};
}
function showProposal({run,receiptDate,amount,detectedAmount,currency,documentType,source,written}){
  invalidateCandidate();
  const reader=source==='openai'?'AI':'Prehliadač';
  const supported=supportedTypes.has(documentType);
  const detected=supported?money(detectedAmount):null;
  const payable=documentType==='payment_instruction';
  const hasEUR=currency==='EUR';
  if(detected){
    amountReading=`${reader} ${source==='openai'?'prečítala':'prečítal'} sumu${payable?' na platbu':''}: ${detected}${currency?' '+currency:''}.`;
    if(payable)amountReading+=' Suma na platbu; nejde o celkovú sumu faktúry.';
    if(currency===null)amountReading+=' Mena na dokumente nebola potvrdená.';
    else if(!hasEUR)amountReading+=' Nie je to návrh sumy v EUR.';
  }else{
    amountReading=supported?`${reader} ${source==='openai'?'nerozpoznala':'nerozpoznal'} spoľahlivú celkovú sumu.`:'Typ dokladu nie je podporovaný na návrh nákladu.';
  }
  amountNote.textContent=amountReading+' '+(written[2]?'Prečítaná suma je vložená do formulára; náklad ešte nebol uložený.':originalAmountNote());
  if(receiptDate){
    dateNote.textContent=source==='openai'?`AI navrhla dátum vystavenia ${receiptDate}.`:`Prehliadač prečítal dátum ${receiptDate}; overte, či ide o dátum vystavenia.`;
    dateNote.textContent+=written[1]?' Skontrolujte ho podľa originálu.':' Vo formulári zostal pôvodný alebo ručne zadaný dátum.';
  }else{
    dateNote.textContent=`${reader} ${source==='openai'?'nenašla':'nenašiel'} dátum vystavenia. `+(fields[1].value?'Dátum vo formulári je pôvodný alebo ručne zadaný; čítanie ho nepotvrdilo. ':'Zadajte dátum podľa originálu. ')+'Dátum splatnosti nepovažujte za dátum vystavenia.';
  }
  // Unknown currency requires the user's explicit EUR choice; never auto-fill it.
  if(detected&&(currency===null||(hasEUR&&!written[2]))){
    candidate={run,revision:form.elements.revision.value,value:detected,unknownCurrency:currency===null,
      edit:edits.get(fields[2]),expectedValue:fields[2].value};
    applyButton.textContent=currency===null?`Použiť ${detected} € (potvrdzujem EUR)`:`Použiť návrh ${detected} € namiesto sumy vo formulári`;
    applyButton.disabled=running;applyWrap.hidden=false;
  }
}
applyButton.addEventListener('click',()=>{
  const selected=candidate;
  if(!selected||running||saving||selected.run!==generation||selected.revision!==form.elements.revision.value
      ||selected.edit!==edits.get(fields[2])||selected.expectedValue!==fields[2].value){invalidateCandidate();return;}
  fields[2].value=selected.value;edits.set(fields[2],edits.get(fields[2])+1);fields[2].dataset.userEdited='yes';
  invalidateCandidate();resetConfirmation();
  amountNote.textContent=amountReading+` Do formulára ste vložili ${selected.value} €`+(selected.unknownCurrency?' a výslovne potvrdili EUR.':'.')+' Náklad ešte nebol uložený; skontrolujte aj predajcu a dátum.';
});

async function readAI(run,snapshot,signal,manual){
  const response=await fetch(form.dataset.extractUrl,{
    method:'POST',credentials:'same-origin',cache:'no-store',signal,
    headers:{'Content-Type':'application/json','X-CSRFToken':form.elements.csrf_token.value},
    body:JSON.stringify({revision:Number(form.elements.revision.value),manual:manual===true}),
  });
  if(!response.ok){
    const error=new Error('AI reading unavailable');error.noFallback=response.status>=400&&response.status<500&&response.status!==429;
    try{const data=await response.json();if(typeof data.message==='string')error.userMessage=data.message;}catch{}
    throw error;
  }
  const result=await response.json();
  if(run!==generation)return;
  if(result.source!=='openai')throw new Error('Invalid AI proposal');
  const vendor=typeof result.vendor==='string'&&result.vendor.trim().length<=120?result.vendor.trim():null;
  const receiptDate=validDate(result.receipt_date);
  const documentType=typeof result.document_type==='string'?result.document_type:null;
  const currency=typeof result.currency==='string'?result.currency:null;
  const amount=currency==='EUR'&&supportedTypes.has(documentType)?money(result.amount):null;
  const {preserved,written}=fillProposal([vendor,receiptDate,amount],snapshot,manual);
  showProposal({run,receiptDate,amount,detectedAmount:result.detected_amount??result.amount,currency,documentType,source:'openai',written});
  const message=typeof result.message==='string'?result.message:'AI navrhla údaje. Skontrolujte ich podľa originálu bločka.';
  status.textContent=message+(preserved?' Ručne zadané údaje zostali zachované.':'');
}

async function readInBrowser(run,snapshot,signal,{afterAIError=false,manual=false}={}){
  progress.value=0;
  status.textContent=afterAIError?'AI čítanie sa nepodarilo. Skúšam čítanie priamo v prehliadači…':'Pripravujem čítanie v prehliadači. Prvý bloček môže trvať dlhšie.';
  if(!window.Tesseract)throw new Error('OCR assets missing');
  const image=await fetch(form.dataset.imageUrl,{credentials:'same-origin',cache:'no-store',signal});
  if(!image.ok)throw new Error('Receipt unavailable');
  const blob=await image.blob();if(run!==generation)return;
  const ocrBase=document.getElementById('ocr-engine').dataset.ocrBase;
  let active=null;
  try{
    active=await Tesseract.createWorker(['slk','eng'],1,{
      workerPath:`${ocrBase}/worker.min.js`,corePath:`${ocrBase}/core`,langPath:`${ocrBase}/lang`,workerBlobURL:false,gzip:true,
      logger:({status:phase,progress:value})=>{if(run===generation&&phase==='recognizing text'){progress.value=Math.round(value*100);status.textContent=`Čítam bloček v prehliadači… ${Math.round(value*100)} %`; }},
    });
    if(run!==generation)return;worker=active;
    await active.setParameters({tessedit_pageseg_mode:Tesseract.PSM.SINGLE_COLUMN,preserve_interword_spaces:'1'});
    const {data}=await active.recognize(blob,{rotateAuto:true},{text:true});if(run!==generation)return;
    const result=extractReceipt(data.text),receiptDate=validDate(result.date);
    const detectedAmount=result.amountCents===null?null:money((result.amountCents/100).toFixed(2));
    const currency=result.currency??null;
    const amount=currency==='EUR'?detectedAmount:null;
    document.getElementById('ocr-text').value=data.text;document.getElementById('ocr-result').textContent=data.text;
    const {preserved,written}=fillProposal([result.vendor||null,receiptDate,amount],snapshot,manual);
    showProposal({run,receiptDate,amount,detectedAmount,currency,documentType:'receipt',source:'browser',written});
    status.textContent=(afterAIError?'AI nebola dostupná; údaje načítal prehliadač. ':'')+result.reason+(preserved?' Ručne zadané údaje zostali zachované.':'');
  }finally{await active?.terminate().catch(()=>{});if(worker===active)worker=null;}
}

async function read({manual=false}={}){
  if(running){
    generation++;controller?.abort();controller=null;
    const active=worker;worker=null;running=false;progress.hidden=true;clearProposal();
    status.textContent='Automatické dopĺňanie je zastavené. Údaje môžete vyplniť ručne podľa fotografie.';
    button.textContent='Načítať údaje znovu';resetConfirmation();await active?.terminate().catch(()=>{});return;
  }
  const run=++generation,snapshot=snapshotFields(),requestController=new AbortController();
  controller=requestController;running=true;clearProposal();resetConfirmation();progress.hidden=false;
  button.textContent='Zastaviť dopĺňanie a zadať ručne';
  try{
    if(canUseAI&&(manual||form.dataset.receiptStatus==='draft')){
      progress.removeAttribute('value');status.textContent='Automatické čítanie cez AI. Údaje môžete zatiaľ vyplniť ručne.';
      try{await readAI(run,snapshot,requestController.signal,manual);}
      catch(error){
        if(run!==generation||requestController.signal.aborted)return;
        if(error.noFallback){clearProposal();status.textContent=error.userMessage||'Bloček sa zmenil alebo nie je dostupný. Obnovte záznam a porovnajte údaje s originálom.';return;}
        await readInBrowser(run,snapshot,requestController.signal,{afterAIError:true,manual});
      }
    }else{await readInBrowser(run,snapshot,requestController.signal,{manual});}
  }catch{if(run===generation){clearProposal();status.textContent='Automatické čítanie sa nepodarilo. Údaje vyplňte ručne podľa fotografie.';}}
  finally{
    if(controller===requestController)controller=null;
    if(run===generation){running=false;progress.hidden=true;button.textContent='Načítať údaje znovu';if(candidate)applyButton.disabled=false;resetConfirmation();}
  }
}
button.addEventListener('click',()=>void read({manual:true}));
window.addEventListener('pagehide',()=>{generation++;controller?.abort();invalidateCandidate();void worker?.terminate().catch(()=>{});});
if(form.dataset.autoOcr==='yes'&&form.dataset.receiptStatus==='draft')void read({manual:false});
