"""Root-only, opt-in Linux deployment of the isolated CRM pilot.

Default invocation only reads and checks. Nothing touches invoice.service or
its checkout, database, environment or attachments. Run the reviewed script on
the VPS; it intentionally contains no SSH client or upload mechanism.
"""
from __future__ import annotations

import argparse
import configparser
import fcntl
import grp
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import uuid


ROOT = Path('/srv/crm-pilot')
UNIT = Path('/etc/systemd/system/crm-pilot.service')
NGINX = Path('/etc/nginx/sites-available/invoicemakerai.com')
SERVICE = 'crm-pilot.service'
MAIN_SERVICE = 'invoice.service'
ORIGIN = 'https://invoicemakerai.com'
PREFIX = '/remeselnici'
BEGIN = '# BEGIN INVOICEMAKER CRM PILOT'
END = '# END INVOICEMAKER CRM PILOT'
FIXED = {
    'crm_pilot.py', 'models.py', 'extensions.py', 'requirements-crm-pilot.txt',
    'README_CRM.md', 'DEVELOPMENT_LOG.md', 'deploy/crm-pilot.service',
    'deploy/nginx-crm-pilot.conf', 'deploy/README.md',
}
OCR_ROOT = 'static/crm/vendor/ocr/'
REQUIRED = FIXED | {
    'crm/__init__.py', 'crm/routes.py', 'crm/receipts.py', 'crm/ai_receipts.py',
    'templates/crm/base.html', 'templates/crm/login.html', 'templates/crm/detail.html', 'templates/crm/receipt.html',
    'static/crm/crm.css', 'static/crm/job-notes.js', 'static/crm/receipt-ui.js', 'static/crm/receipt-parser.mjs',
    *(OCR_ROOT + name for name in (
        'tesseract.min.js', 'worker.min.js', 'tesseract.min.js.LICENSE.txt',
        'worker.min.js.LICENSE.txt', 'lang/slk.traineddata.gz', 'lang/eng.traineddata.gz')),
    *(f'{OCR_ROOT}core/tesseract-core{variant}.wasm{suffix}'
      for variant in ('', '-lstm', '-simd', '-simd-lstm', '-relaxedsimd', '-relaxedsimd-lstm')
      for suffix in ('', '.js')),
}
EXPECTED_ENV = {
    'CRM_INSTANCE_DIR': '/srv/crm-pilot/shared',
    'CRM_PUBLIC_ORIGIN': ORIGIN,
    'CRM_URL_PREFIX': PREFIX,
    'PYTHONDONTWRITEBYTECODE': '1',
    'PYTHONUNBUFFERED': '1',
}
EXPECTED_EXEC = ('/srv/crm-pilot/venv/bin/gunicorn --workers 1 --threads 4 '
                 '--bind 127.0.0.1:8098 --timeout 60 --access-logfile - '
                 '--error-logfile - --no-control-socket crm_pilot:create_pilot_app()')


class DeployError(Exception):
    pass


def fail(message):
    raise DeployError(message)


