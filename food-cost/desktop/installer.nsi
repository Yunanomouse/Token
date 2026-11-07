; Restaurant installer (per-user, no admin rights needed).
; Built by build-win.js: makensis -DAPPDIR=<win-unpacked> -DOUTFILE=<setup.exe> -DVERSION=<x.y.z> -DPUBLISHER=<name> installer.nsi
Unicode true
!include "MUI2.nsh"

!define APPNAME "Restaurant"
!ifndef PUBLISHER
  !define PUBLISHER "Matthew Neil Louis Marinier"
!endif
!ifndef DISPLAYNAME
  !define DISPLAYNAME "${APPNAME}"
!endif
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\RestaurantCosting"

Name "${DISPLAYNAME}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\${APPNAME}"
InstallDirRegKey HKCU "${UNINSTKEY}" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${DISPLAYNAME}"
VIAddVersionKey "FileDescription" "${DISPLAYNAME} installer"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "CompanyName" "${PUBLISHER}"
VIAddVersionKey "LegalCopyright" "${PUBLISHER}"

!define MUI_ICON "icon.ico"
!define MUI_UNICON "icon.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TEXT "This installs ${DISPLAYNAME} on this computer. If another edition of ${APPNAME} is installed, this replaces it and keeps your workbook.$\r$\n$\r$\nIt runs without the internet. Your workbook is saved in Documents\Restaurant, with a dated copy kept every day in its backups folder.$\r$\n$\r$\nUninstalling the program never deletes your workbook."
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APPNAME}.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Open ${DISPLAYNAME} now"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "${APPDIR}\*.*"
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${APPNAME}.exe"
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\${APPNAME}.exe"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\Uninstall ${APPNAME}.lnk" "$INSTDIR\Uninstall ${APPNAME}.exe"
  WriteUninstaller "$INSTDIR\Uninstall ${APPNAME}.exe"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayName" "${DISPLAYNAME}"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINSTKEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\${APPNAME}.exe"
  WriteRegStr HKCU "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTKEY}" "UninstallString" '"$INSTDIR\Uninstall ${APPNAME}.exe"'
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  ; program files only: the workbook in Documents\Restaurant stays
  Delete "$DESKTOP\${APPNAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APPNAME}"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "${UNINSTKEY}"
SectionEnd
