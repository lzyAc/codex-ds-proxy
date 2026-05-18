import React from "react";

type Tab = "status" | "logs" | "settings";

interface SidebarProps {
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
  isRunning: boolean;
}

const tabs: { id: Tab; label: string; icon: string }[] = [
  { id: "status", label: "状态", icon: "◎" },
  { id: "logs", label: "日志", icon: "≡" },
  { id: "settings", label: "设置", icon: "⚙" },
];

export default function Sidebar({ activeTab, onTabChange, isRunning }: SidebarProps) {
  return (
    <aside className="w-16 lg:w-48 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col items-center lg:items-stretch py-4 shrink-0">
      {/* Logo */}
      <div className="px-3 lg:px-5 mb-6 flex items-center justify-center lg:justify-start gap-2">
        <div className="w-8 h-8 rounded-lg gradient-bg flex items-center justify-center text-white text-xs font-bold shrink-0">
          CD
        </div>
        <span className="hidden lg:block text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
          Codex-DS
        </span>
      </div>

      {/* 导航 */}
      <nav className="flex-1 flex flex-col gap-1 px-2 lg:px-3">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`
              flex items-center justify-center lg:justify-start gap-3 px-3 py-2.5 rounded-xl text-sm
              transition-all duration-200
              ${
                activeTab === tab.id
                  ? "bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 font-medium"
                  : "text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
              }
            `}
          >
            <span className="text-lg">{tab.icon}</span>
            <span className="hidden lg:block">{tab.label}</span>
          </button>
        ))}
      </nav>

      {/* 底部状态 */}
      <div className="px-3 lg:px-5 mt-auto">
        <div className="flex items-center justify-center lg:justify-start gap-2 py-2">
          <span
            className={`w-2 h-2 rounded-full ${
              isRunning ? "bg-emerald-500 animate-pulse" : "bg-gray-400"
            }`}
          />
          <span className="hidden lg:block text-xs text-gray-500 dark:text-gray-400">
            {isRunning ? "运行中" : "已停止"}
          </span>
        </div>
      </div>
    </aside>
  );
}