def run(arguments, *, timeout=60, cwd=None, environment=None, check=True):
    try:
        result = subprocess.run(arguments, cwd=cwd, env=environment, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        fail(f'Príkaz {Path(arguments[0]).name} sa nepodarilo dokončiť.')
    if check and result.returncode:
        # Subprocess output may contain a first-init access code; never echo it.
        fail(f'Príkaz {Path(arguments[0]).name} skončil s kódom {result.returncode}.')
    return result


def safe_absolute_file(value):
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        fail('Vstupy musia byť absolútne cesty k obyčajným súborom.')
    return path.resolve()


def ensure_fixed_path(path):
    if path.resolve() != path or path.is_symlink():
        fail(f'Pevná cesta nesmie obsahovať symbolický odkaz: {path}')
    if path.exists() and not path.is_dir():
        fail(f'Očakáva sa priečinok: {path}')


def ordinary_file(path):
    if path.is_symlink() or not path.is_file():
        fail(f'Očakáva sa obyčajný súbor: {path}')


def sha(content):
    return hashlib.sha256(content).hexdigest()


def allowed_name(name):
    parts = PurePosixPath(name).parts
    if not parts or name != PurePosixPath(name).as_posix() or '\\' in name:
        return False
    if name.startswith('/') or any(part in {'.', '..', '.env', '__pycache__'} for part in parts):
        return False
    if name in FIXED:
        return True
    suffix = PurePosixPath(name).suffix
    return ((name.startswith('crm/') and suffix == '.py')
            or (name.startswith('templates/crm/') and suffix == '.html')
            or (name.startswith('static/crm/') and suffix in {'.css', '.svg', '.js', '.mjs', '.wasm', '.gz', '.txt'}))


def check_unit(content):
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    try:
        # systemd permits repeated Environment=; combine exactly the reviewed ones.
        text = content.decode('utf-8')
        env_lines = re.findall(r'^Environment=(.*)$', text, re.M)
        environment = dict(line.split('=', 1) for line in env_lines)
        text = re.sub(r'^Environment=.*\n?', '', text, flags=re.M)
        parser.read_string(text)
    except (UnicodeError, ValueError, configparser.Error):
        fail('Neplatná systemd jednotka v balíku.')
    expected_service = {
        'Type': 'simple', 'User': 'crm-pilot', 'Group': 'crm-pilot',
        'WorkingDirectory': '/srv/crm-pilot/current', 'ExecStart': EXPECTED_EXEC,
        'Restart': 'on-failure', 'RestartSec': '3', 'TimeoutStopSec': '30',
        'UMask': '0077', 'NoNewPrivileges': 'true', 'PrivateTmp': 'true',
        'ProtectSystem': 'strict', 'ProtectHome': 'true',
        'PrivateDevices': 'true', 'RestrictSUIDSGID': 'true', 'CapabilityBoundingSet': '',
        'TasksMax': '64', 'MemoryMax': '512M', 'LimitNOFILE': '4096',
        'ReadWritePaths': '/srv/crm-pilot/shared',
        'StandardOutput': 'journal', 'StandardError': 'journal',
    }
    if (environment != EXPECTED_ENV or len(env_lines) != len(EXPECTED_ENV)
            or set(parser.sections()) != {'Unit', 'Service', 'Install'}
            or dict(parser['Service']) != expected_service
            or dict(parser['Unit']) != {'Description': 'InvoiceMaker CRM pilot for craftspeople', 'After': 'network.target'}
            or dict(parser['Install']) != {'WantedBy': 'multi-user.target'}):
        fail('Jednotka sa líši od pevne ohraničenej CRM konfigurácie.')


def canonical_nginx(text):
    return '\n'.join(line.strip() for line in text.splitlines()
                     if line.strip() and not line.lstrip().startswith('#'))


EXPECTED_SNIPPET = '''location = /remeselnici {
    return 308 /remeselnici/;
}
location ^~ /remeselnici/ {
    client_max_body_size 9m;
    proxy_pass http://127.0.0.1:8098/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /remeselnici;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header Forwarded "";
    proxy_set_header Connection "";
    proxy_read_timeout 70s;
    proxy_redirect off;
}'''


def load_package(archive, manifest_path):
    if archive.stat().st_size > 150 * 1024 * 1024 or manifest_path.stat().st_size > 1024 * 1024:
        fail('Balík alebo manifest prekračuje limit.')
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        release_id = manifest['release_id']
        if not re.fullmatch(r'\d{8}T\d{12}Z', release_id):
            fail('Neplatný identifikátor vydania.')
        if manifest['archive'] != archive.name or manifest['archive_sha256'] != sha(archive.read_bytes()):
            fail('Nesedí meno alebo SHA-256 archívu.')
        expected = {}
        for item in manifest['files']:
            name = item['path']
            if (not allowed_name(name) or name in expected or not isinstance(item['size'], int)
                    or not 0 < item['size'] <= 100 * 1024 * 1024
                    or not re.fullmatch(r'[a-f0-9]{64}', item['sha256'])):
                fail('Manifest obsahuje nepovolený alebo duplicitný súbor.')
            expected[name] = item
        if not REQUIRED <= expected.keys() or sum(item['size'] for item in expected.values()) > 300 * 1024 * 1024:
            fail('Balíku chýba potrebný súbor alebo prekračuje rozbalený limit.')
        contents = {}
        with tarfile.open(archive, 'r:gz') as package:
            for member in package:
                if (not member.isfile() or not allowed_name(member.name) or member.name in contents
                        or member.name not in expected or member.size != expected[member.name]['size']):
                    fail('Archív obsahuje nepovolenú cestu, odkaz alebo súbor.')
                content = package.extractfile(member).read()
                if sha(content) != expected[member.name]['sha256']:
                    fail('Nesedí SHA-256 zabaleného súboru.')
                contents[member.name] = content
        if set(contents) != set(expected):
            fail('Obsah archívu a manifestu sa líši.')
        check_unit(contents['deploy/crm-pilot.service'])
        snippet = contents['deploy/nginx-crm-pilot.conf'].decode('utf-8')
        if canonical_nginx(snippet) != canonical_nginx(EXPECTED_SNIPPET):
            fail('Nginx fragment prekračuje pevnú konfiguráciu pilota.')
        return manifest, contents
    except (KeyError, TypeError, ValueError, OSError, tarfile.TarError, UnicodeError):
        fail('Balík alebo manifest sa nedá bezpečne overiť.')


def structural_nginx(text):
    """Preserve offsets, ignoring braces in comments and quoted values."""
    chars = list(text)
    quote = None
    comment = False
    escaped = False
    for index, char in enumerate(text):
        if comment:
            if char == '\n':
                comment = False
            else:
                chars[index] = ' '
            continue
        if quote:
            chars[index] = ' '
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
            chars[index] = ' '
        elif char == '#':
            comment = True
            chars[index] = ' '
    if quote:
        fail('Nginx konfigurácia obsahuje neukončený reťazec.')
    return ''.join(chars)


def nginx_target(original, snippet):
    try:
        text = original.decode('utf-8')
    except UnicodeError:
        fail('Nginx konfigurácia nie je UTF-8.')
    clean = structural_nginx(text)
    blocks = []
    for match in re.finditer(r'\bserver\s*\{', clean):
        depth = 1
        finish = match.end()
        while finish < len(clean) and depth:
            if clean[finish] == '{':
                depth += 1
            elif clean[finish] == '}':
                depth -= 1
            finish += 1
        if depth:
            fail('Nginx server blok je neukončený.')
        segment = clean[match.end():finish - 1]
        if (re.search(r'\blisten\s+[^;]*\b443\b[^;]*;', segment)
                and re.search(r'\bserver_name\s+[^;]*\binvoicemakerai\.com\b[^;]*;', segment)):
            blocks.append((match.end(), finish - 1))
    if len(blocks) != 1:
        fail('Nemožno jednoznačne vybrať HTTPS server invoicemakerai.com.')
    start, finish = blocks[0]
    segment = text[start:finish]
    if BEGIN in text or END in text:
        if text.count(BEGIN) != 1 or text.count(END) != 1 or BEGIN not in segment or END not in segment:
            fail('Nejednoznačné CRM značky v nginx konfigurácii.')
        marker = re.search(r'(?m)^[ \t]*' + re.escape(BEGIN) + r'\n.*?^[ \t]*' + re.escape(END) + r'[^\n]*\n(?:[ \t]*\n)*', text, re.S)
        if not marker or marker.start() < start or marker.end() > finish:
            fail('Nginx CRM fragment nemožno bezpečne nahradiť.')
        if canonical_nginx(marker.group(0)) == canonical_nginx(snippet):
            return original
        insertion_start, insertion_end = marker.span()
    else:
        locations = list(re.finditer(r'(?m)^[ \t]*location\s+/\s*\{', clean[start:finish]))
        if len(locations) != 1 or re.search(r'\blocation\b[^;{]*/remeselnici', clean):
            fail('Nginx má nejednoznačné location / alebo existujúci iný CRM prefix.')
        insertion_start = insertion_end = start + locations[0].start()
    wrapped = '\n'.join('    ' + line if line else '' for line in
                        (BEGIN + '\n' + snippet.strip() + '\n' + END).splitlines()) + '\n\n'
    return (text[:insertion_start] + wrapped + text[insertion_end:]).encode('utf-8')


def service_property(service, name):
    return run(['systemctl', 'show', service, f'--property={name}', '--value']).stdout.strip()


def http_check(url, *, headers=None, health=False, timeout=15):
    try:
        request = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read(128 * 1024)
            if response.status != 200:
                fail('HTTPS alebo interná kontrola nevrátila 200.')
            if health and json.loads(content).get('app') != 'invoicemaker-crm-pilot':
                fail('Health kontrola nevrátila správny CRM marker.')
            return response.status
    except (urllib.error.URLError, ValueError, OSError):
        fail('HTTP kontrola aplikácie zlyhala.')


def wait_health():
    headers = {'Host': 'invoicemakerai.com', 'X-Forwarded-Proto': 'https',
               'X-Forwarded-Prefix': PREFIX}
    deadline = time.monotonic() + 45
    while True:
        try:
            http_check('http://127.0.0.1:8098/health', headers=headers, health=True)
            return
        except DeployError:
            if time.monotonic() >= deadline:
                fail('Nová CRM služba nedosiahla zdravý stav.')
            time.sleep(1)


def wait_public_health():
    # A reload can return before old Nginx workers finish serving their route.
    # Accept only the intended app marker; a 200 from another app is a failure.
    deadline = time.monotonic() + 20
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            fail('Verejná CRM health kontrola nedosiahla zdravý stav do 20 sekúnd.')
        try:
            http_check(ORIGIN + PREFIX + '/health', health=True, timeout=min(4, remaining))
            return
        except DeployError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                fail('Verejná CRM health kontrola nedosiahla zdravý stav do 20 sekúnd.')
            time.sleep(min(1, remaining))


def old_link(path, parent):
    if not path.exists() and not path.is_symlink():
        return None
    if not path.is_symlink():
        fail(f'Očakáva sa spravovaný symbolický odkaz: {path}')
    target = path.resolve(strict=True)
    if not target.is_relative_to(parent) or not target.is_dir():
        fail(f'Odkaz smeruje mimo spravovaných vydaní: {path}')
    return str(target)


def check_database(shared):
    database = shared / 'crm.sqlite3'
    if not database.exists():
        if database.is_symlink():
            fail('Databáza nesmie byť symbolický odkaz.')
        return
    ordinary_file(database)
    try:
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=5) as connection:
            result = connection.execute('PRAGMA quick_check').fetchall()
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            columns = {name: {row[1] for row in connection.execute(f'PRAGMA table_info({name})')}
                       for name in ('job_plans', 'job_receipts', 'job_notes')}
        if result != [('ok',)] or not {'users', 'clients', 'jobs', 'job_plans', 'job_receipts', 'job_notes'} <= tables:
            fail('Existujúca pilotná databáza potrebuje explicitnú opravu alebo migráciu.')
        if (not {'job_id', 'user_id', 'agreed_price_cents', 'due_date'} <= columns['job_plans']
                or not {'id', 'user_id', 'job_id', 'revision', 'sha256', 'amount_cents', 'status'} <= columns['job_receipts']
                or not {'id', 'job_id', 'user_id', 'content', 'note_type', 'created_at'} <= columns['job_notes']):
            fail('Existujúca schéma pilota nie je kompatibilná; automatická migrácia je zakázaná.')
        ordinary_file(shared / 'pilot-auth.json')
    except sqlite3.Error:
        fail('Pilotnú databázu nemožno overiť v režime iba na čítanie.')


