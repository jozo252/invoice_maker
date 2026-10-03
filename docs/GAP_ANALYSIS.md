# InvoiceMakerAI vs. pracovný systém elektrikára

**Podklady:** [výskum](ELECTRICIAN_WORKFLOW_RESEARCH.md) a [audit lokálneho kódu](INVOICEMAKERAI_AUDIT.md), 3. 10. 2026. Kvalita hodnotí pripravenosť na konkrétny elektro tok, nie všeobecnú kvalitu pôvodnej fakturácie. Časové prínosy nižšie sú hypotézy; bez troch skutočných zákaziek ich nemožno považovať za výsledok.

| Oblasť | Existuje | Kvalita dnes | Zachovať | Upraviť | Nové | Priorita |
| --- | --- | --- | --- | --- | --- | --- |
| Prihlásenie, firma, klient | Áno | Použiteľné pre jedného vlastníka | User, Company, Client, owner filtre | jednotný výber klienta, validácia všetkých FK | — | P0 |
| Prvý kontakt a kvalifikácia | Lead s textom | Slabá: bez telefónu, miesta a ďalšieho kroku | Lead a raw opis | typ dopytu, zdroj, status, follow-up, kontakt | krátky intake odkaz až po internom teste | P0/P1 |
| Miesto realizácie | Adresa len v Client | Nedostatočná: fakturačná ≠ miesto práce | fakturačná adresa | prenášať adresu bez prepisu | Site naviazané na Client, Lead, Job | P0 |
| Obhliadka | JobNote a príloha | Čiastočná; bez termínu, miestnosti a kontroly nejasností | rýchla poznámka, hlas do editovateľného poľa | karta obhliadky, tag miesta, návrh rozsahu | jednoduchá Activity/Visit | P1 |
| Kalkulácia | ručné položky a AI Offer | Slabá pre skutočnú maržu a pôvod cien | Offer, PDF, ručný editor | jeden výpočet v Decimal/centoch, množstvá, práca, materiál, doprava, rezervy, DPH | malé pracovné šablóny a cenové záznamy | P0/P1 |
| Odsúhlasená ponuka | status accepted | Riziková: položky sa dajú meniť po prijatí | číslo a PDF | verzie, zmrazenie schváleného rozsahu, dôkaz súhlasu | QuoteVersion/snapshot | P0 |
| Konverzia do zákazky | Offer môže ukazovať na už založený Job | Opačný smer, nie schválená ponuka → Job | Job a väzbu Offer.job_id | idempotentný prechod s klientom, miestom a cenou | transakčná služba | P0 |
| Plánovanie | JobPlan.due_date | Jediný dátum, bez slotov a kolízií | existujúci termín | týždenný pracovný zoznam | Activity pre obhliadku, servis a etapu; pracovníci neskôr | P1 |
| Realizácia | status, poznámky, prílohy, bločky | Základ existuje | rýchle poznámky a potvrdené doklady | extra práca, čas a materiál s minimom polí | JobCost/JobAction podľa pilotu | P1 |
| Foto dokumentácia | JobAttachment | Verejný súbor, bez miestnosti a trasy | metadáta a staré odkazy po migrácii | súkromné podávanie, miestnosť, prvok, text trasy | foto index a jednoduché štítky | P0 súkromie, P1 tagy |
| Odovzdanie/revízia | všeobecná príloha | Bez elektro štruktúry | prílohy | checklist podľa druhu práce, stav a autor dokladu | balík podkladov; revízna správa ako externý dokument | P2 |
| Rozvádzač/okruhy | Nie | — | — | — | pracovný zoznam okruhov a štítkov až po overení potreby | P2/P3 |
| Materiál/nákup | potvrdené bločky | Náklad áno, potreba/objednávka nie | JobReceipt | job list potrebné/objednané/pripravené/použité | malý katalóg a CSV import, nie sklad | P1 |
| Faktúra | Áno, PDF/e-mail/stavy | Solídny izolovaný základ; tok na zákazku chýba | Invoice, InvoiceItem, PDF, číslovanie | zdroj schválenej ponuky, koncept, stav odoslania a bezpečné opravy | job/quote väzba; Payment neskôr | P0/P1 |
| Platby a upomienky | paid/unpaid, asistentov návrh | Čiastočné | splatnosť a draft | dátum, suma a zdroj skutočnej úhrady | Payment pre zálohy/čiastkové úhrady | P1/P2 |
| Ziskovosť | dohodnutá cena mínus bločky | Zámerne nie zisk | potvrdené centové náklady | ukázať neúplnosť a odhad vs. realitu | náklad práce, doprava, subdodávka | P1 |
| Komunikácia | mail, ReplyBot, EmailLog | Viac oddelených ciest; nie celá história | drafty a owner filtre | posledný kontakt, ďalší krok, jasný výsledok send | ručný záznam telefón/SMS/WhatsApp; integrácie neskôr | P1/P2 |
| AI asistent | Intent router a read tools | Užitočné vyhľadávanie, obmedzený zápis | owner-filtered tools | služby s validáciou, náhľad a potvrdenie | náklady/materiál/ponuky ako úzko definované tools | P2 |
| OCR a hlas | bločky a editovateľný prepis | Dobré hranice potvrdenia v pilote | ručné potvrdenie, OCR cache, čítanie | merať presnosť a čas na reálnych mobiloch | štruktúrovaný návrh z hlasu až po teste | P2/P3 |
| Dashboard | fakturačný dashboard a CRM karty | Oddelené pohľady | jednoduché čísla | zoznam akcií dnes, nie ďalšie grafy | tok prípadov cez jednu kartu | P1 |

