import React, { useEffect, useState, useCallback, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { ProxyStatus, ProxyConfig, AppState } from "./types";
import StatusCard from "./components/StatusCard";
import SettingsPanel from "./components/SettingsPanel";
import ProxyToggle from "./components/ProxyToggle";
import Sidebar from "./components/Sidebar";

type Tab = "status" | "settings";

export default function App() {
  const [state, setState] = useState<AppState>({
    proxyStatus: null,
    config: null,
    loading: true,
    starting: false,
    error: null,
    keyValid: null,
    checkingKey: false,
  });
  const [activeTab, setActiveTab] = useState<Tab>("status");
  const [darkMode, setDarkMode] = useState(true);
  const mountedRef = useRef(true);

  // ── 回调函数定义 ──

  const refreshStatus = useCallback(async () => {
    if (!mountedRef.current) return;
    try {
      const status: ProxyStatus = await invoke("get_proxy_status");
      if (mountedRef.current) {
        setState((s) => ({ ...s, proxyStatus: status }));
      }
    } catch {
      // ignore
    }
  }, []);

  const loadInitialData = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const config: ProxyConfig = await invoke("get_config");
      if (!mountedRef.current) return;
      setDarkMode(config.dark_mode);
      setState((s) => ({ ...s, config, loading: false }));
      await refreshStatus();
    } catch (e) {
      if (mountedRef.current) {
        setState((s) => ({ ...s, loading: false, error: String(e) }));
      }
    }
  }, [refreshStatus]);

  // ── 加载初始数据 ──
  useEffect(() => {
    mountedRef.current = true;
    const loadingTimeout = setTimeout(() => {
      if (mountedRef.current) {
        setState((s) => {
          if (s.loading) {
            return { ...s, loading: false, error: "加载超时" };
          }
          return s;
        });
      }
    }, 5000);

    loadInitialData().finally(() => clearTimeout(loadingTimeout));

    const unlisten1 = listen("proxy-started", () => {
      refreshStatus();
    });
    const unlisten2 = listen("proxy-stopped", () => {
      if (mountedRef.current) {
        setState((s) => ({
          ...s,
          proxyStatus: { running: false, port: 8787, uptime_seconds: 0, total_requests: 0 },
          starting: false,
        }));
      }
    });

    const statusInterval = setInterval(refreshStatus, 2000);

    return () => {
      mountedRef.current = false;
      unlisten1.then((f) => f());
      unlisten2.then((f) => f());
      clearInterval(statusInterval);
      clearTimeout(loadingTimeout);
    };
  }, []);

  // ── 暗色模式 ──
  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [darkMode]);

  // ── 启动/停止 ──

  const handleStartProxy = useCallback(
    async (apiKey: string, port: number) => {
      setState((s) => ({ ...s, error: null, starting: true }));
      try {
        await invoke("start_proxy", { apiKey, port: port || null });
        await refreshStatus();
      } catch (e) {
        setState((s) => ({ ...s, error: String(e) }));
      } finally {
        setState((s) => ({ ...s, starting: false }));
      }
    },
    [refreshStatus]
  );

  const handleStopProxy = useCallback(async () => {
    setState((s) => ({ ...s, error: null, starting: true }));
    try {
      await invoke("stop_proxy");
      await refreshStatus();
    } catch (e) {
      setState((s) => ({ ...s, error: String(e) }));
    } finally {
      setState((s) => ({ ...s, starting: false }));
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
      <Sidebar activeTab={activeTab} onTabChange={setActiveTab} isRunning={isRunning} />

      <main className="flex-1 flex flex-col overflow-hidden">
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
              isStarting={state.starting}
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