def preflight(contents):
    ensure_fixed_path(ROOT)
    ordinary_file(NGINX)
    if UNIT.exists() or UNIT.is_symlink():
        ordinary_file(UNIT)
        check_unit(UNIT.read_bytes())
    for folder in ('releases', 'runtimes', 'shared', 'backups'):
        ensure_fixed_path(ROOT / folder)
    current = old_link(ROOT / 'current', ROOT / 'releases')
    runtime = old_link(ROOT / 'venv', ROOT / 'runtimes')
    original = NGINX.read_bytes()
    desired = nginx_target(original, contents['deploy/nginx-crm-pilot.conf'].decode('utf-8'))
    run(['nginx', '-t'])
    if service_property(MAIN_SERVICE, 'ActiveState') != 'active':
        fail('Pôvodný InvoiceMaker nie je aktívny; nasadenie CRM sa zastavilo.')
    main_pid = service_property(MAIN_SERVICE, 'MainPID')
    if not main_pid.isdigit() or main_pid == '0':
        fail('Pôvodný InvoiceMaker nemá platný MainPID.')
    http_check(ORIGIN + '/')
    check_database(ROOT / 'shared')
    if shutil.disk_usage('/srv').free < 1024 * 1024 * 1024:
        fail('Na staging vydania a prostredia treba aspoň 1 GB voľného miesta.')
    active = service_property(SERVICE, 'ActiveState') == 'active'
    enabled = run(['systemctl', 'is-enabled', SERVICE], check=False).stdout.strip() == 'enabled'
    if active and (not current or not runtime or not UNIT.exists()):
        fail('Existujúca CRM služba nezodpovedá spravovanej konfigurácii.')
    return {'current': current, 'runtime': runtime, 'nginx': original, 'desired_nginx': desired,
            'unit': UNIT.read_bytes() if UNIT.exists() else None, 'active': active,
            'enabled': enabled, 'main_pid': main_pid, 'nginx_mode': stat.S_IMODE(NGINX.stat().st_mode)}


