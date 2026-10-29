"""Build a separate installable QR gadget without changing ShipoMaster."""
from pathlib import Path
import importlib.metadata
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
from version import VERSION
for name in ('QRMaster_Aspire.lua','QRMaster_Aspire.html','README_RU.txt'):
    if VERSION not in (ROOT/name).read_text(encoding='utf-8'):
        raise RuntimeError('Version label mismatch: '+name)
PACKAGE=ROOT/'package/QRMaster Aspire'
PACKAGE.mkdir(parents=True,exist_ok=True)
for name in ('QRMaster_Aspire.lua','QRMaster_Aspire.html','README_RU.txt'):
    shutil.copy2(ROOT/name,PACKAGE/name)
(PACKAGE/'__runtime').mkdir(exist_ok=True)
shutil.copy2(ROOT/'bin/QRMasterEngine.exe',PACKAGE/'__runtime/QRMasterEngine.exe')
sources=PACKAGE/'sources'
sources.mkdir(exist_ok=True)
for name in ('qr_engine.py','updates.py','version.py','package_qr.py','requirements.txt','test_qr.py'):
    shutil.copy2(ROOT/name,sources/name)
licenses=PACKAGE/'LICENSES'
licenses.mkdir(exist_ok=True)
for name in ('segno','shapely','numpy','pyinstaller'):
    dist=importlib.metadata.distribution(name)
    for item in dist.files or []:
        if any(part in str(item).lower() for part in ('license','copying')):
            source=dist.locate_file(item)
            if source.is_file():
                shutil.copy2(source,licenses/(name+'_'+source.name))
python_license=Path(sys.base_prefix)/'LICENSE.txt'
if python_license.exists():
    shutil.copy2(python_license,licenses/'Python_LICENSE.txt')
archive=ROOT/f'QRMaster_Aspire_{VERSION}.vgadget'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for path in PACKAGE.rglob('*'):
        if path.is_file():
            z.write(path,path.relative_to(PACKAGE.parent))
print(archive)
print('Size:',archive.stat().st_size)
