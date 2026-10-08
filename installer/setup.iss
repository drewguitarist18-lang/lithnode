; Inno Setup script for LithnodeSetup.exe. Build everything with installer\build.ps1.
#define AppVersion "0.1.0"

[Setup]
AppId={{8F3C2A51-6B7E-4E9D-9C1A-1E5B7D4C2A90}
AppName=Lithnode
AppVersion={#AppVersion}
AppVerName=Lithnode {#AppVersion}
AppPublisher=Lithnode
AppPublisherURL=https://lithnode.com
AppSupportURL=https://lithnode.com
DefaultDirName={localappdata}\Programs\Lithnode
DefaultGroupName=Lithnode
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=LithnodeSetup
SetupIconFile=lithnode.ico
; dark like the app, with the crab on the welcome/finish panel and in the corner of every page (art: make_icon.py)
WizardStyle=modern dark
WizardBackColor=#0a0a0a
WizardImageFile=wizard-1x.bmp,wizard-2x.bmp
WizardSmallImageFile=wizard-small-1x.bmp,wizard-small-2x.bmp
WizardImageStretch=no
WizardImageBackColor=#0a0a0a
DisableWelcomePage=no
UninstallDisplayIcon={app}\Lithnode.exe
UninstallDisplayName=Lithnode
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force

[Types]
Name: "full"; Description: "Lithnode and Claude Pet (recommended)"
Name: "compact"; Description: "Lithnode only"
Name: "custom"; Description: "Choose"; Flags: iscustom

[Components]
Name: "app"; Description: "Lithnode: draw teams of Claude Code agents and run them"; Types: full compact custom; Flags: fixed
Name: "pet"; Description: "Claude Pet: a little Clawd on your desktop that shows what Claude Code is doing"; Types: full

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
; the app window (Electron) at the top, the engine and Claude Pet (PyInstaller) in server\
Source: "..\dist\Lithnode-win32-x64\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\dist\Lithnode\*"; DestDir: "{app}\server"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Lithnode"; Filename: "{app}\Lithnode.exe"
Name: "{autodesktop}\Lithnode"; Filename: "{app}\Lithnode.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\server\lithnode-cli.exe"; Parameters: "install-pet"; Components: pet; Flags: runhidden; StatusMsg: "Adding Claude Pet to Claude Code..."
Filename: "{app}\server\lithnode-cli.exe"; Parameters: "uninstall-pet"; Components: not pet; Flags: runhidden
Filename: "{app}\Lithnode.exe"; Description: "Open Lithnode"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM Lithnode.exe /IM lithnode-server.exe"; Flags: runhidden; RunOnceId: "StopLithnode"
Filename: "{app}\server\lithnode-cli.exe"; Parameters: "uninstall-pet"; Flags: runhidden; RunOnceId: "RemovePetHooks"

[Messages]
WelcomeLabel1=Welcome to Lithnode
WelcomeLabel2=Build an AI team. Watch it ship.%n%nLithnode lets you draw a team of Claude Code agents, press run, and watch them plan, build, check and ship. It runs on your computer and your own Claude plan.
FinishedLabel=Lithnode is installed. It runs on Claude Code: if you don't have it yet, get it at claude.com/claude-code, then click Sign in at the top right of Lithnode.
