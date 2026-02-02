/**
 * Opengrep Rules Management Page
 * Cyberpunk Terminal Aesthetic
 */

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { toast } from 'sonner';
import {
  Trash2,
  Search,
  Copy,
  Eye,
  Code,
  Shield,
  Zap,
  AlertCircle,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import {
  getOpengrepRules,
  getOpengrepRule,
  toggleOpengrepRule,
  deleteOpengrepRule,
  generateOpengrepRule,
  RULE_SOURCES,
  SEVERITIES,
  type OpengrepRule,
  type OpengrepRuleDetail,
} from '@/shared/api/opengrep';
import { setOpengrepActiveRules } from '@/shared/stores/opengrepRulesStore';

interface OpengrepRulesProps {
  headerTitle?: string;
  headerDescription?: string;
}

export default function OpengrepRules(props: OpengrepRulesProps = {}) {
  const {
    headerTitle = '静态扫描规则管理',
    headerDescription = '管理和配置静态代码扫描规则',
  } = props;

  const [rules, setRules] = useState<OpengrepRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedLanguage, setSelectedLanguage] = useState<string>('');
  const [selectedSource, setSelectedSource] = useState<string>('');
  const [selectedSeverity, setSelectedSeverity] = useState<string>('');
  const [showRuleDetail, setShowRuleDetail] = useState(false);
  const [selectedRule, setSelectedRule] = useState<OpengrepRuleDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [availableLanguages, setAvailableLanguages] = useState<string[]>([]);
  const [allRules, setAllRules] = useState<OpengrepRule[]>([]); // 保存所有规则用于提取语言列表
  const [showGenerateDialog, setShowGenerateDialog] = useState(false);
  const [generatingRule, setGeneratingRule] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [selectedRuleIds, setSelectedRuleIds] = useState<Set<string>>(new Set());
  const [batchOperating, setBatchOperating] = useState(false);
  const [generateFormData, setGenerateFormData] = useState({
    repo_owner: '',
    repo_name: '',
    commit_hash: '',
    commit_content: '',
  });

  useEffect(() => {
    loadRules();
  }, []);

  // 当筛选条件改变时，重新加载规则
  useEffect(() => {
    if (!loading) {
      setCurrentPage(1);
      loadRules();
    }
  }, [selectedLanguage, selectedSource, selectedSeverity]);

  const loadRules = async () => {
    try {
      setLoading(true);
      const data = await getOpengrepRules({
        language: selectedLanguage || undefined,
        source: (selectedSource as 'internal' | 'patch') || undefined,
      });
      setRules(data);

      // 如果是首次加载或没有筛选条件，保存所有规则用于提取语言列表
      if (!selectedLanguage && !selectedSource) {
        setAllRules(data);
        // 提取所有唯一的编程语言
        const languages = Array.from(new Set(data.map(rule => rule.language))).sort();
        setAvailableLanguages(languages);
      }

      // 同步启用规则到全局缓存
      setOpengrepActiveRules(data.filter((rule) => rule.is_active));
    } catch (error) {
      console.error('Failed to load rules:', error);
      toast.error('加载规则失败');
    } finally {
      setLoading(false);
    }
  };

  const handleViewRule = async (rule: OpengrepRule) => {
    try {
      setLoadingDetail(true);
      const detail = await getOpengrepRule(rule.id);
      setSelectedRule(detail);
      setShowRuleDetail(true);
    } catch (error) {
      console.error('Failed to load rule detail:', error);
      toast.error('加载规则详情失败');
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleToggleRule = async (rule: OpengrepRule) => {
    try {
      await toggleOpengrepRule(rule.id);
      toast.success(`规则已${rule.is_active ? '禁用' : '启用'}`);
      loadRules();
    } catch (error) {
      console.error('Failed to toggle rule:', error);
      toast.error('更新规则失败');
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    if (!confirm('确定要删除此规则吗?')) return;

    try {
      await deleteOpengrepRule(ruleId);
      toast.success('规则已删除');
      loadRules();
      setShowRuleDetail(false);
    } catch (error) {
      console.error('Failed to delete rule:', error);
      toast.error('删除规则失败');
    }
  };

  const handleGenerateRule = async () => {
    if (!generateFormData.repo_owner || !generateFormData.repo_name || !generateFormData.commit_hash || !generateFormData.commit_content) {
      toast.error('请填写所有必需字段');
      return;
    }
    try {
      setGeneratingRule(true);
      await generateOpengrepRule(generateFormData);
      toast.success('规则生成成功');
      setShowGenerateDialog(false);
      setGenerateFormData({
        repo_owner: '',
        repo_name: '',
        commit_hash: '',
        commit_content: '',
      });
      loadRules();
    } catch (error) {
      console.error('Failed to generate rule:', error);
      toast.error('生成规则失败');
    } finally {
      setGeneratingRule(false);
    }
  };

  const handleResetFilters = () => {
    setSearchTerm('');
    setSelectedLanguage('');
    setSelectedSource('');
    setSelectedSeverity('');
    setCurrentPage(1);
    setSelectedRuleIds(new Set());
  };

  const handleToggleRuleSelection = (ruleId: string) => {
    const newSet = new Set(selectedRuleIds);
    if (newSet.has(ruleId)) {
      newSet.delete(ruleId);
    } else {
      newSet.add(ruleId);
    }
    setSelectedRuleIds(newSet);
  };

  const handleToggleAllSelection = () => {
    if (selectedRuleIds.size === paginatedRules.length) {
      setSelectedRuleIds(new Set());
    } else {
      setSelectedRuleIds(new Set(paginatedRules.map(r => r.id)));
    }
  };

  const handleBatchUpdateRules = async (isActive: boolean) => {
    if (selectedRuleIds.size === 0) {
      toast.error('请先选择要操作的规则');
      return;
    }

    try {
      setBatchOperating(true);
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'}/v1/static-tasks/rules/select`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`,
        },
        body: JSON.stringify({
          rule_ids: Array.from(selectedRuleIds),
          is_active: isActive,
        }),
      });

      if (!response.ok) {
        throw new Error('批量操作失败');
      }

      const result = await response.json();
      toast.success(result.message);
      setSelectedRuleIds(new Set());
      loadRules();
    } catch (error) {
      console.error('Batch operation failed:', error);
      toast.error('批量操作失败');
    } finally {
      setBatchOperating(false);
    }
  };

  const filteredRules = rules.filter((rule) => {
    const matchSearch =
      rule.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      rule.id.toLowerCase().includes(searchTerm.toLowerCase());

    const matchLanguage = !selectedLanguage || rule.language === selectedLanguage;
    const matchSeverity = !selectedSeverity || rule.severity === selectedSeverity;

    return matchSearch && matchLanguage && matchSeverity;
  });

  // 分页逻辑
  const totalPages = Math.ceil(filteredRules.length / pageSize);
  const paginatedRules = filteredRules.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'ERROR':
        return 'bg-rose-500/20 text-rose-300 border-rose-500/30';
      case 'WARNING':
        return 'bg-amber-500/20 text-amber-300 border-amber-500/30';
      case 'INFO':
        return 'bg-sky-500/20 text-sky-300 border-sky-500/30';
      default:
        return 'bg-muted text-muted-foreground';
    }
  };

  const getSourceBadge = (source: string) => {
    return source === 'patch' ? '从Patch生成' : '内置规则';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center space-y-4">
          <div className="loading-spinner mx-auto" />
          <p className="text-muted-foreground font-mono text-sm uppercase tracking-wider">
            加载规则数据...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-background font-mono relative overflow-hidden">
      {/* Grid background */}
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
      
      {/* Scrollable Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="space-y-6 p-6 relative z-10">

      {/* Header */}
      <div className="relative z-10">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-3xl font-bold text-foreground uppercase tracking-wider flex items-center gap-2">
              <Shield className="w-8 h-8 text-primary" />
              {headerTitle}
            </h1>
            <p className="text-muted-foreground font-mono text-sm mt-1">
              {headerDescription}
            </p>
          </div>
          <div className="text-right">
            <p className="text-2xl font-bold text-primary">{filteredRules.length}</p>
            <p className="text-xs text-muted-foreground">活跃规则</p>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
          <div className="cyber-card p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="stat-label">总规则数</p>
                <p className="stat-value">{rules.length}</p>
              </div>
              <Code className="w-6 h-6 text-primary" />
            </div>
          </div>

          <div className="cyber-card p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="stat-label">已启用</p>
                <p className="stat-value">{rules.filter((r) => r.is_active).length}</p>
              </div>
              <CheckCircle className="w-6 h-6 text-emerald-400" />
            </div>
          </div>

          <div className="cyber-card p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="stat-label">已选择</p>
                <p className="stat-value">{selectedRuleIds.size}</p>
              </div>
              <Shield className="w-6 h-6 text-sky-400" />
            </div>
          </div>

          <div className="cyber-card p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="stat-label">生成规则</p>
                <p className="stat-value">{rules.filter((r) => r.source === 'patch').length}</p>
              </div>
              <Zap className="w-6 h-6 text-amber-400" />
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="cyber-card p-4 relative z-10 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">
          <div>
            <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
              搜索
            </Label>
            <div className="relative mt-1.5">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-4 h-4" />
              <Input
                placeholder="规则名称或ID..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="cyber-input !pl-10"
              />
            </div>
          </div>

          <div>
            <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
              编程语言
            </Label>
            <Select value={selectedLanguage || 'all'} onValueChange={(val) => setSelectedLanguage(val === 'all' ? '' : val)}>
              <SelectTrigger className="cyber-input mt-1.5">
                <SelectValue placeholder="所有语言" />
              </SelectTrigger>
              <SelectContent className="cyber-dialog border-border">
                <SelectItem value="all">所有语言</SelectItem>
                {availableLanguages.map((lang) => (
                  <SelectItem key={lang} value={lang}>
                    {lang}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
              规则来源
            </Label>
            <Select value={selectedSource || 'all'} onValueChange={(val) => setSelectedSource(val === 'all' ? '' : val)}>
              <SelectTrigger className="cyber-input mt-1.5">
                <SelectValue placeholder="所有来源" />
              </SelectTrigger>
              <SelectContent className="cyber-dialog border-border">
                <SelectItem value="all">所有来源</SelectItem>
                {RULE_SOURCES.map((source) => (
                  <SelectItem key={source.value} value={source.value}>
                    {source.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
              严重程度
            </Label>
            <Select value={selectedSeverity || 'all'} onValueChange={(val) => setSelectedSeverity(val === 'all' ? '' : val)}>
              <SelectTrigger className="cyber-input mt-1.5">
                <SelectValue placeholder="所有级别" />
              </SelectTrigger>
              <SelectContent className="cyber-dialog border-border">
                <SelectItem value="all">所有级别</SelectItem>
                {SEVERITIES.map((severity) => (
                  <SelectItem key={severity.value} value={severity.value}>
                    {severity.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="md:col-span-2 xl:col-span-1 flex flex-wrap items-end gap-2">
            <Button
              variant="outline"
              onClick={handleResetFilters}
              className="cyber-btn-outline h-10 min-w-[110px] flex-1 sm:flex-none"
            >
              重置
            </Button>
            <Button
              onClick={() => setShowGenerateDialog(true)}
              className="cyber-btn-primary h-10 min-w-[150px] flex-1 sm:flex-none whitespace-nowrap"
            >
              <Zap className="w-4 h-4 mr-2" />
              生成新规则
            </Button>
          </div>
        </div>
      </div>

      {/* Batch Operations */}
      {selectedRuleIds.size > 0 && (
        <div className="cyber-card p-4 relative z-10 bg-primary/5 border-primary/30">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <p className="font-mono text-sm">已选择 <span className="font-bold text-primary">{selectedRuleIds.size}</span> 条规则</p>
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => handleBatchUpdateRules(true)}
                disabled={batchOperating}
                className="cyber-btn-primary h-9 text-sm"
              >
                {batchOperating ? '处理中...' : '批量启用'}
              </Button>
              <Button
                onClick={() => handleBatchUpdateRules(false)}
                disabled={batchOperating}
                className="cyber-btn-outline h-9 text-sm"
              >
                {batchOperating ? '处理中...' : '批量禁用'}
              </Button>
              <Button
                onClick={() => setSelectedRuleIds(new Set())}
                disabled={batchOperating}
                className="cyber-btn-ghost h-9 text-sm"
              >
                取消选择
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Rules Table */}
      <div className="cyber-card relative z-10 overflow-hidden">
        {filteredRules.length === 0 ? (
          <div className="p-16 text-center">
            <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-bold text-foreground mb-2">未找到规则</h3>
            <p className="text-muted-foreground font-mono text-sm">
              {searchTerm || selectedLanguage || selectedSource || selectedSeverity
                ? '调整筛选条件尝试'
                : '暂无规则数据'}
            </p>
          </div>
        ) : (
          <>
            <div>
              {/* Table Header with Select All */}
              <div className="flex items-center gap-3 p-4 border-b border-border bg-muted/30">
                <Checkbox
                  checked={selectedRuleIds.size === paginatedRules.length && paginatedRules.length > 0}
                  onCheckedChange={handleToggleAllSelection}
                  className="w-4 h-4"
                />
                <span className="text-sm font-mono text-muted-foreground">
                  {selectedRuleIds.size > 0 ? `已选择 ${selectedRuleIds.size} 条` : '全选当前页'}
                </span>
              </div>

              {/* Rules List */}
              <ScrollArea className="h-[calc(100vh-600px)] min-h-[400px]">
                <div className="divide-y divide-border">
                  {paginatedRules.map((rule) => (
                    <div
                      key={rule.id}
                      className="p-4 hover:bg-muted/50 transition-colors border-b border-border last:border-0"
                    >
                      <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-4">
                        <div className="flex gap-3 flex-1 min-w-0">
                          <Checkbox
                            checked={selectedRuleIds.has(rule.id)}
                            onCheckedChange={() => handleToggleRuleSelection(rule.id)}
                            className="w-4 h-4 mt-1"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-2">
                              <h3 className="font-bold text-foreground truncate">{rule.name}</h3>
                              <Badge className={`cyber-badge ${getSeverityColor(rule.severity)}`}>
                                {rule.severity}
                              </Badge>
                              <Badge
                                className={`cyber-badge ${rule.source === 'patch'
                                    ? 'cyber-badge-warning'
                                    : 'cyber-badge-info'
                                  }`}
                              >
                                {getSourceBadge(rule.source)}
                              </Badge>
                              {rule.is_active ? (
                                <Badge className="cyber-badge cyber-badge-success">已启用</Badge>
                              ) : (
                                <Badge className="cyber-badge cyber-badge-muted">已禁用</Badge>
                              )}
                            </div>

                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs text-muted-foreground font-mono">
                              <div>
                                <span className="text-muted-foreground">ID: </span>
                                <span className="text-foreground font-bold">{rule.id.substring(0, 8)}</span>
                              </div>
                              <div>
                                <span className="text-muted-foreground">语言: </span>
                                <span className="text-foreground font-bold">{rule.language}</span>
                              </div>
                              <div>
                                <span className="text-muted-foreground">状态: </span>
                                <span className={rule.correct ? 'text-emerald-400' : 'text-amber-400'}>
                                  {rule.correct ? '✓ 正确' : '⚠ 未验证'}
                                </span>
                              </div>
                              <div>
                                <span className="text-muted-foreground">创建: </span>
                                <span className="text-foreground font-bold">
                                  {new Date(rule.created_at).toLocaleDateString('zh-CN')}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>

                        <div className="flex flex-wrap items-center gap-2 xl:justify-end">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleViewRule(rule)}
                            className="cyber-btn-ghost h-8 px-3 min-w-[64px]"
                          >
                            <Eye className="w-4 h-4" />
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleToggleRule(rule)}
                            className={`cyber-btn-ghost h-8 px-3 min-w-[72px] ${rule.is_active ? 'hover:bg-rose-500/10' : 'hover:bg-emerald-500/10'
                              }`}
                          >
                            {rule.is_active ? '禁用' : '启用'}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleDeleteRule(rule.id)}
                            className="cyber-btn-ghost h-8 px-3 min-w-[64px] hover:bg-rose-500/10 hover:text-rose-400"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between p-4 border-t border-border bg-muted/20">
              <div className="flex items-center gap-2">
                <Label className="text-xs font-mono text-muted-foreground">每页显示:</Label>
                <Select value={pageSize.toString()} onValueChange={(val) => {
                  setPageSize(Number(val));
                  setCurrentPage(1);
                }}>
                  <SelectTrigger className="cyber-input w-[80px] h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="cyber-dialog border-border">
                    <SelectItem value="10">10</SelectItem>
                    <SelectItem value="20">20</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                    <SelectItem value="100">100</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="text-xs font-mono text-muted-foreground">
                第 {currentPage} / {totalPages} 页 (共 {filteredRules.length} 条)
              </div>

              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                  disabled={currentPage === 1}
                  className="cyber-btn-ghost h-8 px-2 w-8"
                >
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <div className="flex items-center gap-1">
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    const page = Math.max(1, currentPage - 2) + i;
                    if (page > totalPages) return null;
                    return (
                      <Button
                        key={page}
                        size="sm"
                        variant={page === currentPage ? 'default' : 'outline'}
                        onClick={() => setCurrentPage(page)}
                        className={`cyber-btn-${page === currentPage ? 'primary' : 'ghost'} h-8 px-2 min-w-8`}
                      >
                        {page}
                      </Button>
                    );
                  })}
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                  disabled={currentPage === totalPages}
                  className="cyber-btn-ghost h-8 px-2 w-8"
                >
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Rule Detail Dialog */}
      <Dialog open={showRuleDetail} onOpenChange={setShowRuleDetail}>
        <DialogContent className="!w-[min(90vw,900px)] !max-w-none max-h-[90vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg">
          {/* Terminal Header */}
          <div className="flex items-center gap-2 px-4 py-3 cyber-bg-elevated border-b border-border flex-shrink-0">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full bg-red-500/80" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
              <div className="w-3 h-3 rounded-full bg-green-500/80" />
            </div>
            <span className="ml-2 font-mono text-xs text-muted-foreground tracking-wider">
              rule_detail@deepaudit
            </span>
          </div>

          <DialogHeader className="px-6 pt-4 flex-shrink-0">
            <DialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
              <Code className="w-5 h-5 text-primary" />
              规则详情
            </DialogTitle>
          </DialogHeader>

          {loadingDetail ? (
            <div className="flex items-center justify-center p-8">
              <div className="loading-spinner" />
            </div>
          ) : selectedRule ? (
            <div className="flex-1 overflow-y-auto p-6">
              <div className="space-y-6">
                {/* Basic Info */}
                <div className="space-y-3">
                  <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                    基本信息
                  </h3>
                  <div className="grid grid-cols-2 gap-4 text-sm font-mono">
                    <div>
                      <p className="text-muted-foreground">名称</p>
                      <p className="text-foreground font-bold mt-1">{selectedRule.name}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">规则ID</p>
                      <p className="text-foreground font-bold mt-1 break-all">{selectedRule.id}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">编程语言</p>
                      <p className="text-foreground font-bold mt-1">{selectedRule.language}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">严重程度</p>
                      <Badge className={`cyber-badge mt-1 ${getSeverityColor(selectedRule.severity)}`}>
                        {selectedRule.severity}
                      </Badge>
                    </div>
                    <div>
                      <p className="text-muted-foreground">规则来源</p>
                      <Badge className={`cyber-badge mt-1 ${selectedRule.source === 'patch' ? 'cyber-badge-warning' : 'cyber-badge-info'}`}>
                        {getSourceBadge(selectedRule.source)}
                      </Badge>
                    </div>
                    <div>
                      <p className="text-muted-foreground">验证状态</p>
                      <p className={`font-bold mt-1 ${selectedRule.correct ? 'text-emerald-400' : 'text-amber-400'}`}>
                        {selectedRule.correct ? '✓ 正确' : '⚠ 未验证'}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Pattern YAML */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground">
                      规则模式
                    </h3>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        navigator.clipboard.writeText(selectedRule.pattern_yaml);
                        toast.success('已复制到剪贴板');
                      }}
                      className="cyber-btn-ghost h-7 text-xs"
                    >
                      <Copy className="w-3 h-3" />
                    </Button>
                  </div>
                  <div className="bg-muted border border-border rounded p-4">
                    <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words">
                      {selectedRule.pattern_yaml}
                    </pre>
                  </div>
                </div>

                {/* Patch Info */}
                {selectedRule.source === 'patch' && selectedRule.patch && (
                  <div className="space-y-3">
                    <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                      生成来源
                    </h3>
                    <div className="bg-muted border border-border rounded p-4">
                      <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words">
                        {selectedRule.patch}
                      </pre>
                    </div>
                  </div>
                )}

                {/* Metadata */}
                <div className="space-y-3">
                  <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                    元数据
                  </h3>
                  <div className="text-sm font-mono text-muted-foreground">
                    <p>创建时间: {new Date(selectedRule.created_at).toLocaleString('zh-CN')}</p>
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          {/* Footer */}
          <div className="flex-shrink-0 flex justify-end gap-3 px-6 py-4 bg-muted border-t border-border">
            <Button
              variant="outline"
              onClick={() => setShowRuleDetail(false)}
              className="cyber-btn-outline"
            >
              关闭
            </Button>
            <Button
              variant="outline"
              onClick={() => selectedRule && handleDeleteRule(selectedRule.id)}
              className="cyber-btn-ghost hover:bg-rose-500/10 hover:text-rose-400"
            >
              <Trash2 className="w-4 h-4 mr-2" />
              删除规则
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Generate Rule Dialog */}
      <Dialog open={showGenerateDialog} onOpenChange={setShowGenerateDialog}>
        <DialogContent className="cyber-dialog max-w-2xl border-border">
          <div className="absolute inset-0 opacity-5 pointer-events-none" style={{
            backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(34, 197, 94, 0.1) 2px, rgba(34, 197, 94, 0.1) 4px)',
            backgroundSize: '100% 4px',
          }} />
          <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-cyan-500 via-green-500 to-cyan-500" />
          <DialogHeader className="px-6 pt-4 flex-shrink-0">
            <DialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
              根据Patch生成规则
            </DialogTitle>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            <div>
              <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">仓库所有者</Label>
              <Input
                value={generateFormData.repo_owner}
                onChange={(e) => setGenerateFormData({ ...generateFormData, repo_owner: e.target.value })}
                placeholder="例如: owner"
                className="cyber-input mt-1.5"
              />
            </div>

            <div>
              <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">仓库名称</Label>
              <Input
                value={generateFormData.repo_name}
                onChange={(e) => setGenerateFormData({ ...generateFormData, repo_name: e.target.value })}
                placeholder="例如: repository"
                className="cyber-input mt-1.5"
              />
            </div>

            <div>
              <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">提交哈希</Label>
              <Input
                value={generateFormData.commit_hash}
                onChange={(e) => setGenerateFormData({ ...generateFormData, commit_hash: e.target.value })}
                placeholder="例如: abc123def456"
                className="cyber-input mt-1.5"
              />
            </div>

            <div>
              <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">Patch内容</Label>
              <Textarea
                value={generateFormData.commit_content}
                onChange={(e) => setGenerateFormData({ ...generateFormData, commit_content: e.target.value })}
                placeholder="粘贴补丁内容..."
                className="cyber-input mt-1.5 font-mono text-xs min-h-48"
              />
            </div>
          </div>

          <div className="flex-shrink-0 flex justify-end gap-3 px-6 py-4 bg-muted border-t border-border">
            <Button
              variant="outline"
              onClick={() => setShowGenerateDialog(false)}
              className="cyber-btn-outline"
              disabled={generatingRule}
            >
              取消
            </Button>
            <Button
              onClick={handleGenerateRule}
              className="cyber-btn-primary"
              disabled={generatingRule}
            >
              {generatingRule ? (
                <>
                  <div className="loading-spinner mr-2" />
                  生成中...
                </>
              ) : (
                <>生成规则</>
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
        </div>
      </div>
    </div>
  );
}
