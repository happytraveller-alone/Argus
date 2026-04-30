
import type { Project, ProjectSourceType } from '@/shared/types';
import { REPOSITORY_PLATFORM_LABELS } from '@/shared/constants/projectTypes';

export const HTTPS_ONLY_REPOSITORY_ERROR = '仅支持 HTTPS 仓库地址，不再支持 SSH 地址';

export function isUnsupportedRepositoryUrl(repositoryUrl?: string | null): boolean {
  const normalized = String(repositoryUrl || '').trim().toLowerCase();
  return normalized.startsWith('git@') || normalized.startsWith('ssh://');
}

export function isRepositoryProject(project: Project): boolean {
  return project.source_type === 'repository';
}

export function isZipProject(project: Project): boolean {
  return project.source_type === 'zip';
}

export function getSourceTypeLabel(sourceType: ProjectSourceType): string {
  const labels: Record<ProjectSourceType, string> = {
    repository: '远程仓库',
    zip: '上传项目'
  };
  return labels[sourceType] || '未知';
}

export function getSourceTypeBadge(sourceType: ProjectSourceType): string {
  const badges: Record<ProjectSourceType, string> = {
    repository: 'REPO',
    zip: 'ZIP'
  };
  return badges[sourceType] || 'UNKNOWN';
}

export function getRepositoryPlatformLabel(platform?: string): string {
  return REPOSITORY_PLATFORM_LABELS[platform as keyof typeof REPOSITORY_PLATFORM_LABELS] || REPOSITORY_PLATFORM_LABELS.other;
}

export function canSelectBranch(project: Project): boolean {
  return isRepositoryProject(project) && !!project.repository_url;
}

export function requiresZipUpload(project: Project): boolean {
  return isZipProject(project);
}

export function getScanMethodDescription(project: Project): string {
  if (isRepositoryProject(project)) {
    return `从 ${getRepositoryPlatformLabel(project.repository_type)} 仓库拉取代码`;
  }
  return '上传源码归档进行扫描';
}

export function validateProjectConfig(project: Project): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (!project.name?.trim()) {
    errors.push('项目名称不能为空');
  }

  if (isRepositoryProject(project)) {
    if (!project.repository_url?.trim()) {
      errors.push('仓库地址不能为空');
    } else if (isUnsupportedRepositoryUrl(project.repository_url)) {
      errors.push(HTTPS_ONLY_REPOSITORY_ERROR);
    }
  }

  return {
    valid: errors.length === 0,
    errors
  };
}
