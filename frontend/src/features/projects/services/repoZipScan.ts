import { apiClient } from "@/shared/api/serverClient";

/**
 * 上传ZIP文件并启动扫描
 */
export async function scanZipFile(params: {
  projectId: string;
  zipFile: File;
  excludePatterns?: string[];
  createdBy?: string;
  filePaths?: string[];
  ruleSetId?: string;
  promptTemplateId?: string;
}): Promise<string> {
  const formData = new FormData();
  formData.append("file", params.zipFile);
  formData.append("project_id", params.projectId);

  const scanConfig = {
    file_paths: params.filePaths,
    full_scan: !params.filePaths || params.filePaths.length === 0,
    exclude_patterns: params.excludePatterns || [],
    rule_set_id: params.ruleSetId,
    prompt_template_id: params.promptTemplateId,
  };
  formData.append("scan_config", JSON.stringify(scanConfig));

  const res = await apiClient.post(`/scan/upload-zip`, formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });

  return res.data.task_id;
}

/**
 * 使用已存储的ZIP文件启动扫描（无需重新上传）
 */
export async function scanStoredZipFile(params: {
  projectId: string;
  excludePatterns?: string[];
  createdBy?: string;
  filePaths?: string[];
  ruleSetId?: string;
  promptTemplateId?: string;
}): Promise<string> {
  const scanRequest = {
    file_paths: params.filePaths,
    full_scan: !params.filePaths || params.filePaths.length === 0,
    exclude_patterns: params.excludePatterns || [],
    rule_set_id: params.ruleSetId,
    prompt_template_id: params.promptTemplateId,
  };
  const res = await apiClient.post(`/scan/scan-stored-zip`, scanRequest, {
    params: { project_id: params.projectId },
  });

  return res.data.task_id;
}

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
