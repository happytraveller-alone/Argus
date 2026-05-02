import { useNavigate } from 'react-router-dom';
import { Construction } from 'lucide-react';

export default function InDevelopmentPlaceholder() {
  const navigate = useNavigate();

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="text-center max-w-md px-6">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-100 dark:bg-blue-900/30 mb-4">
          <Construction className="w-8 h-8 text-blue-600 dark:text-blue-400" />
        </div>
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
          智能审计 · 重构中
        </h1>
        <p className="text-gray-600 dark:text-gray-400 mb-6">
          智能审计功能正在进行架构升级，敬请期待更强大的新版本。
        </p>
        <button
          onClick={() => navigate('/dashboard')}
          className="inline-flex items-center px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors"
        >
          返回仪表盘
        </button>
      </div>
    </div>
  );
}
