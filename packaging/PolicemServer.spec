# PyInstaller spec; build on Windows with: pyinstaller --noconfirm packaging/PolicemServer.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_all
root = Path(SPECPATH).parent.parent
datas = [(str(root / 'static'), 'static')]
hiddenimports = ['customer_portal', 'notification_core', 'push_service', 'reminder_job', 'push_job']
binaries = []
for module in ['fitz', 'pymupdf', 'webauthn', 'pywebpush']:
    d, b, h = collect_all(module)
    datas += d
    binaries += b
    hiddenimports += h
a = Analysis([str(root / 'packaging' / 'server_entry.py')], pathex=[str(root)], binaries=binaries, datas=datas, hiddenimports=hiddenimports, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PolicemServer', console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='PolicemServer')
