"""exe 진입점: 돋보기 데스크톱 앱 창을 연다. (PyInstaller가 이 파일로 Dotbogi.exe를 만든다)"""
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()  # 분석 라이브러리가 하위 프로세스를 띄울 때 exe가 다시 실행되지 않게
    from dotbogi.desktop import run
    run()
