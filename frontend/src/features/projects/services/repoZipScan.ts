export function validateZipFile(file: File): { valid: boolean; error?: string } {
  // 支持的压缩格式
  const supportedExtensions = ['.zip', '.tar', '.tar.gz', '.tar.bz2', '.7z', '.rar'];
  const fileName = file.name.toLowerCase();
  
  // 检查文件扩展名
  const isSupported = supportedExtensions.some(ext => fileName.endsWith(ext));
  if (!isSupported) {
    return { 
      valid: false, 
      error: `请上传支持的压缩格式文件 (${supportedExtensions.join(', ')})` 
    };
  }

  // 检查文件大小 (限制为500MB)
  const maxSize = 500 * 1024 * 1024;
  if (file.size > maxSize) {
    return { valid: false, error: '文件大小不能超过500MB' };
  }

  return { valid: true };
}