def atomic_bytes(path, content, mode=0o644):
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_link(path, target):
    if path.exists() or path.is_symlink():
        if not path.is_symlink():
            fail(f'Nemožno nahradiť nespravovaný súbor: {path}')
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        temporary.symlink_to(target)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_user():
    try:
        user = pwd.getpwnam('crm-pilot')
    except KeyError:
        run(['useradd', '--system', '--user-group', '--home-dir', '/nonexistent',
             '--shell', '/usr/sbin/nologin', 'crm-pilot'])
        user = pwd.getpwnam('crm-pilot')
    if (user.pw_uid == 0 or user.pw_uid >= 1000 or user.pw_shell not in {'/usr/sbin/nologin', '/sbin/nologin', '/bin/false'}
            or grp.getgrgid(user.pw_gid).gr_name != 'crm-pilot'):
        fail('Existujúci používateľ crm-pilot nie je vyhradený systémový účet.')
    return user


def stage_release(manifest, contents):
    release = ROOT / 'releases' / manifest['release_id']
    ensure_fixed_path(release)
    if release.exists():
        for name, content in contents.items():
            path = release / name
            ordinary_file(path)
            if path.resolve() != path or sha(path.read_bytes()) != sha(content):
                fail('Existujúce vydanie má odlišný alebo nespravovaný obsah.')
        return release
    release.mkdir(mode=0o755)
    for name, content in contents.items():
        path = release / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        atomic_bytes(path, content)
    atomic_bytes(release / '.release-manifest.json', json.dumps(manifest, indent=2).encode('utf-8'))
    return release


