# CRM pilot na existujúcom VPS

Cieľová adresa pilota je `https://invoicemakerai.com/remeselnici/`. Konfigurácia používa vlastnú službu `crm-pilot.service`, Gunicorn na `127.0.0.1:8098`, vlastnú databázu a súkromné bločky. Existujúci InvoiceMaker na porte 8000 používa `invoice.service`. Účet, databáza a prílohy pôvodného InvoiceMakeru sa do pilota nekopírujú.

Tento priečinok obsahuje podklady na nasadenie. Samotné vytvorenie súborov ani balíka neznamená, že je pilot dostupný online.

Serverové čítanie bločkov používa OpenAI API. Pripravovaná oprava `receipt-total-v2` odlišuje novú prečítanú sumu od už uloženej sumy, pridáva metadáta meny a typu dokumentu vrátane pokynu k platbe. Jej testy, nasadenie a spracovanie fotografie treba osobitne overiť a zaznamenať v `DEVELOPMENT_LOG.md`. Nastavený kľúč, skorší test alebo zdravý `/health` toto overenie nenahrádza.

## Priečinky

```text
/srv/crm-pilot/
  releases/<release_id>/   # rozbalený, po nasadení nemenný kód
  current -> releases/<release_id>
  runtimes/<requirements_hash>/  # nemenné Python prostredie; prvých 16 znakov SHA-256
  venv -> runtimes/<requirements_hash>
  shared/                 # crm.sqlite3, private_receipts, pilot-auth.json
    openai-api.key        # súkromný serverový API kľúč, nikdy v archíve vydania
    ai-state.sqlite3      # trvalá cache návrhov a počítadlo AI pokusov
  backups/<release_id>-<suffix>/ # konzistentná záloha dát a pôvodnej konfigurácie
```

Používateľ služby `crm-pilot` má právo zápisu iba do `shared`. Priečinok `shared` má oprávnenia `0700`, prihlasovacie nastavenia `0600`. Hodnota prístupového kódu ani session secret nepatria do kódu, balíka, nginx konfigurácie či systemd jednotky. `pilot-auth.json` vytvorí `crm_pilot.py --init` a obsahuje iba hash kódu (`access_hash`) a session secret (`secret_key`).

AI kľúč má pevné umiestnenie `/srv/crm-pilot/shared/openai-api.key`, oprávnenie `0400` a vlastníka `crm-pilot`. Factory `crm_pilot.create_pilot_app()` ho číta iba ako serverové nastavenie; neimportuje pôvodnú `.env` ani produkčnú factory. `ai-state.sqlite3` je súkromný súbor `0600`. Oba súbory zostávajú mimo `releases`, aktualizácia ich zachová. Konzistentná súkromná záloha celého `shared` obsahuje aj API kľúč, cache a prihlasovacie tajomstvá; takú zálohu nezverejňovať ani nepribaľovať k archívu vydania.

## Lokálna príprava vydania

1. Dokončiť testy CRM vrátane autentifikácie, CSRF, vlastníctva záznamov a práce pod prefixom `/remeselnici`.
2. Pripraviť lokálne OCR súbory podľa `README_CRM.md`.
3. Z koreňa projektu spustiť:

```powershell
.\.venv\Scripts\python.exe -B scripts\package_crm_pilot.py --check
.\.venv\Scripts\python.exe -B scripts\package_crm_pilot.py
```

Archív a manifest vzniknú v ignorovanom priečinku `work`. Manifest obsahuje SHA-256 archívu aj každého zabaleného súboru. Balíček povoľuje iba pilot, modely, rozšírenia, CRM kód vrátane `crm/ai_receipts.py`, šablóny a statické súbory vrátane OCR, závislosti a dokumentáciu. `.env`, API kľúče, lokálne databázy, AI cache, bločky, pôvodné prílohy a virtuálne prostredie nie sú zahrnuté. Chýbajúci OCR engine alebo jazyk zastaví vytvorenie balíka.

## Samostatná konfigurácia AI

API kľúč sa prenáša oddelene od vydania, cez stdin do skontrolovaného `scripts/configure_crm_ai_vps.py`. Helper musí byť prenesený na VPS osobitne, nie vložený do frontend kódu alebo jednotky služby. Najprv preniesť helper, potom spustiť lokálny provisionovací skript:

