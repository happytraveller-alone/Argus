
import type { ProjectSourceType, RepositoryPlatform } from '@/shared/types';

export const PROJECT_SOURCE_TYPES: Array<{
  value: ProjectSourceType;
  label: string;
  description: string;
}> = [
    {
      value: 'repository',
      label: '远程仓库',
      description: '从 GitHub/GitLab 等远程仓库拉取代码'
    },
    {
      value: 'zip',
      label: '上传项目',
      description: '上传本地压缩包进行扫描'
    }
  ];

export const REPOSITORY_PLATFORM_LABELS: Record<RepositoryPlatform, string> = {
  github: 'GitHub',
  gitlab: 'GitLab',
  gitea: 'Gitea',
  other: '其他',
};

export const REPOSITORY_PLATFORMS: Array<{
  value: RepositoryPlatform;
  label: string;
  icon?: string;
}> = Object.entries(REPOSITORY_PLATFORM_LABELS).map(([value, label]) => ({
  value: value as RepositoryPlatform,
  label
}));

export const SOURCE_TYPE_COLORS: Record<ProjectSourceType, {
  bg: string;
  text: string;
  border: string;
}> = {
  repository: {
    bg: 'bg-blue-100',
    text: 'text-blue-800',
    border: 'border-blue-300'
  },
  zip: {
    bg: 'bg-amber-100',
    text: 'text-amber-800',
    border: 'border-amber-300'
  }
};

export const PLATFORM_COLORS: Record<RepositoryPlatform, {
  bg: string;
  text: string;
}> = {
  github: { bg: 'bg-foreground', text: 'text-background' },
  gitlab: { bg: 'bg-orange-500', text: 'text-white' },
  gitea: { bg: 'bg-green-600', text: 'text-white' },
  other: { bg: 'bg-muted-foreground', text: 'text-background' }
};
