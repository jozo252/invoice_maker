"""Reuse the already installed, pinned OCR engine from the first local prototype."""
from pathlib import Path
import argparse
import json
import shutil

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--node-modules',type=Path,default=Path.home()/'Documents'/'ChatGPT'/'crm-remeselnici'/'node_modules')
args=parser.parse_args();source=args.node_modules
for package,version in [('tesseract.js','7.0.0'),('tesseract.js-core','7.0.0'),('@tesseract.js-data/slk','1.0.0'),('@tesseract.js-data/eng','1.0.0')]:
    manifest=json.loads((source/package/'package.json').read_text(encoding='utf-8'))
    if manifest['version']!=version:raise SystemExit(f'Vyžadovaný balík {package}@{version}.')
target=ROOT/'static'/'crm'/'vendor'/'ocr'
(target/'core').mkdir(parents=True,exist_ok=True);(target/'lang').mkdir(parents=True,exist_ok=True)
for name in ['tesseract.min.js','worker.min.js','tesseract.min.js.LICENSE.txt','worker.min.js.LICENSE.txt']:
    shutil.copy2(source/'tesseract.js'/'dist'/name,target/name)
for path in (source/'tesseract.js-core').glob('tesseract-core*.wasm*'):
    if path.suffix in {'.wasm','.js'}:shutil.copy2(path,target/'core'/path.name)
for lang in ['slk','eng']:
    shutil.copy2(source/'@tesseract.js-data'/lang/'4.0.0_best_int'/f'{lang}.traineddata.gz',target/'lang'/f'{lang}.traineddata.gz')
print('Lokálne OCR súbory pripravené. Fotografie sa neposielajú do externého OCR API.')
