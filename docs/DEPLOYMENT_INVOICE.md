# Nasadenie hlavnej aplikácie InvoiceMakerAI

Stav k 3. 10. 2026: **pripravený kandidát, nie nasadené vydanie**. Tento postup sa týka `invoice.service` na `invoicemakerai.com`. `crm-pilot.service` na `/remeselnici/` má samostatný installer a pri tomto vydaní sa nemení. Zámerne sa nepoužíva `git pull`, automatický `stamp`, `db.create_all` ani mazanie dát.

## Overený východiskový stav

| Kontrola | Výsledok |
| --- | --- |
| Serverový checkout | `/home/adam/invoice_maker`, `main` na `caec0b2` |
| Hlavná služba | `invoice.service`, Gunicorn na `127.0.0.1:8000`, aktívna |
| Pilot | `crm-pilot.service`, samostatne na `127.0.0.1:8098`, aktívny |
| Živá DB | `/home/adam/invoice_maker/instance/invoices.db`, Alembic `631e160e6364` |
| Integrita | `PRAGMA quick_check=ok`, `foreign_key_check=0` |
| Cieľová migrácia | `b47a19de0c62`; skúška na súkromnej kópii skutočnej DB zachovala 99 riadkov v 12 pôvodných tabuľkách |
| Runtime | Python 3.12.3, `pip check` bez chyby, potrebné moduly a `wkhtmltopdf` dostupné |
| Nginx | `/remeselnici/` na 8098, ostatné na 8000; bez priameho `/static` aliasu |
| Voľné miesto | pri kontrole približne 6,2 GB; pred nasadením zmerať znova |

Skúška na kópii overila presné zachovanie všetkých pôvodných stĺpcov, počtov a SHA-256 obsahu riadkov, integritu SQLite a cieľovú revíziu. Lokálny `instance/invoices.db` je **iný, neoznačený legacy súbor** a nepoužíva sa ako podklad produkčnej migrácie. Na skúšobnej kópii bežali aj import aplikácie a GET `/`, `/login`, `/jobs` a zákaz priamej cesty `/static/uploads/jobs/…`.

Na serveri ostal súkromný adresár `/home/adam/invoice-release-rehearsal-dca874f` s Git archívom a tromi kópiami DB z pokusov; iba `migrated-ready.sqlite3` je úspešne migrovaná kópia. Prístup má vlastník `adam` (`0700`), kópie majú `0600`. Nie sú pod webovým koreňom. Neúspešné kópie vznikli pri oprave spúšťania skriptu; živé dáta a služby sa nemenili. Pred ďalším použitím kandidáta ho treba znovu vytvoriť z finálneho commitu.

## Čo vydanie mení

Nový pracovný tok dopyt → obhliadka → ponuka → prijatie → zákazka → faktúra, cenník, nákupný zoznam a priame náklady. Migračný reťazec `631e160e6364` → `d72c913f1b08` → `ea42d6a90b17` → `f36b7c0912da` → `c42f980d7b25` → `b47a19de0c62` pridáva tabuľky a stĺpce. Produkčné zmeny Veduci z `main` sú zahrnuté. `requirements` sa voči `main` nemení. Nginx ani systemd jednotky netreba meniť.

Git diff **odstraňuje `backup_inv.db` z trackovaných súborov**. Je to stará kópia DB; pred aktualizáciou checkoutu ju treba skopírovať do súkromnej zálohy a po fast-forward ju vrátiť do pracovného adresára ako ignorovaný lokálny súbor. Checkout má tiež sedem zmenených trackovaných `__pycache__/*.pyc` a netrackovaný `fix_schema.py`. Pri kontrole to boli jediné cudzie zmeny; neprepisovať ich ani nespúšťať `git clean`.

## Pred nasadením: nový kandidát a skúška na kópii

1. Finálny release commit nahrať do samostatnej vetvy a skontrolovať jeho diff voči aktuálnemu `main`. Na VPS sa neprihlasovať s cieľom upravovať živý checkout, kým nie je hotová skúška.
2. Na VPS urobiť `git fetch origin <release-vetva>` a uložiť plný `target=$(git rev-parse FETCH_HEAD)`. Overiť `git merge-base --is-ancestor HEAD "$target"`. Ak sa produkčný `main` posunul alebo sa zmenili `requirements`, najprv znova zlúčiť a otestovať kandidáta.
3. V súkromnom adresári (`0700`) rozbaliť `git archive "$target"` z lokálneho Git repozitára. Archív nesmie obsahovať `.env`, databázy, kľúče ani nahrané súbory. Tento adresár nesmie byť pod webovým koreňom.
4. Spustiť v čistom archíve s existujúcim serverovým venv:

```sh
cd "$release_dir/code"
/home/adam/invoice_maker/venv/bin/python -B scripts/audit_invoice_db.py /home/adam/invoice_maker/instance/invoices.db
/home/adam/invoice_maker/venv/bin/python -B scripts/preflight_invoice_migration.py \
  --source /home/adam/invoice_maker/instance/invoices.db \
  --copy "$release_dir/migrated.sqlite3"
/home/adam/invoice_maker/venv/bin/python -B scripts/verify_invoice_migration.py \
  --before /home/adam/invoice_maker/instance/invoices.db \
  --after "$release_dir/migrated.sqlite3"
```

