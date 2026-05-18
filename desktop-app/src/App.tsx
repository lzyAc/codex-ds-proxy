import React, { useEffect, useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { ProxyStatus, LogEntry, ProxyConfig, AppState } from "./types";
import StatusCard from "./components/StatusCard";
import LogPanel from "./components/LogPanel";
import SettingsPanel from "./components/SettingsPanel";
import ProxyToggle from "./components/ProxyToggle";
import Sidebar from "./components/Sidebar";

type Tab = "status" | "logs" | "settings";

export default function App() {
  const [state, setState] = useState<AppState>({
    proxyStatus: null,
    logs: [],
    config: null,
    loading: true,
    error: null,
    keyValid: null,
    checkingKey: false,
  });
  const [activeTab, setActiveTab] = useState<Tab>("status");
  const [darkMode, setDarkMode] = useState(true);

  // ── 加载初始数据 ──
  useEffect(() => {
    loadInitialData();

    // 监听代理事件
    const unlisten1 = listen("proxy-started", () => {
      refreshStatus();
    });
    const unlisten2 = listen("proxy-stopped", () => {
      setState((s) => ({
        ...s,
        proxyStatus: { running: false, port: 8787, uptime_seconds: 0, total_requests: 0 },
        logs: [],
      }));
    });

    // 定时轮询状态（每 2 秒）
    const interval = setInterval(refreshStatus, 2000);

    return () => {
      unlisten1.then((f) => f());
      unlisten2.then((f) => f());
      clearInterval(interval);
    };
  }, []);

  // eslint-disable-next-line
  // 暗色模式同步
  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [darkMode]);

  const loadInitialData = async () => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const config: ProxyConfig = await invoke("get_config");
      setDarkMode(config.dark_mode);
      setState((s) => ({ ...s, config, loading: false }));
      await refreshStatus();
    } catch (e) {
      setState((s) => ({ ...s, loading: false, error: String(e) }));
    }
  };

  const refreshStatus = useCallback(async () => {
    try {
      const status: ProxyStatus = await invoke("get_proxy_status");
      setState((s) => ({ ...s, proxyStatus: status }));
    } catch {
      // ignore
    }
  }, []);

  const refreshLogs = useCallback(async () => {
    try {
      const result = await invoke("get_logs", { limit: 100 });
      const data = result as { logs: LogEntry[] };
      setState((s) => ({ ...s, logs: data.logs }));
    } catch {
      // ignore
    }
  }, []);

  const handleStartProxy = useCallback(
    async (apiKey: string, port: number) => {
      try {
        setState((s) => ({ ...s, error: null }));
        await invoke("start_proxy", { apiKey, port: port || null });
        await refreshStatus();
      } catch (e) {
        setState((s) => ({ ...s, error: String(e) }));
      }
    },
    [refreshStatus]
  );

  const handleStopProxy = useCallback(async () => {
    try {
      setState((s) => ({ ...s, error: null }));
      await invoke("stop_proxy");
      await refreshStatus();
    } catch (e) {
      setState((s) => ({ ...s, error: String(e) }));
    }
  }, [refreshStatus]);

  const handleCheckKey = useCallback(async (key: string) => {
    setState((s) => ({ ...s, checkingKey: true, keyValid: null }));
    try {
      const valid: boolean = await invoke("check_api_key", { key });
      setState((s) => ({ ...s, keyValid: valid, checkingKey: false }));
    } catch {
      setState((s) => ({ ...s, keyValid: false, checkingKey: false }));
    }
  }, []);

  const handleSaveConfig = useCallback(
    async (config: ProxyConfig) => {
      try {
        await invoke("save_config", { config });
        setState((s) => ({ ...s, config }));
        setDarkMode(config.dark_mode);
      } catch (e) {
        setState((s) => ({ ...s, error: String(e) }));
      }
    },
    []
  );

  const isRunning = state.proxyStatus?.running ?? false;

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50 dark:bg-gray-950">
      {/* 侧边栏 */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        isRunning={isRunning}
      />

      {/* 主内容区 */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* 顶部渐变栏 */}
        <header className="gradient-bg px-6 py-4 shrink-0">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">
                Codex-DS 代理
              </h1>
              <p className="text-sm text-white/70 mt-0.5">
                将 Claude / Codex CLI 无缝切换到 DeepSeek
              </p>
            </div>
            <ProxyToggle
              isRunning={isRunning}
              onStart={() =>
                handleStartProxy(
                  state.config?.api_key || "",
                  state.config?.proxy_port || 8787
                )
              }
              onStop={handleStopProxy}
            />
          </div>
        </header>

        {/* 错误提示 */}
        {state.error && (
          <div className="mx-6 mt-4 px-4 py-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-xl text-sm text-red-700 dark:text-red-300 flex items-center justify-between animate-fade-in">
            <span>{state.error}</span>
            <button
              onClick={() => setState((s) => ({ ...s, error: null }))}
              className="ml-2 text-red-500 hover:text-red-700 dark:hover:text-red-200"
            >
              ✕
            </button>
          </div>
        )}

        {/* 主面板 */}
        <div className="flex-1 overflow-auto p-6">
          {state.loading ? (
            <LoadingScreen />
          ) : (
            <>
              {activeTab === "status" && (
                <StatusCard
                  status={state.proxyStatus}
                  onStart={() =>
                    handleStartProxy(
                      state.config?.api_key || "",
                      state.config?.proxy_port || 8787
                    )
                  }
                  onStop={handleStopProxy}
                  isRunning={isRunning}
                  config={state.config}
                />
              )}
              {activeTab === "logs" && (
                <LogPanel logs={state.logs} onRefresh={refreshLogs} />
              )}
              {activeTab === "settings" && (
                <SettingsPanel
                  config={state.config}
                  onSave={handleSaveConfig}
                  onCheckKey={handleCheckKey}
                  keyValid={state.keyValid}
                  checkingKey={state.checkingKey}
                />
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function LoadingScreen() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm text-gray-500 dark:text-gray-400">加载中...</p>
      </div>
    </div>
  );
}
