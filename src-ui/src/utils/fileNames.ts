/** 与后端一致的名称提示；最终校验仍由后端执行。 */
export function fileNameError(name: string): string {
  if (!name || name !== name.trim() || name === '.' || name === '..' || name.endsWith('.') || name.length > 255
    || /[<>:"/\\|?*\u0000-\u001f]/.test(name)
    || /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i.test(name.split('.')[0])) {
    return '名称不能为空，不能包含路径、控制字符或系统保留名称，不能以空格或点结尾'
  }
  return ''
}
