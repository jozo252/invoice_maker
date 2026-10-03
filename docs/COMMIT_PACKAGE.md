# Jeden Git balík: CRM pilot a pracovný tok elektrikára

**3. 10. 2026.** Tento balík spája zdrojový kód CRM pilota s novým tokom hlavnej aplikácie a bezpečnostnými kontrolami nasadenia. Nevkladá do Gitu databázy, doklady, fotografie, virtuálne prostredia, API kľúče ani zostavené archívy. Commit sám nič nenasadzuje a nemení živé dáta.

Koreňový `backup_inv.db` bol sledovaný už pred týmto balíkom. Commit ho vyberá **iba z Git indexu** a ignoruje ďalšie `.db`; lokálny súbor zostáva zachovaný. Staršia kópia je stále v histórii Gitu, takže toto nie je čistenie vzdialenej histórie.

## Obsah

- CRM pilot: samostatná lokálna/VPS factory, zákazky, poznámky, potvrdené náklady z bločkov, UI a testy. Nasadzovacie skripty sú len zdrojové súbory; v tomto kroku sa nespúšťajú.
- InvoiceMakerAI: dopyt a miesto realizácie → obhliadka → kontrolovaná ponuka → prijatá revízia → zákazka → kontrola faktúry. Doplnky: cenník, nákupný zoznam, priame náklady, odsúhlasené dodatky, súkromné fotky a akčný prehľad.
- Alembic: nad existujúcou revíziou `631e160e6364` nasledujú `d72c913f1b08` → `ea42d6a90b17` → `f36b7c0912da` → `c42f980d7b25` → `b47a19de0c62`. Nové upgrade kroky pridávajú tabuľky a stĺpce; neresetujú dáta.

## Lokálne overenie

- `python -B -m pytest -q`: 94 úspešných testov po zahrnutí produkčných zmien Veduci.
- `node --test tests/job-notes-ui.test.cjs tests/receipt-parser.test.mjs tests/receipt-ui.test.cjs`: 29 úspešných testov.
- Úplný Alembic reťazec prešiel na novej dočasnej SQLite databáze. Samostatný test preveruje zachovanie existujúcich previazaných riadkov a odmietnutie neoznačenej legacy DB.
- Na VPS prešiel upgrade **súkromnej kópie skutočnej produkčnej databázy** z `631e160e6364` na `b47a19de0c62`: zachovaných 99 riadkov v 12 pôvodných tabuľkách. Živá DB zostala na `631e160e6364`, `quick_check=ok`, služba aktívna.
- Čistý archív kódu na VPS prešiel importom aplikácie a GET smoke testom proti migrovanej kópii. Skript `verify_invoice_migration.py` porovnáva zálohu a výsledok iba na čítanie.
- `git diff --check` a kontrola kandidátov na tajomstvá pred commitom.
- `python -B scripts/package_crm_pilot.py --check` prešiel v lokálnom prostredí. OCR binárne súbory sú zámerne ignorované Gitom; na čistom checkoute ich najprv pripraví `scripts/prepare_receipt_ocr.py` podľa `README_CRM.md`.

## Brány pred nasadením hlavnej aplikácie

1. Podľa [presného postupu](DEPLOYMENT_INVOICE.md) vytvoriť konzistentnú súkromnú zálohu živého `instance`, príloh, `.env` a historického `backup_inv.db` počas zastavenia `invoice.service`. Overiť obnovenie v servisnom okne.
2. Skúška migrácie na kópii cieľovej produkčnej DB prešla; po finálnom release commite ju zopakovať a po živej migrácii porovnať zálohu s výsledkom pomocou `verify_invoice_migration.py`. Lokálna stará `instance/invoices.db` je iný legacy súbor a produkciu neblokuje.
3. Nginx na kontrolovanom VPS nepodáva `/static` priamo; Flask blokuje `/static/uploads/jobs/`. Pred nasadením znovu overiť konfiguráciu. Staré súbory ostávajú dostupné iba cez vlastníkom kontrolovanú route; prípadný presun robiť až po inventúre a zálohe.
4. Overiť PDF faktúry, súkromné prílohy a mobilný postup na testovacom účte. Následne skúsiť jednu skutočnú zákazku a merať čas a opravy údajov.

CRM pilot má vlastný nasadzovací postup v [deploy/README.md](../deploy/README.md). Tento Git balík nie je pokyn na spustenie jeho installeru ani na zmenu `invoice.service`.

**Návrat:** Git revert vráti zdrojový kód na vetve. Ak už bola migrovaná databáza, treba samostatne použiť vopred overenú zálohu a kompatibilnú verziu aplikácie; samotný Git revert databázovú schému nevráti.
