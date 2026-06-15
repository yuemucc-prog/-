[Setup]
AppId={{A81A4F06-2F69-42EF-81D8-3D35C2D93C11}
AppName=BossLoopTimer
AppVersion=0.1.0
AppPublisher=Kali
DefaultDirName={autopf}\BossLoopTimer
DefaultGroupName=BossLoopTimer
DisableProgramGroupPage=yes
OutputDir=dist-installer
OutputBaseFilename=BossLoopTimer-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\BossLoopTimer.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\BossLoopTimer"; Filename: "{app}\BossLoopTimer.exe"
Name: "{autodesktop}\BossLoopTimer"; Filename: "{app}\BossLoopTimer.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："

[Run]
Filename: "{app}\BossLoopTimer.exe"; Description: "启动 BossLoopTimer"; Flags: nowait postinstall skipifsilent
