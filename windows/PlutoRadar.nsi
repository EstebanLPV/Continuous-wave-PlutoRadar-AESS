Unicode true
!include "MUI2.nsh"
!include "x64.nsh"
!include "WinVer.nsh"

!define PRODUCT_NAME "PlutoRadar AESS"
!define INSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\PlutoRadar-AESS"
!ifndef PRODUCT_VERSION
  !define PRODUCT_VERSION "1.0.0"
!endif

Name "${PRODUCT_NAME}"
OutFile "..\dist\PlutoRadar-Setup-x64.exe"
InstallDir "$LOCALAPPDATA\Programs\PlutoRadar-AESS"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\PlutoRadar.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir PlutoRadar AESS"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Spanish"

Function .onInit
  ${IfNot} ${RunningX64}
  ${OrIfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "PlutoRadar AESS requiere Windows 10 u 11 de 64 bits." /SD IDOK
    Abort
  ${EndIf}
  SetShellVarContext current
FunctionEnd

Section "PlutoRadar AESS"
  SetOutPath "$INSTDIR"
  SetOverwrite on
  File "..\dist\PlutoRadar\PlutoRadar.exe"
  File "..\dist\PlutoRadar\radar (1).grc"
  File "..\dist\PlutoRadar\LEEME_EJECUTABLE.txt"
  SetOverwrite off
  File "..\dist\PlutoRadar\configuracion_radar.json"
  SetOverwrite on
  SetOutPath "$INSTDIR\_internal"
  File /r "..\dist\PlutoRadar\_internal\*.*"

  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\Desinstalar.exe"
  CreateDirectory "$SMPROGRAMS\PlutoRadar AESS"
  CreateShortcut "$SMPROGRAMS\PlutoRadar AESS\PlutoRadar AESS.lnk" "$INSTDIR\PlutoRadar.exe"
  CreateShortcut "$SMPROGRAMS\PlutoRadar AESS\Guía y diagrama.lnk" "$INSTDIR\LEEME_EJECUTABLE.txt"
  WriteRegStr HKCU "${INSTALL_KEY}" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKCU "${INSTALL_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "${INSTALL_KEY}" "DisplayIcon" "$INSTDIR\PlutoRadar.exe"
  WriteRegStr HKCU "${INSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${INSTALL_KEY}" "UninstallString" '$\"$INSTDIR\Desinstalar.exe$\"'
  WriteRegStr HKCU "${INSTALL_KEY}" "QuietUninstallString" '$\"$INSTDIR\Desinstalar.exe$\" /S'
  WriteRegDWORD HKCU "${INSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${INSTALL_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$SMPROGRAMS\PlutoRadar AESS\PlutoRadar AESS.lnk"
  Delete "$SMPROGRAMS\PlutoRadar AESS\Guía y diagrama.lnk"
  RMDir "$SMPROGRAMS\PlutoRadar AESS"
  Delete "$INSTDIR\PlutoRadar.exe"
  Delete "$INSTDIR\radar (1).grc"
  Delete "$INSTDIR\LEEME_EJECUTABLE.txt"
  Delete "$INSTDIR\configuracion_radar.json"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\Desinstalar.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${INSTALL_KEY}"
SectionEnd
