import React from "react";
import { ProxyStatus, ProxyConfig } from "../types";

interface StatusCardProps {
  status: ProxyStatus | null;
  onStart: () => void;
  onStop: () => void;
  isRunning: boolean;
  config: ProxyConfig | null;
}

export default function StatusCard({
  status,
  onStart,
  onStop,
  isRunning,
  config,
}: StatusCardProps) {
  const hasKey = config?.api_key && config.api_key.length > 0;

  const formatUptime = (seconds: number): string => {
    if (seconds < 60) return `${seconds}秒`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}分${seconds % 60}秒`;
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}小时${m}分`;
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-in">
      {/* 状态卡片 */}
      <div className="card">
        <div className="card-body">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              代理状态
            </h2>
            {isRunning && (
              <span className="tag-green flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
                运行中
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50">
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">代理端口</p>
              <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {config?.proxy_port || 8787}
              </p>
            </div>
            <div className="p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50">
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">请求次数</p>
              <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {status?.total_requests ?? 0}
              </p>
            </div>
            <div className="p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50">
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">运行时长</p>
              <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {isRunning ? formatUptime(status?.uptime_seconds ?? 0) : "—"}
              </p>
            </div>
            <div className="p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50">
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">API Key</p>
              <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {hasKey ? "✅ 已配置" : "⚠️ 未配置"}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* 使用说明 */}
      <div className="card">
        <div className="card-header">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            接入指南
          </h3>
        </div>
        <div className="card-body space-y-4 text-sm">
          <InstructionBlock
            title="Claude Desktop"
            steps={[
              { label: "API Base URL", value: `http://127.0.0.1:${config?.proxy_port || 8787}` },
              { label: "API Key", value: "deepseek-proxy" },
              { label: "模型", value: "选择 claude-opus-4.6 或 claude-opus-4.6-1m" },
            ]}
            port={config?.proxy_port || 8787}
          />

          <InstructionBlock
            title="Claude CLI"
            steps={[
              { label: "终端执行", value: `export ANTHROPIC_BASE_URL=http://127.0.0.1:${config?.proxy_port || 8787}` },
              { label: "终端执行", value: 'export ANTHROPIC_API_KEY="deepseek-proxy"' },
            ]}
            port={config?.proxy_port || 8787}
          />

          <InstructionBlock
            title="Codex CLI"
            steps={[
              { label: "终端执行", value: `export OPENAI_BASE_URL=http://127.0.0.1:${config?.proxy_port || 8787}/v1` },
              { label: "终端执行", value: 'export OPENAI_API_KEY="deepseek-proxy"' },
            ]}
            port={config?.proxy_port || 8787}
          />
        </div>
      </div>
    </div>
  );
}

function InstructionBlock({
  title,
  steps,
  port,
}: {
  title: string;
  steps: { label: string; value: string }[];
  port: number;
}) {
  const [copied, setCopied] = React.useState(false);

  const copyAll = () => {
    const text = steps.map((s) => s.value).join("\n");
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h4 className="font-medium text-gray-700 dark:text-gray-300">{title}</h4>
        <button
          onClick={copyAll}
          className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300"
        >
          {copied ? "✅ 已复制" : "复制全部"}
        </button>
      </div>
      <div className="space-y-1.5">
        {steps.map((step, i) => (
          <div
            key={i}
            className="flex items-center gap-2 p-2 rounded-lg bg-gray-50 dark:bg-gray-800/50 text-xs"
          >
            <span className="text-gray-400 dark:text-gray-500 shrink-0 w-20">
              {step.label}:
            </span>
            <code className="text-indigo-600 dark:text-indigo-400 font-mono break-all">
              {step.value}
            </code>
          </div>
        ))}
      </div>
    </div>
  );
}
