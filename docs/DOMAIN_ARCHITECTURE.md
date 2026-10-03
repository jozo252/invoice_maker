# Doménový a technický návrh pred implementáciou

**Status:** návrh, nie súčasná schéma. Vychádza z [auditu](INVOICEMAKERAI_AUDIT.md) a [produktovej vízie](PRODUCT_VISION.md). P0/P1 sa majú zavádzať po malých migračných krokoch s testom na kópii databázy. Najprv jedna firma/jeden vlastník; model tímov a ďalších remesiel až po používaní.

## 1. Jeden prípad, dva druhy postupu

Lead predstavuje obchodný prípad pred schválením. Job predstavuje realizáciu. Rýchly servis môže založiť Job bez formálnej Offer, ale musí mať zapísanú odsúhlasenú sadzbu alebo hranicu odhadu. Dlhšia práca má Lead → OfferRevision → Job. Každý aktívny záznam má konkrétne „ďalej spraviť“, dátum a človeka, ktorý za to zodpovedá. Pri fakturácii sa vychádza zo schválenej verzie rozsahu plus odsúhlasených zmien, nie z poslednej editovanej obrazovky.

## 2. Entity a ich životný cyklus

| Entita | Stav dnes / zmena | Jediná zodpovednosť |
| --- | --- | --- |
| User, Company | zachovať | prihlásenie a vystavovateľ; owner_id zostáva hranicou pilotu |
| Client | zachovať | právna identita/kontakt a fakturačná adresa, nie automaticky adresa stavby |
| **Site** | nová P0 | opakovane použiteľné miesto realizácie, adresa, prístupové poznámky; patrí vlastníkovi a klientovi |
| Lead | rozšíriť P0 | pôvodný dopyt, kontakt, typ, zdroj, site_id, stav, ďalší krok a jeho termín; raw text ostáva |
| Offer | zachovať ako hlavičku | číslo, owner, Lead/Client/Site väzba a obchodný stav |
| **OfferRevision** | nová P0 | nemenný JSON snapshot položiek, výpočtu, výluk, meny/DPH a textu dokumentu; verzia a čas odoslania/súhlasu |
| Job | rozšíriť P0 | realizácia nad odsúhlasenou verziou, Client/Site, stav a plánovaná cena; pre servis aj bez Offer |
| JobNote, JobPlan, JobReceipt | zachovať | časovaný terénny text, jednoduchá cena/termín, človekom potvrdený náklad s originálom |
| JobAttachment | zachovať záznam, meniť úložisko | súkromná foto/dokumentácia s miestnosťou, prvkom alebo trasou a poznámkou |
| Invoice, InvoiceItem, InvoiceCounter | zachovať, rozšíriť P1 | daňový doklad a jeho položky, trvalá väzba na Job/OfferRevision, číslo a stav |
| EmailLog | zachovať | audit návrhu/odoslania e-mailu, nie univerzálna história všetkých kanálov |
| **Activity** | nová P1 | obhliadka, servisný termín, etapa, úloha alebo follow-up s časom a stavom; voliteľne User pracovník |
| **JobCost** | nová P1 | potvrdený čas/materiál/doprava/subdodávka/iný náklad v centoch; doklad môže byť zdrojom |
| **Payment** | nová P1/P2 | skutočná úhrada faktúry (suma, dátum, metóda, referencia), aj čiastočná |
| **PriceEntry** | nová až P1 | vlastný materiál alebo pracovná šablóna, zdroj nákupnej ceny a dátum |

Toto je postupný cieľ, nie pokyn založiť všetky nové tabuľky naraz. Nie je potrebná samostatná tabuľka pre Room, Circuit, Contact, MaterialStock, CalendarEvent, Task a Document v P0. Miestnosť/prvok môžu byť kontrolované textové štítky na fotke a položke; okruhy možno neskôr vyčleniť, ak sa opakovane používajú v odovzdaní a rozvádzači. Pri zložitejšom tímovom modeli sa Company nesmie automaticky zameniť za tenant: dnes je vystavovateľ faktúry a User je vlastník záznamu.

## 3. Väzby a invariantu „zadať raz“

- Client má 0–N Site. Lead odkazuje na Client/Site po identifikácii; predtým môže mať pôvodný text a kontakt. Neukladať len meno v Offer bez väzby na overeného Client.
- Lead má 0–N Offer; Offer má 1–N OfferRevision. Iba posledná odoslaná a človekom prijatá revízia môže založiť platenú Job. Odoslaná/odsúhlasená revízia sa nemení; oprava vytvorí novú revíziu. Staré Offer.items zostávajú pri migrácii čitateľné ako historické dáta.
- Na jednu prijatú revíziu najviac jedna Job. Konverzia musí byť idempotentná v DB transakcii, musí overiť owner_id na všetkých referenciách a vrátiť už vytvorenú zákazku pri opakovanom kliknutí. Zmena rozsahu je nový schválený dodatok/snapshot, nie edit pôvodného súhlasu.
- Job môže mať 0–N Invoice, pretože záloha/etapa/konečná faktúra; Invoice má presnú zdrojovú Job/OfferRevision väzbu alebo dôvod samostatného vystavenia. Už vydaný doklad drží snapshot zákazníka a ceny podľa účtovného režimu.
- JobReceipt sa do JobCost započíta najviac raz; opätovné čítanie OCR a koncept bločka nesmú zmeniť potvrdené náklady. Náklad je bez dvojitého započítania. Pri zmene priradenej zákazky sa súčet prepočíta z aktuálneho potvrdeného zdroja.
- Peniaze v nových výpočtoch používať Decimal s explicitným zaokrúhľovaním na 2 miesta alebo celé centy; nikdy nie binary float ako zdroj fakturačnej sumy. Hodiny ukladať ako minúty a internú nákladovú sadzbu snapshotovať v JobCost.
- Ownership platí aj pre nepriamy FK. Overiť, že Lead, Client, Site, Offer, Job, Invoice a vložený doklad patria tomu istému účtu. Databázové FK a uniqueness dopĺňajú aplikačné kontroly; nenahrádzajú ich.