def stage_runtime(release):
    requirements = release / 'requirements-crm-pilot.txt'
    digest = sha(requirements.read_bytes())
    runtime = ROOT / 'runtimes' / digest[:16]
    ensure_fixed_path(runtime)
    marker = runtime / '.requirements-sha256'
    if runtime.exists():
        if not marker.is_file() or marker.read_text().strip() != digest:
            fail('Existujúce prostredie nemá platný dokončený kontrolný marker; nebude prepísané.')
    else:
        run(['python3', '-m', 'venv', str(runtime)], timeout=120)
        run([str(runtime / 'bin/python'), '-m', 'pip', 'install', '--disable-pip-version-check',
             '--no-cache-dir', '-r', str(requirements)], timeout=300)
        run([str(runtime / 'bin/python'), '-m', 'pip', 'check'])
        atomic_bytes(marker, (digest + '\n').encode())
    run([str(runtime / 'bin/python'), '-m', 'pip', 'check'])
    return runtime


def optional_tests(tests, release, runtime):
    if not tests:
        return
    program = '''import pathlib,sys,types,unittest
source=pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
module=types.ModuleType("deployment_pilot_tests")
module.__file__=str(pathlib.Path(sys.argv[2])/"tests"/"test_crm_pilot.py")
sys.modules[module.__name__]=module
exec(compile(source,module.__file__,"exec"),module.__dict__)
suite=unittest.defaultTestLoader.loadTestsFromModule(module)
if not suite.countTestCases(): raise SystemExit(2)
result=unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
'''
    environment = os.environ.copy()
    environment.update(PYTHONPATH=str(release), PYTHONDONTWRITEBYTECODE='1')
    run([str(runtime / 'bin/python'), '-B', '-c', program, str(tests), str(release)],
        cwd=release, environment=environment, timeout=120)


