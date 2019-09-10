; Script for NullSoft Scriptable Install System, producing an executable
; installer for SQLitely.
;
; Expected command-line parameters:
; /DPRODUCT_VERSION=<program version>
; /DSUFFIX64=<"_x64" for 64-bit installer>
;
; @created   22.08.2019
; @modified  10.09.2014

; HM NIS Edit Wizard helper defines
!define PRODUCT_NAME "SQLitely"
!ifndef PRODUCT_VERSION
  ; PRODUCT_VERSION should come from command-line parameter
  !define PRODUCT_VERSION "1.0"
!endif
!define PRODUCT_PUBLISHER "Erki Suurjaak"
!define PRODUCT_WEB_SITE "http://suurjaak.github.com/SQLitely"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\sqlitely.exe"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"

; MUI 1.67 compatible ------
!include "MUI.nsh"
!include x64.nsh
!include FileAssociation.nsh

!define MUI_TEXT_WELCOME_INFO_TEXT "This wizard will guide you through the installation of $(^NameDA).$\r$\n$\r$\n$_CLICK"

; MUI Settings
!define MUI_ABORTWARNING
!define MUI_ICON "sqlitely.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

; Welcome page
!insertmacro MUI_PAGE_WELCOME
; Directory page
!insertmacro MUI_PAGE_DIRECTORY
; Instfiles page
!insertmacro MUI_PAGE_INSTFILES
; Finish page
!define MUI_PAGE_CUSTOMFUNCTION_PRE FinishPage_Pre
!define MUI_PAGE_CUSTOMFUNCTION_SHOW FinishPage_Show
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE FinishPage_Leave
!define MUI_FINISHPAGE_RUN "$INSTDIR\sqlitely.exe"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\README.txt"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_INSTFILES

; Language files
!insertmacro MUI_LANGUAGE "English"

; MUI end ------

RequestExecutionLevel admin

InstallDir "$PROGRAMFILES\SQLitely"
OutFile "sqlitely_${PRODUCT_VERSION}${SUFFIX64}_setup.exe"
Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
ShowInstDetails show
ShowUnInstDetails show

Function .OnInit
  ${If} SUFFIX64 != ''
    StrCpy $INSTDIR "$PROGRAMFILES64\SQLitely"
  ${EndIf}
FunctionEnd


Section "MainSection" SEC01
  ; Fixes potential problems with uninstalling shortcuts in Windows 7
  SetShellVarContext all
  SetOutPath "$INSTDIR"
  SetOverwrite ifnewer
  File "sqlitely.exe"
  CreateDirectory "$SMPROGRAMS\SQLitely"
  CreateShortCut "$SMPROGRAMS\SQLitely\SQLitely.lnk" "$INSTDIR\sqlitely.exe"
  SetOverwrite off
  File "sqlitely.ini"
  SetOverwrite ifnewer
  File /oname=README.txt "README for Windows.txt"
  CreateShortCut "$SMPROGRAMS\SQLitely\README.lnk" "$INSTDIR\README.txt"
  File "3rd-party licenses.txt"
SectionEnd

Section -AdditionalIcons
  WriteIniStr "$INSTDIR\${PRODUCT_NAME}.url" "InternetShortcut" "URL" "${PRODUCT_WEB_SITE}"
  CreateShortCut "$SMPROGRAMS\SQLitely\Website.lnk" "$INSTDIR\${PRODUCT_NAME}.url"
  CreateShortCut "$SMPROGRAMS\SQLitely\Uninstall SQLitely.lnk" "$INSTDIR\uninst.exe"
SectionEnd

Section -Post
  WriteUninstaller "$INSTDIR\uninst.exe"
  WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\sqlitely.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayName" "$(^Name)"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninst.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\sqlitely.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
SectionEnd


Function un.onUninstSuccess
  HideWindow
  MessageBox MB_ICONINFORMATION|MB_OK "$(^Name) was successfully removed from your computer."
FunctionEnd

Function un.onInit
  MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 "Are you sure you want to uninstall $(^Name)?" IDYES +2
  Abort
FunctionEnd

Section Uninstall
  ; Fixes potential problems with uninstalling shortcuts in Windows 7
  SetShellVarContext all
  Delete "$INSTDIR\${PRODUCT_NAME}.url"
  Delete "$INSTDIR\uninst.exe"
  Delete "$INSTDIR\README.txt"
  Delete "$INSTDIR\3rd-party licenses.txt"
  Delete "$INSTDIR\sqlitely.ini"
  Delete "$INSTDIR\sqlitely.exe"

  Delete "$SMPROGRAMS\SQLitely\SQLitely.lnk"
  Delete "$SMPROGRAMS\SQLitely\README.lnk"
  Delete "$SMPROGRAMS\SQLitely\Website.lnk"
  Delete "$SMPROGRAMS\SQLitely\Uninstall SQLitely.lnk"

  RMDir "$SMPROGRAMS\SQLitely"
  RMDir "$INSTDIR"

  ${UnregisterExtension} ".db" "SQLite3 database file"

  DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"
  DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"
  SetAutoClose true
SectionEnd

Function FinishPage_Show
ReadINIStr $0 "$PLUGINSDIR\iospecial.ini" "Field 6" "HWND"
SetCtlColors $0 0x000000 0xFFFFFF
FunctionEnd

Function FinishPage_Pre
WriteINIStr "$PLUGINSDIR\iospecial.ini" "Settings" "NumFields" "6"
WriteINIStr "$PLUGINSDIR\iospecial.ini" "Field 6" "Type" "CheckBox"
WriteINIStr "$PLUGINSDIR\iospecial.ini" "Field 6" "Text" "&Associate SQLitely with *.db *.sqlite *.sqlite3 files"
WriteINIStr "$PLUGINSDIR\iospecial.ini" "Field 6" "Left" "120"
WriteINIStr "$PLUGINSDIR\iospecial.ini" "Field 6" "Right" "315"
WriteINIStr "$PLUGINSDIR\iospecial.ini" "Field 6" "Top" "130"
WriteINIStr "$PLUGINSDIR\iospecial.ini" "Field 6" "Bottom" "140"
WriteINIStr "$PLUGINSDIR\iospecial.ini" "Field 6" "State" "0"
FunctionEnd

Function FinishPage_Leave
ReadINIStr $0 "$PLUGINSDIR\iospecial.ini" "Field 6" "State"
StrCmp $0 "0" end
${RegisterExtension} "$INSTDIR\sqlitely.exe" ".db" "SQLite3 database file"
${RegisterExtension} "$INSTDIR\sqlitely.exe" ".sqlite" "SQLite3 database file"
${RegisterExtension} "$INSTDIR\sqlitely.exe" ".sqlite3" "SQLite3 database file"
end:
FunctionEnd
