import React, { useEffect, useRef } from "react";
import { LogEntry } from "../types";

interface LogPanelProps {
  logs: LogEntry[];
  onRefresh: () => void;
}

function formatLogTime(rawTime: string): string {
  if (!rawTime) return "--:--:--";
  // 如果已经是 HH:MM:SS 格式（如来自 Rust 的错误信息）
  if (rawTime.length <= 8 && rawTime.includes(":")) return rawTime;
  // 如果是 ISO 格式如 "2026-05-18T10:30:00.000000+08:00"
  // 尝试提取 T 后面的 HH:MM:SS
  const tIndex = rawTime.indexOf("T");
  if (tIndex !== -1 && rawTime.length > tIndex + 9) {
    return rawTime.slice(tIndex + 1, tIndex + 9);
  }
  // 提取 HH:MM:SS
  const match = rawTime.match(/(\d{2}:\d{2}:\d{2})/);
  return match ? match[1] : rawTime.slice(-8);
}

export default function LogPanel({ logs, onRefresh }: LogPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const logCount = logs.length;
  const errorCount = logs.filter((l) => l.level === "error").length;

  return (
    <div className="max-w-4xl mx-auto animate-fade-in">
      <div className="card">
        <div className="card-header flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              请求日志
            </h2>
            {logCount > 0 && (
              <span className="text-xs text-gray-400 dark:text-gray-500">
                {logCount} 条
                {errorCount > 0 && (
                  <span className="text-red-400 ml-1">({errorCount} 错误)</span>
                )}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {logCount > 0 ? `最新: ${formatLogTime(logs[logCount - 1].time)}` : ""}
            </span>
            <button onClick={onRefresh} className="btn-secondary text-xs !py-1.5 !px-3">
              刷新
            </button>
          </div>
        </div>

        <div
          ref={scrollRef}
          className="card-body overflow-y-auto"
          style={{ maxHeight: "60vh" }}
        >
          {logs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-gray-400 dark:text-gray-500">
              <span className="text-4xl mb-3 opacity-30">≡</span>
              <p className="text-sm">暂无日志</p>
              <p className="text-xs mt-1">
                启动代理并发送请求后，日志将在此显示
              </p>
            </div>
          ) : (
            <div className="space-y-0.5">
              {logs.map((log, i) => (
                <div
                  key={i}
                  className={`flex items-start gap-2 px-3 py-2 rounded-md text-xs font-mono leading-5 transition-colors
                    ${
                      log.level === "error"
                        ? "bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300"
                        : log.level === "warn"
                          ? "bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-300"
                          : "bg-gray-50 dark:bg-gray-800/30 text-gray-700 dark:text-gray-300"
                    }
                  `}
                >
                  {/* 时间戳 */}
                  <span className="shrink-0 text-gray-400 dark:text-gray-500 min-w-[4.5rem] text-right">
                    {formatLogTime(log.time)}
                  </span>

                  {/* 分隔符 */}
                  <span className="shrink-0 text-gray-300 dark:text-gray-600">|</span>

                  {/* 级别指示器 */}
                  <span
                    className={`shrink-0 min-w-[3.5rem] text-center font-semibold ${
                      log.level === "error"
                        ? "text-red-500"
                        : log.level === "warn"
                          ? "text-yellow-500"
                          : "text-emerald-500"
                    }`}
                  >
                    {log.level === "error" ? "ERROR" : log.level === "warn" ? "WARN" : "INFO"}
                  </span>

                  {/* 分隔符 */}
                  <span className="shrink-0 text-gray-300 dark:text-gray-600">|</span>

                  {/* 消息内容 — 允许换行 */}
                  <span className="flex-1 break-all whitespace-pre-wrap">
                    {log.message}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
