; Tauri 2.0 NSIS 自定义钩子文件
; 参考: https://v2.tauri.app/distribute/windows-installer/#customizing-the-nsis-installer-template

; ============================================
; 安装前钩子 - 在安装开始之前执行
; ============================================
!macro NSIS_HOOK_PREINSTALL
  DetailPrint "=== NSIS_HOOK_PREINSTALL ==="
!macroend

; ============================================
; 安装完成后钩子 - 在安装完成后执行
; ============================================
!macro NSIS_HOOK_POSTINSTALL
  DetailPrint "=== NSIS_HOOK_POSTINSTALL ==="
  DetailPrint "Install directory: $INSTDIR"
!macroend

; ============================================
; 卸载前钩子 - 在卸载开始之前执行
; 这是删除 .taghive 文件夹的主要位置
; ============================================
!macro NSIS_HOOK_PREUNINSTALL
  DetailPrint "=== NSIS_HOOK_PREUNINSTALL ==="
  DetailPrint "Install directory: $INSTDIR"
  
  ; 检查 .taghive 目录是否存在
  IfFileExists "$INSTDIR\.taghive\*.*" 0 check_empty_dir
    DetailPrint ".taghive directory exists with content"
    Goto do_remove
  
  check_empty_dir:
  IfFileExists "$INSTDIR\.taghive" 0 no_taghive
    DetailPrint ".taghive directory exists (may be empty)"
    Goto do_remove
  
  do_remove:
    DetailPrint "Removing .taghive directory..."
    ; 递归删除整个目录（包括所有子目录和文件）
    RMDir /r "$INSTDIR\.taghive"
    ; 检查是否成功
    IfFileExists "$INSTDIR\.taghive" 0 success
      DetailPrint "Normal removal failed, trying REBOOTOK..."
      RMDir /r /REBOOTOK "$INSTDIR\.taghive"
      IfFileExists "$INSTDIR\.taghive" 0 success
        DetailPrint "Warning: Could not remove .taghive directory"
        Goto done
  
  success:
    DetailPrint ".taghive directory successfully removed"
    Goto done
  
  no_taghive:
    DetailPrint ".taghive directory not found at: $INSTDIR\.taghive"
  
  done:
  DetailPrint "=== End NSIS_HOOK_PREUNINSTALL ==="
!macroend

; ============================================
; 卸载后钩子 - 在卸载完成后执行
; ============================================
!macro NSIS_HOOK_POSTUNINSTALL
  DetailPrint "=== NSIS_HOOK_POSTUNINSTALL ==="
  DetailPrint "Uninstall completed"
!macroend
