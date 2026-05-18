export interface ProxyStatus {
  running: boolean;
  port: number;
  uptime_seconds: number;
  total_requests: number;
}

export interface LogEntry {
  time: string;
  message: string;
  level: string;
}

export interface ProxyLogResponse {
  logs: LogEntry[];
}

export interface ProxyConfig {
  api_key: string;
  proxy_port: number;
  web_port: number;
  auto_start: boolean;
  dark_mode: boolean;
  model_mapping: Record<string, string>;
}

export interface AppState {
  proxyStatus: ProxyStatus | null;
  logs: LogEntry[];
  config: ProxyConfig | null;
  loading: boolean;
  starting: boolean;
  error: string | null;
  keyValid: boolean | null;
  checkingKey: boolean;
}