## 4. Kalkulátor, ktorý vie človek skontrolovať

Vstup jednej pracovnej položky: kód/ľudský názov, množstvo, jednotka, odhad minút, interný náklad práce na hodinu, nákupné ceny a množstvá materiálu, ostatný priamy náklad, predajná sadzba alebo cieľová marža, výluky a pôvod ceny. K tomu doprava, subdodávka, rezerva, zľava a DPH na úrovni ponuky podľa krajiny a účtovného nastavenia. Výstup: medzisúčty nákladov, predaj bez dane, daň, celkom, očakávaný hrubý príspevok a marža. Chýbajúca cena materiálu sa zobrazuje ako chýbajúca, nie nula bez upozornenia. Záporné množstvá a nemožné sadzby sa odmietajú.

Čistá funkcia vypočíta výsledok zo vstupného snapshotu. HTTP route len validuje, volá službu, uloží verziu a zobrazí náhľad. AI môže predložiť štruktúrovaný návrh riadkov a otázky k rozsahu; nemá zapisovať cenu alebo stav do DB. Pri každom riadku sa ukáže pôvod (vlastný cenník, posledná nákupná cena s dátumom, manuálne). Vystavená ponuka používateľovi môže byť prehľadne zoskupená, interný detail zostáva dohľadateľný.

## 5. Servisné hranice v existujúcom Flasku

Nie je potrebný microservice alebo nový frontend. Vnútri súčasnej aplikácie majú byť malé aplikačné služby: create_or_link_lead, calculate_quote, send_quote_revision, accept_quote_and_create_job, record_job_cost, draft_invoice_from_job, record_payment. Každá dostane explicitný owner_id a používa jednu transakciu. Routes nesmú medzi sebou volať view funkcie na opätovné použitie pravidiel. Asistent volá presne tieto služby alebo read-only query služby; na side effects má návrh a výslovné potvrdenie.

Súbory musia ísť do súkromného úložiska s owner-filtered endpointom. JobReceipt je použiteľný vzor validácie obrazu a ochrany originálu. Staré URL /static/uploads/jobs sa nesmú len prepísať v databáze; treba inventúru, kópiu na súkromné miesto, kontrolu hashov a plán, kedy prestať servovať verejné originály. Súčasný SQLite je pre jedného vlastníka prijateľný pilot, ak má pravidelné zálohy databázy **aj príloh** a test obnovy. Pri súbežnom používaní viacerých pracovníkov bude potrebné overiť locky, oprávnenia a možno iný DB engine.

## 6. Migračný sled bez straty historických údajov

1. Zálohovať schému, databázu a súbory na testovacej kópii. Zaznamenať Alembic revision a kontrolovať rozdiel medzi lokálnou, pilotnou a produkčnou DB. Nevykonať create_all ani reset na existujúcich dátach.
2. Opraviť dostupné bezpečnostné a odosielacie chyby s regresnými testami. To nemení schému.
3. Pridať nullable Site/Lead/Offer/Job väzby a nové status/next-action polia cez Alembic. Historické mená a adresy neprepísať. Ak sa miesto nedá bezpečne odlíšiť od fakturačnej adresy, označiť na ručnú kontrolu.
4. Pridať OfferRevision a pri starých Offer vytvoriť len migračný historický snapshot označený ako nepotvrdený zdroj. Starý status accepted automaticky nevykladať ako zdokumentovaný súhlas zákazníka.
5. Zaviesť idempotentnú konverziu prijatej ponuky do Job a návrh faktúry s väzbou. Testovať existujúce faktúry bez job_id a opakované konverzie.
6. Následne riešiť private file migration, Activity, JobCost, Payment a PriceEntry podľa priorít. Každú migráciu overiť na anonymizovanej kópii starých dát, pri upgrade aj čítaní starého záznamu; downgrade skúšať len v dočasnej DB.

Neistoty, ktoré potrebujú reálny terénny podklad: podiel servisov bez ponuky, zvyklosť práce s DPH a zálohami, spôsob zaznamenania súhlasu, počet miest na jedného klienta, typy materiálových dokladov a či sa fotky hľadajú podľa miestnosti alebo prvku. Bez týchto odpovedí sa nemá uzamknúť detail schémy P1.