def reject_shared_links(shared):
    for path in shared.rglob('*'):
        if path.is_symlink():
            fail('Privátne pilotné dáta nesmú obsahovať symbolické odkazy.')


def initialize_if_needed(release, runtime):
    if (ROOT / 'shared/crm.sqlite3').exists():
        return None
    arguments = ['runuser', '-u', 'crm-pilot', '--', 'env',
                 'CRM_INSTANCE_DIR=/srv/crm-pilot/shared', 'CRM_PUBLIC_ORIGIN=' + ORIGIN,
                 'CRM_URL_PREFIX=' + PREFIX, str(runtime / 'bin/python'), '-B',
                 str(release / 'crm_pilot.py'), '--init']
    output = run(arguments, cwd=release).stdout
    matches = re.findall(r'^NOVY_PRISTUPOVY_KOD=([A-Za-z0-9_-]{20,128})$', output, re.M)
    if len(matches) > 1:
        fail('Inicializácia vrátila nejednoznačný prístupový kód.')
    check_database(ROOT / 'shared')
    return matches[0] if matches else None


def restore_link(path, old):
    if old:
        atomic_link(path, old)
    elif path.is_symlink():
        path.unlink()
    elif path.exists():
        fail('Rollback odmietol odstrániť nespravovaný súbor.')


def rollback(previous, changed):
    failures = []
    if changed.get('nginx'):
        try:
            atomic_bytes(NGINX, previous['nginx'], previous['nginx_mode'])
            run(['nginx', '-t'])
            run(['systemctl', 'reload', 'nginx'])
        except DeployError:
            failures.append('nginx')
    if changed.get('service'):
        try:
            run(['systemctl', 'stop', SERVICE], check=False)
            restore_link(ROOT / 'current', previous['current'])
            restore_link(ROOT / 'venv', previous['runtime'])
            if previous['unit'] is None:
                run(['systemctl', 'disable', SERVICE], check=False)
                if UNIT.is_symlink():
                    fail('Rollback odmietol odstrániť nespravovanú jednotku.')
                UNIT.unlink(missing_ok=True)
            else:
                atomic_bytes(UNIT, previous['unit'])
            run(['systemctl', 'daemon-reload'])
            if previous['unit'] is not None:
                run(['systemctl', 'enable' if previous['enabled'] else 'disable', SERVICE])
                if previous['active']:
                    run(['systemctl', 'start', SERVICE])
        except (DeployError, OSError):
            failures.append('crm-pilot.service')
    return failures


