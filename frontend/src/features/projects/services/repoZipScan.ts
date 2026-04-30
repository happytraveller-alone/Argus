export const SUPPORTED_ARCHIVE_EXTENSIONS = [
  ".tar.zstd",
  ".tar.zst",
  ".tar.xz",
  ".tar.bz2",
  ".tar.gz",
  ".tzst",
  ".txz",
  ".tbz2",
  ".tbz",
  ".tgz",
  ".zip",
  ".tar",
  ".zst",
] as const;

export const SUPPORTED_ARCHIVE_INPUT_ACCEPT = SUPPORTED_ARCHIVE_EXTENSIONS.join(",");

export function stripSupportedArchiveSuffix(fileName: string) {
  const lower = fileName.toLowerCase();
  const matched = SUPPORTED_ARCHIVE_EXTENSIONS.find((suffix) =>
    lower.endsWith(suffix),
  );
  if (!matched) return fileName;
  return fileName.slice(0, fileName.length - matched.length);
}

export function validateZipFile(file: File): { valid: boolean; error?: string } {
  const fileName = file.name.toLowerCase();
  const isSupported = SUPPORTED_ARCHIVE_EXTENSIONS.some((ext) =>
    fileName.endsWith(ext),
  );
  if (!isSupported) {
    return {
      valid: false,
      error: `请上传支持的压缩格式文件 (${SUPPORTED_ARCHIVE_EXTENSIONS.join(", ")})`,
    };
  }

  const maxSize = 500 * 1024 * 1024;
  if (file.size > maxSize) {
    return { valid: false, error: "文件大小不能超过500MB" };
  }

  return { valid: true };
}
