"""Pass the existing project key to SSH stdin; never emit it on stdout."""
from pathlib import Path
import json
import re
import subprocess
import sys

if sys.argv[1:]!=['--to-ssh']:
    raise SystemExit('Use --to-ssh only after uploading configure_crm_ai_vps.py to the pilot staging directory.')
source=Path(__file__).resolve().parents[1]/'.env'
text=source.read_text(encoding='utf-8')
match=re.search(r'(?m)^\s*(?:export\s+)?OPENAI_API_KEY\s*=\s*(.*)$',text)
key=match.group(1).strip().strip(chr(34)).strip(chr(39)) if match else ''
if not re.fullmatch(r'sk-[A-Za-z0-9_-]{20,300}',key):
    raise SystemExit('Existing project key was not found. No credential emitted.')
try:
    result=subprocess.run(['ssh','-F',str(Path.home()/'.ssh'/'config'),'-o','BatchMode=yes',
        'vps-gallax','sudo -n python3 /home/adam/crm-pilot-upload/configure_crm_ai_vps.py'],
        input=json.dumps({'api_key':key})+'\n',capture_output=True,text=True,timeout=30)
    receipt=json.loads(result.stdout)
    if receipt.get('key_printed') is not False or key in result.stdout or key in result.stderr:
        raise ValueError
    print(json.dumps(receipt))
    raise SystemExit(result.returncode)
except (OSError,ValueError,subprocess.TimeoutExpired):
    raise SystemExit('Private SSH provisioning failed. No key was printed.')
