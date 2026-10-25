; 돋보기 설치 프로그램 (Inno Setup 6). 실행: python packaging/build.py
; 관리자 권한 없이 사용자 폴더에 설치하고, 시작 메뉴·(선택) 바탕화면 바로가기와 '앱 제거'를 등록한다.
#define AppVersion GetEnv("DOTBOGI_VERSION")
#if AppVersion == ""
  #define AppVersion "1.1.0"
#endif

[Setup]
AppId={{6F3C2B8E-1D4A-4F57-9C21-7A0D5E9B3C41}
AppName=돋보기
AppVersion={#AppVersion}
AppVerName=돋보기 {#AppVersion}
AppPublisher=Dotbogi
AppPublisherURL=https://github.com/maximuthking/dotbogi
AppSupportURL=https://github.com/maximuthking/dotbogi/issues
DefaultDirName={localappdata}\Programs\Dotbogi
DefaultGroupName=돋보기
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=Dotbogi-Setup-{#AppVersion}
SetupIconFile=..\dotbogi\static\img\dotbogi.ico
UninstallDisplayIcon={app}\Dotbogi.exe
UninstallDisplayName=돋보기
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "바로가기:"

[Files]
Source: "..\dist\Dotbogi\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\돋보기"; Filename: "{app}\Dotbogi.exe"; Comment: "캐글·데이콘 대회 데이터 분석"
Name: "{autodesktop}\돋보기"; Filename: "{app}\Dotbogi.exe"; Tasks: desktopicon; Comment: "캐글·데이콘 대회 데이터 분석"

[Run]
Filename: "{app}\Dotbogi.exe"; Description: "돋보기 실행"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 프로그램 폴더만 지운다. 대회 폴더의 .dotbogi 기록과 ~/.dotbogi 설정은 남긴다.
Type: filesandordirs; Name: "{app}"
