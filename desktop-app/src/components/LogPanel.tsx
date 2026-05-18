import React, { useEffect, useRef } from "react";
import { LogEntry } from "../types";

interface LogPanelProps {
  logs: LogEntry[];
  onRefresh: () => void;
}

export default function LogPanel({ logs, onRefresh }: LogPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // 自动滚动到底部
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="max-w-4xl mx-auto animate-fade-in">
      <div className="card">
        <div className="card-header flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            请求日志
          </h2>
          <button onClick={onRefresh} className="btn-secondary text-xs !py-1.5 !px-3">
            刷新
          </button>
        </div>
        <div
          ref={scrollRef}
          className="card-body overflow-y-auto"
          style={{ maxHeight: "60vh" }}
        >
          {logs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-gray-400 dark:text-gray-500">
              <span className="text-4xl mb-3">≡</span>
              <p className="text-sm">暂无日志</p>
              <p className="text-xs mt-1">
                启动代理并发送请求后，日志将在此显示
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {logs.map((log, i) => (
                <div
                  key={i}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-mono transition-colors
                    ${
                      log.level === "error"
                        ? "bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300"
                        : "bg-gray-50 dark:bg-gray-800/30 text-gray-700 dark:text-gray-300"
                    }
                  `}
                >
                  <span className="text-gray-400 dark:text-gray-500 shrink-0 w-20">
                    {log.time ? log.time.slice(11, 19) : "--:--:--"}
                  </span>
                  <span className="text-gray-400 dark:text-gray-500 shrink-0">|</span>
                  <span
                    className={`shrink-0 w-12 ${
                      log.level === "error"
                        ? "text-red-500"
                        : "text-emerald-500"
                    }`}
                  >
                    {log.level === "error" ? "ERROR" : "INFO"}
                  </span>
                  <span className="text-gray-400 dark:text-gray-500 shrink-0">|</span>
                  <span className="flex-1 truncate">{log.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
