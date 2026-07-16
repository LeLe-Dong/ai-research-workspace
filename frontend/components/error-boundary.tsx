"use client";
import { Component, ErrorInfo, ReactNode } from "react";
import Link from "next/link";
import { AlertTriangle, RefreshCw, Home, Bug } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Props {
  children: ReactNode;
  fallback?: (error: Error, reset: () => void) => ReactNode;
  level?: "page" | "section";
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

/**
 * Global Error Boundary for the entire app.
 * Catches React render errors and shows a user-friendly fallback.
 * Sends errors to the console for debugging.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({ errorInfo });
    // Log to console for debugging
    console.error("[ErrorBoundary] Caught error:", error, errorInfo);
  }

  reset = (): void => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render(): ReactNode {
    if (this.state.hasError && this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback(this.state.error, this.reset);
      }

      const isPage = this.props.level !== "section";
      return (
        <div className={isPage ? "container max-w-none px-6 py-12" : "p-6"}>
          <Card className="border-destructive/50 bg-destructive/5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-destructive">
                <AlertTriangle className="h-5 w-5" />
                {isPage ? "页面出错了" : "组件加载失败"}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {isPage 
                  ? "该页面遇到错误无法正常显示。错误已记录到浏览器控制台。"
                  : "该组件遇到错误无法正常加载。错误已记录到浏览器控制台。"}
              </p>

              {process.env.NODE_ENV === "development" && (
                <details className="rounded-md border bg-muted/30 p-3 text-xs">
                  <summary className="cursor-pointer font-medium">
                    <Bug className="mr-1.5 inline h-3.5 w-3.5" />
                    错误详情 (开发模式)
                  </summary>
                  <pre className="mt-2 overflow-auto whitespace-pre-wrap break-all text-[10px]">
                    {this.state.error.name}: {this.state.error.message}
                    {this.state.errorInfo?.componentStack && (
                      <span>{`

${this.state.errorInfo.componentStack}`}</span>
                    )}
                  </pre>
                </details>
              )}

              <div className="flex flex-wrap gap-2">
                <Button variant="default" size="sm" onClick={this.reset}>
                  <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                  重试
                </Button>
                {isPage && (
                  <Button variant="outline" size="sm" asChild>
                    <Link href="/dashboard">
                      <Home className="mr-1.5 h-3.5 w-3.5" />
                      返回工作台
                    </Link>
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={() => window.location.reload()}>
                  刷新页面
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      );
    }
    return this.props.children;
  }
}
