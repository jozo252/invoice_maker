"""Read one API key from stdin; validate and store only in the private VPS pilot."""
import json
import os
from pathlib import Path
import pwd
import re
import sys
import urllib.error
import urllib.request
import uuid

ROOT = Path('/srv/crm-pilot/shared')
KEY_PATH = ROOT / 'openai-api.key'
MODEL = 'gpt-4.1-mini-2025-04-14'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    if not sys.platform.startswith('linux') or os.geteuid()!=0:
        raise ValueError('Requires Linux root.')
    for path in (Path('/srv'),ROOT.parent,ROOT):
        if not path.is_dir() or path.is_symlink() or path.resolve()!=path:
            raise ValueError('Invalid fixed pilot directory.')
    payload=json.loads(sys.stdin.read(4097))
    key=payload.get('api_key','') if isinstance(payload,dict) else ''
    if not isinstance(key,str) or not re.fullmatch(r'sk-[A-Za-z0-9_-]{20,300}',key):
        raise ValueError('No valid API key supplied.')
    if KEY_PATH.is_symlink():
        raise ValueError('Key pathname is a symlink.')
    if KEY_PATH.exists() and KEY_PATH.read_text(encoding='utf-8').strip()!=key:
        raise ValueError('An existing different pilot key requires an explicit rotation.')
    request=urllib.request.Request('https://api.openai.com/v1/models/'+MODEL,
                                  headers={'Authorization':'Bearer '+key})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=15) as response:
            metadata=json.loads(response.read(65536))
        if metadata.get('id')!=MODEL:
            raise ValueError('Requested vision model is unavailable.')
    except urllib.error.HTTPError as error:
        code=error.code
        error.close()
        print(json.dumps({'status':'rejected','api_http_status':code,'key_printed':False}))
        return 1
    owner=pwd.getpwnam('crm-pilot')
    if not KEY_PATH.exists():
        temporary=ROOT/('.openai-key-'+uuid.uuid4().hex)
        descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        try:
            with os.fdopen(descriptor,'w',encoding='utf-8') as output:
                output.write(key+'\n'); output.flush(); os.fsync(output.fileno())
                os.fchown(output.fileno(),owner.pw_uid,owner.pw_gid)
            os.replace(temporary,KEY_PATH)
        finally:
            temporary.unlink(missing_ok=True)
    os.chmod(KEY_PATH,0o400)
    os.chown(KEY_PATH,owner.pw_uid,owner.pw_gid)
    print(json.dumps({'status':'configured','model':MODEL,'key_printed':False,'paid_calls':0}))
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print(json.dumps({'status':'rejected','message':'Private API configuration failed. Key was not printed.'}))
        raise SystemExit(1)
