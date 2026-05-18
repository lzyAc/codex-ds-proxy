import React from "react";

interface ProxyToggleProps {
  isRunning: boolean;
  onStart: () => void;
  onStop: () => void;
}

export default function ProxyToggle({ isRunning, onStart, onStop }: ProxyToggleProps) {
  return (
    <button
      onClick={isRunning ? onStop : onStart}
      className={`
        relative inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium
        transition-all duration-300 shadow-lg
        ${
          isRunning
            ? "bg-white/20 text-white hover:bg-white/30 backdrop-blur-sm"
            : "bg-white text-indigo-600 hover:bg-indigo-50"
        }
      `}
    >
      <span
        className={`w-2.5 h-2.5 rounded-full transition-all duration-500 ${
          isRunning ? "bg-emerald-400 animate-pulse" : "bg-gray-400"
        }`}
      />
      <span className="tracking-wide">
        {isRunning ? "停止代理" : "启动代理"}
      </span>
    </button>
  );
}