def apply_deployment(manifest, contents, previous, tests):
    changed = {}
    code = None
    backup = None
    try:
        ROOT.mkdir(mode=0o755, exist_ok=True)
        for name in ('releases', 'runtimes', 'backups'):
            (ROOT / name).mkdir(mode=0o700 if name == 'backups' else 0o755, exist_ok=True)
        os.chmod(ROOT / 'backups', 0o700)
        user = ensure_user()
        shared = ROOT / 'shared'
        if shared.exists() and shared.stat().st_uid != user.pw_uid:
            fail('Existujúci shared nepatrí vyhradenému používateľovi; dáta nebudú prevzaté.')
        shared.mkdir(mode=0o700, exist_ok=True)
        os.chown(shared, user.pw_uid, user.pw_gid)
        os.chmod(shared, 0o700)
        reject_shared_links(shared)
        release = stage_release(manifest, contents)
        runtime = stage_runtime(release)
        optional_tests(tests, release, runtime)

        backup = ROOT / 'backups' / (manifest['release_id'] + '-' + uuid.uuid4().hex[:8])
        backup.mkdir(mode=0o700)
        atomic_bytes(backup / 'nginx.before.conf', previous['nginx'], 0o600)
        if previous['unit']:
            atomic_bytes(backup / 'crm-pilot.before.service', previous['unit'], 0o600)
        atomic_bytes(backup / 'state.json', json.dumps({key: previous[key] for key in
                     ('current', 'runtime', 'active', 'enabled', 'main_pid')}, indent=2).encode(), 0o600)
        changed['service'] = True
        run(['systemctl', 'stop', SERVICE], check=False)
        if service_property(SERVICE, 'ActiveState') in {'active', 'activating', 'deactivating'}:
            fail('CRM služba sa nezastavila; konzistentná záloha nie je možná.')
        reject_shared_links(shared)
        check_database(shared)
        shutil.copytree(shared, backup / 'shared', copy_function=shutil.copy2)
        os.chmod(backup / 'shared', 0o700)
        code = initialize_if_needed(release, runtime)
        atomic_link(ROOT / 'current', release)
        atomic_link(ROOT / 'venv', runtime)
        atomic_bytes(UNIT, contents['deploy/crm-pilot.service'])
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'start', SERVICE])
        wait_health()
        if previous['desired_nginx'] != previous['nginx']:
            if NGINX.read_bytes() != previous['nginx']:
                fail('Nginx konfigurácia sa počas stagingu zmenila; nebude prepísaná.')
            changed['nginx'] = True
            atomic_bytes(NGINX, previous['desired_nginx'], previous['nginx_mode'])
            run(['nginx', '-t'])
            run(['systemctl', 'reload', 'nginx'])
        wait_public_health()
        http_check(ORIGIN + PREFIX + '/login')
        http_check(ORIGIN + '/')
        if (service_property(MAIN_SERVICE, 'ActiveState') != 'active'
                or service_property(MAIN_SERVICE, 'MainPID') != previous['main_pid']):
            fail('Pôvodná služba InvoiceMakeru zmenila stav alebo PID.')
        run(['systemctl', 'enable', SERVICE])
        result = {'status': 'healthy', 'url': ORIGIN + PREFIX + '/',
                  'release_id': manifest['release_id'], 'backup': str(backup),
                  'main_invoice_pid_unchanged': True}
        if code:
            result['new_access_code'] = code
        return result, 0
    except Exception as error:
        failures = rollback(previous, changed)
        result = {'status': 'failed', 'error': str(error) if isinstance(error, DeployError)
                  else 'Nasadenie zlyhalo; privátne dáta a artefakty zostali zachované.',
                  'rollback_failures': failures, 'release_id': manifest['release_id']}
        if backup:
            result['backup'] = str(backup)
        if code:
            result['new_access_code'] = code
        return result, 1


def main():
    parser = argparse.ArgumentParser(description='Izolovaný CRM pilot; bez --apply iba kontrola.')
    parser.add_argument('--archive', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--pilot-tests', help='Voliteľný samostatný súbor unittest testov pilota.')
    parser.add_argument('--apply', action='store_true', help='Výslovne povolí mutácie na tomto Linux VPS.')
    args = parser.parse_args()
    lock = None
    try:
        if sys.platform != 'linux' or os.geteuid() != 0:
            fail('Kontrolu a nasadenie spustite ako root na cieľovom Linux VPS.')
        archive = safe_absolute_file(args.archive)
        manifest_path = safe_absolute_file(args.manifest)
        tests = safe_absolute_file(args.pilot_tests) if args.pilot_tests else None
        manifest, contents = load_package(archive, manifest_path)
        if args.apply:
            descriptor = os.open('/run/lock/crm-pilot-deploy.lock',
                                 os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            lock = os.fdopen(descriptor, 'w')
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fail('Iné nasadenie CRM práve drží zámok.')
        previous = preflight(contents)
        if not args.apply:
            print(json.dumps({'status': 'checked', 'mutations': False,
                              'release_id': manifest['release_id'], 'files': len(contents),
                              'url': ORIGIN + PREFIX + '/', 'main_invoice_pid': previous['main_pid'],
                              'nginx_change_needed': previous['desired_nginx'] != previous['nginx']}, ensure_ascii=False))
            return 0
        result, code = apply_deployment(manifest, contents, previous, tests)
        print(json.dumps(result, ensure_ascii=False))
        return code
    except DeployError as error:
        print(json.dumps({'status': 'rejected', 'error': str(error)}, ensure_ascii=False))
        return 1
    except Exception:
        print(json.dumps({'status': 'rejected', 'error': 'Kontrola zlyhala bez nasadenia.'}, ensure_ascii=False))
        return 1
    finally:
        if lock is not None:
            lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
