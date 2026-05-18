import React, { useState, useEffect } from "react";
import { ProxyConfig } from "../types";

interface SettingsPanelProps {
  config: ProxyConfig | null;
  onSave: (config: ProxyConfig) => void;
  onCheckKey: (key: string) => void;
  keyValid: boolean | null;
  checkingKey: boolean;
}

export default function SettingsPanel({
  config,
  onSave,
  onCheckKey,
  keyValid,
  checkingKey,
}: SettingsPanelProps) {
  const [form, setForm] = useState<ProxyConfig>(
    config || {
      api_key: "",
      proxy_port: 8787,
      web_port: 8788,
      auto_start: true,
      dark_mode: true,
      model_mapping: {},
    }
  );
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [showKey, setShowKey] = useState(false);

  useEffect(() => {
    if (config) setForm(config);
  }, [config]);

  const handleSave = async () => {
    setSaving(true);
    await onSave(form);
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const modelEntries = Object.entries(form.model_mapping);

  return (
    <div className="max-w-2xl mx-auto animate-fade-in space-y-6">
      {/* API Key */}
      <div className="card">
        <div className="card-header">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            DeepSeek API Key
          </h3>
        </div>
        <div className="card-body space-y-4">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type={showKey ? "text" : "password"}
                className="input pr-10"
                placeholder="sk-..."
                value={form.api_key}
                onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              />
              <button
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                {showKey ? "🙈" : "👁"}
              </button>
            </div>
            <button
              onClick={() => onCheckKey(form.api_key)}
              disabled={!form.api_key || checkingKey}
              className="btn-secondary !py-2.5"
            >
              {checkingKey ? "验证中..." : "验证"}
            </button>
          </div>
          {keyValid !== null && (
            <div
              className={`text-xs flex items-center gap-1.5 ${
                keyValid
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-red-600 dark:text-red-400"
              }`}
            >
              {keyValid ? "✅ Key 有效" : "❌ Key 无效，请检查"}
            </div>
          )}
          <p className="text-xs text-gray-400 dark:text-gray-500">
            在 deepseek.com 获取 API Key。应用会自动保存到本地配置。
          </p>
        </div>
      </div>

      {/* 代理端口 */}
      <div className="card">
        <div className="card-header">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            代理设置
          </h3>
        </div>
        <div className="card-body space-y-4">
          <div className="flex items-center gap-4">
            <label className="text-sm text-gray-600 dark:text-gray-400 w-24">
              代理端口
            </label>
            <input
              type="number"
              className="input w-32"
              value={form.proxy_port}
              onChange={(e) =>
                setForm({ ...form, proxy_port: parseInt(e.target.value) || 8787 })
              }
            />
          </div>
          <div className="flex items-center gap-4">
            <label className="text-sm text-gray-600 dark:text-gray-400 w-24">
              管理端口
            </label>
            <input
              type="number"
              className="input w-32"
              value={form.web_port}
              onChange={(e) =>
                setForm({ ...form, web_port: parseInt(e.target.value) || 8788 })
              }
            />
          </div>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              className="w-4 h-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              checked={form.auto_start}
              onChange={(e) => setForm({ ...form, auto_start: e.target.checked })}
            />
            <span className="text-sm text-gray-600 dark:text-gray-400">
              启动应用时自动启动代理
            </span>
          </label>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              className="w-4 h-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              checked={form.dark_mode}
              onChange={(e) => setForm({ ...form, dark_mode: e.target.checked })}
            />
            <span className="text-sm text-gray-600 dark:text-gray-400">
              深色模式
            </span>
          </label>
        </div>
      </div>

      {/* 模型映射 */}
      <div className="card">
        <div className="card-header flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            模型映射
          </h3>
        </div>
        <div className="card-body">
          <div className="space-y-2">
            {modelEntries.map(([model, target], i) => (
              <div key={i} className="flex items-center gap-2 text-sm">
                <span className="text-gray-600 dark:text-gray-400 w-40 font-mono text-xs truncate">
                  {model}
                </span>
                <span className="text-gray-300 dark:text-gray-600">→</span>
                <select
                  className="input !py-1.5 !w-40"
                  value={target}
                  onChange={(e) => {
                    const newMapping = { ...form.model_mapping };
                    newMapping[model] = e.target.value;
                    setForm({ ...form, model_mapping: newMapping });
                  }}
                >
                  <option value="deepseek-v4-pro">deepseek-v4-pro</option>
                  <option value="deepseek-v4-flash">deepseek-v4-flash</option>
                  <option value="deepseek-chat">deepseek-chat</option>
                  <option value="deepseek-reasoner">deepseek-reasoner</option>
                </select>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-3">
            自定义 Claude 模型到 DeepSeek 模型的映射关系
          </p>
        </div>
      </div>

      {/* 保存 */}
      <button
        onClick={handleSave}
        disabled={saving}
        className="btn-primary w-full"
      >
        {saving ? "保存中..." : saved ? "✅ 已保存" : "保存设置"}
      </button>
    </div>
  );
}