```powershell
scp -F "$env:USERPROFILE\.ssh\config" scripts/configure_crm_ai_vps.py vps-gallax:/home/adam/crm-pilot-upload/configure_crm_ai_vps.py
.\work\pilot-venv\Scripts\python.exe -B scripts/pipe_crm_ai_key.py --to-ssh
```

Tieto príkazy sú samostatný externý zásah. Spustiť ich iba v rámci už schváleného nastavenia AI pilota. `pipe_crm_ai_key.py --to-ssh` sám spustí SSH cez centrálny `~/.ssh/config` na `vps-gallax`, pošle existujúci projektový kľúč do subprocess stdin a vypíše iba overený výsledok bez hodnoty kľúča. **Nepripájať ďalšie `| ssh` potrubie.** Hodnotu kľúča nevkladať do argumentov príkazu, histórie shellu alebo logu. Bežné nasadenie či aktualizácia existujúci kľúč zachová; provisionovanie sa pri každom vydaní neopakuje.

VPS helper vyžaduje Linux root, overí pevné priečinky a dostupnosť modelu `gpt-4.1-mini-2025-04-14`, bezpečne uloží kľúč a vráti iba stav konfigurácie. Odmietne prepísanie existujúceho odlišného kľúča; rotácia potrebuje osobitný postup. Overenie metadát modelu nie je platené čítanie fotografie a nepreukazuje dostupný kredit pre túto operáciu. Po zmene kľúča treba reštartovať iba `crm-pilot.service`, aby factory načítala nové nastavenie.

