
import React, { Component, ReactNode } from 'react';
import { logger, LogCategory } from '@/shared/utils/logger';
import {
  resolveErrorBoundaryViewModel,
  type ErrorBoundaryViewModel,
} from './errorBoundaryState';
import { ErrorBoundaryFallbackView } from './ErrorBoundaryFallbackView';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
  viewModel: ErrorBoundaryViewModel | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      viewModel: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return {
      hasError: true,
      error,
      viewModel: resolveErrorBoundaryViewModel(error),
    };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    const viewModel = resolveErrorBoundaryViewModel(error);

    logger.error(
      LogCategory.CONSOLE_ERROR,
      `React组件错误: ${error.message}`,
      {
        error: error.toString(),
        componentStack: errorInfo.componentStack,
        errorVariant: viewModel.variant,
      },
      error.stack
    );

    this.setState({
      errorInfo,
      viewModel,
    });

    this.props.onError?.(error, errorInfo);
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      viewModel: null,
    });
  };

  handleReload = () => {
    window.location.reload();
  };

  handleGoHome = () => {
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      const viewModel =
        this.state.viewModel ||
        resolveErrorBoundaryViewModel(this.state.error);

      return (
        <ErrorBoundaryFallbackView
          state={viewModel}
          error={this.state.error}
          errorInfo={this.state.errorInfo}
          onReset={this.handleReset}
          onGoHome={this.handleGoHome}
          onReload={this.handleReload}
          isDev={import.meta.env.DEV}
        />
      );
    }

    return this.props.children;
  }
}

export function withErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  fallback?: ReactNode
) {
  return function WithErrorBoundaryComponent(props: P) {
    return (
      <ErrorBoundary fallback={fallback}>
        <Component {...props} />
      </ErrorBoundary>
    );
  };
}
