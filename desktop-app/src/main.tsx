import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

// ── 全局错误处理：捕获任何 JS 错误并显示在页面上 ──

function showFatalError(message: string, detail?: string) {
  const root = document.getElementById("root");
  if (!root) return;
  root.innerHTML = `
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;padding:40px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',sans-serif;background:#0f172a;color:#e2e8f0;">
      <h1 style="font-size:20px;font-weight:600;margin-bottom:12px;">应用加载失败</h1>
      <p style="font-size:14px;color:#94a3b8;max-width:500px;text-align:center;line-height:1.6;word-break:break-all;">${escapeHtml(message)}</p>
      ${detail ? `<pre style="margin-top:16px;padding:12px;background:#1e293b;border-radius:8px;font-size:12px;color:#f87171;max-width:500px;overflow:auto;text-align:left;line-height:1.5;word-break:break-all;">${escapeHtml(detail)}</pre>` : ""}
      <button onclick="location.reload()" style="margin-top:20px;padding:8px 24px;border-radius:8px;border:1px solid #334155;background:#1e293b;color:#e2e8f0;cursor:pointer;font-size:14px;">重新加载</button>
    </div>
  `;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// 监听全局错误
window.addEventListener("error", (event) => {
  event.preventDefault();
  const msg = event.error?.message || event.message || "未知错误";
  const stack = event.error?.stack || "";
  console.error("Global error:", msg, stack);
  showFatalError(msg, stack);
});

window.addEventListener("unhandledrejection", (event) => {
  event.preventDefault();
  const msg = event.reason?.message || event.reason || "未知 Promise 错误";
  const stack = event.reason?.stack || "";
  console.error("Unhandled rejection:", msg, stack);
  showFatalError(msg, stack);
});

// ── 错误边界组件 ──

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: string | null; stack: string | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null, stack: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message, stack: error.stack };
  }

  render() {
    if (this.state.hasError) {
      showFatalError(this.state.error || "未知错误", this.state.stack || undefined);
      return null;
    }
    return this.props.children;
  }
}

// ── 启动 React ──

const root = document.getElementById("root");
if (!root) {
  document.body.innerHTML =
    '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;color:#333"><p>应用初始化失败：找不到 root 节点</p></div>';
} else {
  try {
    ReactDOM.createRoot(root).render(
      <React.StrictMode>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </React.StrictMode>
    );
  } catch (e: any) {
    showFatalError(e?.message || "React 初始化失败", e?.stack);
  }
}