AI request smeruje zo servera na OpenAI Responses API. Posiela overenú, orientovanú JPEG kópiu fotografie s dlhšou stranou najviac 2048 pixelov, používa `store: false` a štruktúrovaný výstup. Viditeľné údaje dokladu preto spracúva externý poskytovateľ; originál zostáva súkromne na VPS. `store: false` nevyhlasuje nulovú retenciu, pozrite [OpenAI spracovanie dát](https://developers.openai.com/api/docs/guides/your-data). API je samostatne účtovaná služba, predplatné ChatGPT nenahrádza kredit; spotrebu overovať na API účte a v [cenníku OpenAI API](https://developers.openai.com/api/docs/pricing).

Trvalý `ai-state.sqlite3` uchováva cache podľa vlastníka, SHA-256 fotografie, modelu a verzie pokynov. `receipt-total-v2` mení kľúč cache; návrhy verzie v1 sa preň nepoužijú a netreba kvôli tomu mazať trvalý stav. Existujúce potvrdené náklady sa zmenou verzie neprepisujú. Rezervácia prebieha pred volaním API. Na celý pilot platí najviac 30 rezervovaných pokusov za UTC deň a 6 za minútu, vrátane neúspešných pokusov. Cache nevyvolá ďalší provider request. Rovnaký zlyhaný pokus má odstup 60 sekúnd, rozpracovaný rezervovaný pokus 90 sekúnd. Reštart ani prepnutie vydania limity a cache nevynuluje. Ide o obmedzenie počtu pokusov, nie peňažný strop celého OpenAI účtu.

Návrh v2 odlišuje prečítanú kladnú sumu (`detected_amount`) od sumy použiteľnej ako EUR. Pri chýbajúcej mene UI ponúkne výslovné **Použiť … ako EUR** až na rozhodnutie používateľa; pri rozpoznanej cudzej mene ho neponúkne. AI rozlišuje pokyn k platbe (`payment_instruction`) od faktúry a účtenky. Dátum splatnosti sa nesmie použiť ako dátum dokladu. Pôvod hodnoty pri poli sumy musí ukázať, či ide o nový výsledok čítania, uloženú alebo ručne upravenú hodnotu. AI odpoveď ani prijatie návrhu do formulára nezapisuje náklad; na to zostáva samostatný potvrdený POST s kontrolou revízie.

## Nasadenie cez installer

Na VPS preniesť archív a jeho manifest z `work`, samostatný skontrolovaný skript `scripts/install_crm_pilot_vps.py` a odporúčane aj `tests/test_crm_pilot.py`. Installer ani testy nie sú súčasťou archívu aplikácie. Skript sa spúšťa ako root priamo na Linux VPS; sám sa nepripája cez SSH ani nič nenahráva.

V nasledujúcom príklade nahradiť `YYYYMMDDTHHMMSSffffffZ` identifikátorom pripraveného vydania. Všetky vstupy musia byť absolútne cesty. Najprv spustiť kontrolu bez mutácií:

```sh
archive_path=/home/adam/crm-pilot-upload/crm-pilot-release-YYYYMMDDTHHMMSSffffffZ.tar.gz
manifest_path=/home/adam/crm-pilot-upload/crm-pilot-release-YYYYMMDDTHHMMSSffffffZ.manifest.json
pilot_tests_path=/home/adam/crm-pilot-upload/test_crm_pilot.py
python3 /home/adam/crm-pilot-upload/install_crm_pilot_vps.py \
  --archive "$archive_path" --manifest "$manifest_path" \
  --pilot-tests "$pilot_tests_path"
```

Bez `--apply` skript iba overí archív, manifest, pevné cesty, systemd jednotku, nginx konfiguráciu, kompatibilitu prípadnej pilotnej databázy, voľné miesto a dostupnosť pôvodného InvoiceMakeru. Nevytvára priečinky, používateľa, prostredie ani zámok. Voliteľné testy sa vykonajú až pri nasadení v pripravenom prostredí.

Po úspešnej kontrole a schválení konkrétneho zásahu spustiť:

```sh
python3 /home/adam/crm-pilot-upload/install_crm_pilot_vps.py \
  --archive "$archive_path" --manifest "$manifest_path" \
  --pilot-tests "$pilot_tests_path" --apply
```

Installer pri `--apply` drží rodičovský zámok nasadenia. Overí SHA-256 každého súboru, odmietne odkazy a nepovolené cesty, pripraví nové nemenné vydanie a prostredie odvodené od hash závislostí. Vytvorí vyhradeného používateľa `crm-pilot` iba ak chýba. Pred prepnutím zastaví iba vlastnú CRM službu a uloží konzistentnú zálohu celého `shared`, pôvodnej jednotky, cieľov odkazov a nginx konfigurácie.

Pri prvom nasadení inicializuje vlastnú databázu `shared/crm.sqlite3` a pilotného používateľa. Pri aktualizácii existujúcu databázu a `pilot-auth.json` zachová; inicializáciu ani automatickú migráciu nevykonáva. Nekompatibilná alebo poškodená schéma zastaví nasadenie.

Potom atómovo prepne `current` a `venv`, spustí iba `crm-pilot.service` a overí interný `/health`. Do presnej konfigurácie `/etc/nginx/sites-available/invoicemakerai.com` vloží označený fragment iba do jedinej HTTPS server sekcie. Pred zápisom overí, že konfiguráciu počas stagingu nikto nezmenil. Rovnaký existujúci fragment zachová bez zápisu či reloadu. Pri zmene nasleduje `nginx -t` a až po úspechu reload nginx; DNS, certifikáty a pôvodný proxy na port 8000 zostávajú zachované.

Úspešný výstup je JSON so stavom `healthy`, URL, identifikátorom vydania a cestou zálohy. Pri novom prihlasovaní obsahuje aj `new_access_code`, iba pri prvej inicializácii. Kód nevkladá do URL, súboru vydania ani systemd journalu. Celý tento výstup preto nepublikovať ako bežný log; nový kód odovzdať používateľovi bezpečne a uchovať ho. Pri chybe po inicializácii môže byť nový kód vo výstupe chyby, pretože privátne dáta sa pri rollbacku nemažú.

Samostatné `crm_pilot.py --init` vytvára prístupový kód s prefixom `NOVY_PRISTUPOVY_KOD=...` iba pri prvom init. Installer tento výstup zachytí a vráti vyššie uvedený JSON. Pri existujúcej databáze sa `--init` nesmie používať na aktualizáciu ani reset prihlasovania.

Installer overí verejné HTTPS health, prihlasovaciu stránku, pôvodnú domovskú stránku a nezmenený MainPID `invoice.service`. Po reload nginx čaká na správny verejný health marker najviac 20 sekúnd, pretože starí workers môžu chvíľu obsluhovať pôvodné smerovanie. Až potom povolí štart novej CRM služby po reštarte VPS. Následne ručne overiť prihlásenie, odmietnutie prístupu bez relácie, zákazníka, zákazku, upload a súkromný originál bločka, čítanie a potvrdenie nákladu. Statické súbory a worker musia mať prefix `/remeselnici/`. Pilot neposiela e-maily ani nevolá platobné služby; pri nastavenom AI kľúči volá OpenAI API.

Pre AI vydanie navyše overiť celý postup na schválenom testovacom obrázku: po upload vznikne iba `draft`, AI navrhne predajcu/dátum/hrubú sumu EUR a náklad sa započíta až po ľudskej kontrole. Overiť zachovanie ručne upraveného poľa pri oneskorenej odpovedi, dostupný fallback do OCR v prehliadači, cache bez ďalšieho API pokusu a žiadne automatické AI volanie pri otvorení potvrdeného nákladu. Platený API pokus musí byť súčasťou schváleného rozsahu. Úspech tohto postupu zaznamenať samostatne od úspechu installeru.

Pri oprave v2 doplniť regresiu s predchádzajúcou uloženou sumou a novou AI odpoveďou bez bezpečnej EUR sumy: stará hodnota sa nesmie označiť ako novo prečítaná a bez potvrdeného POST zostane databáza nezmenená. Overiť čitateľnú sumu bez viditeľnej meny, výslovné prevzatie ako EUR, rozpoznanú cudziu menu bez EUR ponuky a pokyn k platbe obsahujúci iba dátum splatnosti. Použiť všeobecné testovacie doklady bez údajov používateľa; ich live QA úspech netvrdiť pred vykonaním kontroly.

Gunicorn má `--no-control-socket`; pilot nepotrebuje jeho administrátorský socket a vyhradený používateľ nemá zapisovateľný domovský priečinok. Jednotka povoľuje trvalý zápis iba do `shared`.

Verejná prevádzková kontrola je `https://invoicemakerai.com/remeselnici/health`; neprihlásený používateľ nesmie dostať CRM dáta ani súkromný originál bločka. Health endpoint samotný autentifikáciu a vlastníctvo dát nepotvrdzuje.

## Ďalšie úpravy

Zmeny sa pripravujú lokálne, testujú a balia do nového vydania. Neupravovať súbory v bežiacom `current` ani pôvodný InvoiceMaker. Každé vydanie má vlastný identifikátor a manifest.

Pri každej úprave zopakovať lokálne testy, `package_crm_pilot.py`, prenos, read-only kontrolu a `install_crm_pilot_vps.py --apply` pre nový archív. `shared/crm.sqlite3`, fotografie, prihlasovanie, API kľúč a `ai-state.sqlite3` zostávajú na pôvodnom mieste; update prepína iba vydanie a prípadne prostredie. Rovnaký hash závislostí znovu používa už overené prostredie, zmenené závislosti dostanú nové. Bežná úprava aplikácie nemení nginx.

Prípadné zmeny schémy najskôr nacvičiť na kópii zálohy. `create_all` nemení existujúce stĺpce; databázová migrácia musí byť explicitná a nie je súčasťou tohto installeru. Zálohu a predchádzajúce vydanie aj prostredie ponechať, kým nie je aktualizácia potvrdená.

Pri chybe installer obnoví vlastné odkazy `current`/`venv`, pôvodnú jednotku a stav CRM služby. Ak menil nginx, obnoví konkrétne pôvodné bytes, overí `nginx -t` a reload. Výstup `rollback_failures` musí byť prázdny; prípadné zlyhanie rollbacku vyriešiť pred ďalším nasadením. Privátne dáta, zálohy, vydania ani prostredia nemaže a `invoice.service` nereštartuje. Ak by sa neskôr vykonala samostatná databázová migrácia, návrat kódu musí doplniť nacvičený návrat kompatibilnej databázy.

## Diagnostika

```sh
systemctl status crm-pilot.service --no-pager
journalctl -u crm-pilot.service -n 80 --no-pager
nginx -t
```

Pri diagnostike nezverejňovať prístupový kód, session secret, API kľúč, fotografie, obsah AI cache či údaje zákazníkov. API chyby sa zobrazujú všeobecne; neposielať do journalu Authorization header, celý provider request alebo raw provider odpoveď. Journal obsahuje prevádzkové logy novej služby; nepoužívať ho ako dôkaz úspešného prihlásenia alebo spracovania bločka bez následného overenia aplikácie.
