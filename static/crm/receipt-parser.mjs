export function parseMoney(value){
const trimmed=String(value??'').trim();if(!/^(?:\d{1,8}|\d{1,3}(?:[ \u00a0]\d{3})+)(?:[,.]\d{1,2})?$/.test(trimmed))return null;
const [whole,decimal='']=trimmed.replace(/[ \u00a0]/g,'').split(/[,.]/);const cents=Number(whole)*100+Number(decimal.padEnd(2,'0'));return Number.isSafeInteger(cents)&&cents<=1000000000?cents:null;
}
export function validDate(value){return /^\d{4}-\d{2}-\d{2}$/.test(value)&&!Number.isNaN(Date.parse(value))&&new Date(value).toISOString().slice(0,10)===value;}
export function extractReceipt(text){
const lines=text.split(/\r?\n/).map(l=>l.trim()).filter(Boolean),norm=s=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase();const candidates=[],eurCandidates=new Set();let unsafe=false;
for(let i=0;i<lines.length;i++){
const label=norm(lines[i]);if(!/\b(CELKOM|CELKOVA SUMA|SPOLU|TOTAL|K UHRADE|NA UHRADU)\b/.test(label))continue;
if(/MEDZISUCET|SUBTOTAL|ZAKLAD|VYDAVOK|VRATENE|HOTOVOST|CASH|CHANGE|ZLAVA|\bDPH CELKOM\b|\bTAX\b/.test(label))continue;
if(/\bDPH\b/.test(label)&&!/S DPH|VRATANE DPH/.test(label))continue;
let line=lines[i];if(!/\d+[,.]/.test(line)&&i+1<lines.length&&/^\s*[-−]?[\d\s.,]+\s*(?:EUR|€|USD|CZK|GBP|PLN|HUF|CHF)?\s*$/i.test(lines[i+1]))line+=' '+lines[i+1];
if(/\b(USD|CZK|GBP|PLN|HUF|CHF|KUS|KS)\b|[$£]/.test(norm(line))){unsafe=true;continue;}
const matches=[...line.matchAll(/[-−]?\d[\d \u00a0]*[,.][\dA-Za-z]+/g)];
for(const match of matches){const cents=parseMoney(match[0]);if(cents!==null&&cents>0&&/[,.]\d{2}$/.test(match[0])){candidates.push(cents);if(/\bEUR\b|€/.test(norm(line)))eurCandidates.add(cents);}else unsafe=true;}
}
const unique=unsafe?[]:[...new Set(candidates)];let date='';
for(let i=0;i<lines.length;i++){const line=lines[i],m=line.match(/\b(\d{1,2})[./](\d{1,2})[./](20\d{2})\b/);if(!m)continue;
const excluded=/\b(SPLATNOSTI?|DUE(?: DATE)?|PAYMENT DUE|DATUM DODANIA|DELIVERY DATE)\b/;
if(excluded.test(norm(line))||(/^\s*\d/.test(line)&&i>0&&excluded.test(norm(lines[i-1]))))continue;
const candidate=`${m[3]}-${m[2].padStart(2,'0')}-${m[1].padStart(2,'0')}`;if(validDate(candidate)){date=candidate;break;}}
const vendor=lines.slice(0,5).find(l=>/[A-Za-zÀ-ž]{3}/.test(l)&&!/DOKLAD|POKLADN|RECEIPT|FAKTURA|DAKUJ|VITAJ/.test(norm(l)))?.slice(0,120)??'';
return{amountCents:unique.length===1?unique[0]:null,currency:unique.length===1&&eurCandidates.has(unique[0])?'EUR':null,date,vendor,reason:unique.length>1?'Bloček obsahuje rozdielne celkové sumy. Zadajte správnu sumu ručne.':unique.length===0?'Celkovú sumu sa nepodarilo spoľahlivo určiť. Zadajte ju ručne.':'Načítané údaje porovnajte s originálom bločka.'};
}
