#ifndef BundleDir
  #define BundleDir "..\dist\SnapFlow"
#endif
#ifndef OutputDirPath
  #define OutputDirPath "..\dist"
#endif
[Setup]
AppId={{34F0E85B-EC8D-4D95-B87B-70D7B3F994B2}
AppName=SnapFlow
AppVersion=0.23.4
AppPublisher=ZLongLab
AppPublisherURL=https://github.com/ZLongLab/DocumentAssistant
DefaultDirName={code:DefaultInstallDir}
DefaultGroupName=SnapFlow
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDirPath}
OutputBaseFilename=SnapFlow-0.23.4-Windows-x64-Setup
SetupIconFile=..\document_assistant\snapflow.ico
UninstallDisplayIcon={app}\SnapFlow.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
DisableDirPage=no
UninstallDisplayName=SnapFlow

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; GroupDescription: "{cm:ShortcutGroup}"; Flags: checkedonce

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Remove only obsolete build-host system DLL copies from this app's own bundle.
Type: files; Name: "{app}\_internal\api-ms-win-*.dll"
Type: files; Name: "{app}\_internal\ext-ms-win-*.dll"
Type: files; Name: "{app}\_internal\ucrtbase.dll"

[Icons]
Name: "{group}\SnapFlow"; Filename: "{app}\SnapFlow.exe"; AppUserModelID: "SnapFlow.Capture"
Name: "{userdesktop}\SnapFlow"; Filename: "{app}\SnapFlow.exe"; Tasks: desktopicon; AppUserModelID: "SnapFlow.Capture"

[Run]
Filename: "{app}\SnapFlow.exe"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[CustomMessages]
chinesesimp.DesktopShortcut=创建桌面快捷方式
chinesesimp.ShortcutGroup=快捷方式：
chinesesimp.LaunchApp=启动 SnapFlow
english.DesktopShortcut=Create a desktop shortcut
english.ShortcutGroup=Shortcuts:
english.LaunchApp=Launch SnapFlow

[Code]
function DefaultInstallDir(Param: String): String;
begin
  if DirExists('D:\') then Result := 'D:\Apps\SnapFlow'
  else Result := ExpandConstant('{localappdata}\Programs\SnapFlow');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var Existing: String;
begin
  if CurUninstallStep = usUninstall then
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'DocumentAssistant', Existing) then
      if (Pos('"' + ExpandConstant('{app}\SnapFlow.exe') + '" --tray ', Existing) = 1) or
         (Pos(ExpandConstant('{app}\SnapFlow.exe') + ' --tray ', Existing) = 1) then
        RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'DocumentAssistant');
end;