## Najdôležitejšie medzery

1. **Jedno zadanie údaja:** teraz sú zákazník a miesto rozpísané ako voľný text v ponuke a ako odlišné Client polia; Job a Invoice ich nemajú cez stabilný obchodný tok. P0 musí spojiť identity a potom ukladať snapshot na právne/účtovné dokumenty. Fakturačná adresa sa nesmie ticho zmeniť na starej vystavenej faktúre po úprave klienta.
2. **Dohoda vs. realita:** schválená ponuka potrebuje nemennú verziu a explicitnú zmenu rozsahu. Inak sa nedá dokázať, či extra práca bola zahrnutá v cene, ani spoľahlivo merať maržu.
3. **Súkromie fotiek:** produkt pre elektro bude obsahovať trasy káblov, pôdorysy a adresy. Starý statický upload je nevhodný ešte pred budovaním vyhľadávania podľa miestnosti.
4. **Pravdivé peniaze:** zostatok po bločkoch nie je zisk. Pracovné hodiny a aspoň jednoduchá interná nákladová sadzba sú podmienkou finančného dashboardu. Ak chýbajú, ukázať neúplnosť.

## Filter návratnosti pre MVP

Predpoklad malého pilotu: 8 dopytov, 4 ponuky, 3 dokončené zákazky mesačne. Pri jednej karte a prenose údajov môže odpadnúť približne 3–8 minút prepisu na dopyt, pri šablónach a transparentnej kalkulácii 15–45 minút na ponuku a pri faktúre z dohodnutého rozsahu 10–25 minút. Sú to **odhadové rozpätia, ktoré sa prekrývajú**; nie sú sľubom úspory a nenahrádzajú meranie. Najväčšia nefinančná hodnota je menej zabudnutých položiek, sporných zmien a stratených fotiek. Riziko nesprávnej ceny je vysoké, preto je kalkulácia deterministická a odoslanie potvrdzuje človek.

**Zamietnuté pre MVP:** úplná synchronizácia všetkých komunikačných kanálov, plný sklad, drag & drop dispečing, automatický technický návrh rozvádzača, automatické určenie metrov kábla z fotky, generovanie revíznej správy a ďalší všeobecný chatbot. Ich údržba a riziko sú vyššie než pravdepodobná úspora pri prvých vlastných zákazkách. Väčšina by sa použila zriedka alebo by vyžadovala odborné overenie.
