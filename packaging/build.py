"""돋보기 데스크톱 앱 빌드: exe 묶기 → 묶은 exe 자체 점검 → 설치 프로그램 만들기.

    python packaging/build.py            # dist/Dotbogi/Dotbogi.exe 와 dist/Dotbogi-Setup-<버전>.exe
    python packaging/build.py --no-installer

필요: pip install pyinstaller pywebview lightgbm,  설치 프로그램은 Inno Setup 6 (winget install JRSoftware.InnoSetup)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def find_iscc() -> str | None:
    for c in (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Inno Setup 6/ISCC.exe",
              Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"), Path("C:/Program Files/Inno Setup 6/ISCC.exe")):
        if c.exists():
            return str(c)
    return shutil.which("ISCC") or shutil.which("iscc")


def main() -> int:
    from dotbogi import __version__
    os.chdir(ROOT)
    print(f"1/3 exe 묶기 (돋보기 {__version__})", flush=True)
    r = subprocess.run([sys.executable, "-m", "PyInstaller", "packaging/dotbogi.spec", "--noconfirm",
                        "--distpath", "dist", "--workpath", "build/pyinstaller"])
    if r.returncode:
        return r.returncode
    exe = ROOT / "dist/Dotbogi/Dotbogi.exe"

    print("2/3 묶은 exe 자체 점검 (LightGBM 먼저 → scikit-learn → parquet)", flush=True)
    home = tempfile.mkdtemp(prefix="dotbogi_build_")
    r = subprocess.run([str(exe), "--selftest", "--lightgbm-first"], env=dict(os.environ, DOTBOGI_HOME=home),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    log = Path(home) / "desktop.log"
    if log.exists():
        out += log.read_text(encoding="utf-8", errors="replace")
    if r.returncode or "selftest ok" not in out:
        print(out[-3000:])
        print("자체 점검 실패: 설치 프로그램을 만들지 않습니다.")
        return 1
    print("   " + next(line for line in out.splitlines() if line.startswith("selftest ok")))

    if "--no-installer" in sys.argv:
        return 0
    iscc = find_iscc()
    if not iscc:
        print("3/3 Inno Setup이 없어 설치 프로그램은 건너뜁니다 (winget install JRSoftware.InnoSetup).")
        return 0
    print("3/3 설치 프로그램 만들기", flush=True)
    r = subprocess.run([iscc, "/Q", "packaging/dotbogi.iss"], env=dict(os.environ, DOTBOGI_VERSION=__version__))
    if r.returncode:
        return r.returncode
    print(f"완료: {ROOT / 'dist' / f'Dotbogi-Setup-{__version__}.exe'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