`release_dir` musí existovať, byť súkromný (`0700`) a cesta `migrated.sqlite3` nesmie existovať. Pri opakovaní použiť novú cestu. Skripty čítajú originál iba cez SQLite `mode=ro`; `preflight` migruje iba kópiu a ponechá ju na kontrolu. Zastaviť postup pri rozdiele riadkov, porušenom FK, inej revízii alebo chybnom importe. Otestovať prihlásenie, PDF a nový tok na tejto kópii bez odoslania emailu alebo platby. Stav produkčných účtov nemení úspešný testovací GET.

## Krátke servisné okno

Nasledujúci postup vykonať v jednom shelli po záverečnej kontrole `target`, `git status --short`, miesta na disku a úspešnej skúške. Premenné `before`, `target`, `backup_dir` si poznačiť do interného záznamu nasadenia. Ak pribudla iná lokálna zmena, postup zastaviť.

```sh
set -euo pipefail
cd /home/adam/invoice_maker
before=$(git rev-parse HEAD)
test "$before" = caec0b2b122def2d061af0567aa36ffac4e4fd82
git merge-base --is-ancestor "$before" "$target"
test -z "$(git diff --name-only "$before" "$target" -- requirements)"
backup_dir=$(mktemp -d -p /home/adam invoice-backup-XXXXXXXX)
chmod 700 "$backup_dir"
sudo systemctl stop invoice.service
test "$(systemctl is-active invoice.service || true)" != active
cp -a instance uploads .env backup_inv.db __pycache__ "$backup_dir/"
cp -a static/uploads/jobs "$backup_dir/legacy-job-files"
test ! -e fix_schema.py || cp -a fix_schema.py "$backup_dir/"
cmp instance/invoices.db "$backup_dir/instance/invoices.db"
diff -qr instance "$backup_dir/instance"
diff -qr uploads "$backup_dir/uploads"
diff -qr static/uploads/jobs "$backup_dir/legacy-job-files"
git merge --ff-only "$target"
cp -p "$backup_dir/backup_inv.db" backup_inv.db
```

Ak pred `git merge` zlyhá kontrola alebo záloha, znovu spustiť pôvodnú službu bez pokračovania. Pred spustením migrácie skontrolovať, že `.env`, `instance`, `uploads`, staré fotky a `fix_schema.py` zostali na mieste. Git aktualizácia nesmie byť vyriešená pomocou `git reset --hard` bez zachovanej zálohy miestnych súborov.

**Migráciu** spustiť len pri zastavenej hlavnej službe a s explicitnou kontrolou cieľovej cesty:

```sh
PYTHONDONTWRITEBYTECODE=1 venv/bin/python - <<'PY'
from pathlib import Path
from flask_migrate import upgrade
from app import create_app
from extensions import db
app = create_app()
with app.app_context():
    actual = Path(db.engine.url.database).resolve()
    expected = Path('/home/adam/invoice_maker/instance/invoices.db')
    if actual != expected:
        raise RuntimeError(f'Neocakavany ciel DB: {actual}')
    upgrade(directory='migrations', revision='b47a19de0c62')
PY
venv/bin/python -B scripts/verify_invoice_migration.py \
  --before "$backup_dir/instance/invoices.db" \
  --after instance/invoices.db
```

Pri úspechu znovu spustiť iba `invoice.service`, overiť `systemctl is-active invoice.service`, GET `/login`, prihlásenie na testovacom účte, PDF faktúry, súkromnú starú prílohu, nový dopyt/ponuku bez skutočného odoslania, a `crm-pilot.service`. Nginx sa nemení. Prvý reálny dopyt a faktúru kontrolovať ručne. Zálohu ponechať, kým používateľ nepotvrdí živý priechod.

## Ak kontrola zlyhá

Pred opätovným otvorením služby možno vrátiť kód na `before` a DB zo zálohy. Pri rollbacku musí byť `invoice.service` zastavená; najprv uložiť diagnostiku. `git reset --hard "$before"` je prípustný **iba** v tomto konkrétnom rollbacku po overení obsahu súkromnej zálohy. Potom obnoviť `instance`, `uploads`, `static/uploads/jobs`, `.env`, `backup_inv.db`, `__pycache__` a prípadný `fix_schema.py` zo zálohy a skontrolovať SQLite integritu, revíziu `631e160e6364` a pôvodnú stránku pred opätovným štartom. Ak už po štarte vznikli nové zápisy, slepé obnovenie starej DB by ich stratilo; vtedy službu zastaviť a pripraviť samostatný dátový návrat.

Automatický downgrade Alembic ani `git revert` bez databázového návratu tu nie sú bezpečný rollback. Súkromné zálohy a skúšobné kópie nepublikovať, nenahrávať do Gitu a odstrániť až po uzavretí vydania podľa dohodnutej retenčnej doby.
