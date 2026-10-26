import type { WsEvent } from "./types";

interface Handlers {
  onEvent: (e: WsEvent) => void;
  onOpen?: () => void;
  onClose?: () => void;
}

/**
 * Subscribe to a case's live feed. Auto-reconnects with backoff. Returns a disposer.
 * Auth is the access token in the query string (cookies aren't sent cross-origin to the WS host).
 */
/**
 * Resolve the WS endpoint at runtime so it works from any origin the app is served on
 * (localhost, a LAN IP, or a tailnet/MagicDNS name). The HOST comes from the live page;
 * only the API port — and the scheme upgrade to wss on https — is taken from the
 * build-time NEXT_PUBLIC_WS_URL. One build thus serves every network the host is reachable on.
 */
function resolveWsBase(): string {
  const configured = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
  if (typeof window === "undefined") return configured;
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  let port = "8000";
  try {
    port = new URL(configured).port || (proto === "wss" ? "443" : "80");
  } catch {
    /* keep default */
  }
  const hostport = port ? `${window.location.hostname}:${port}` : window.location.hostname;
  return `${proto}://${hostport}`;
}

export function connectCaseFeed(caseId: string, token: string, handlers: Handlers): () => void {
  const base = resolveWsBase();
  const url = `${base}/api/v1/ws/cases/${caseId}?token=${encodeURIComponent(token)}`;
  let ws: WebSocket | null = null;
  let closed = false;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const open = () => {
    if (closed) return;
    ws = new WebSocket(url);
    ws.onopen = () => {
      attempt = 0;
      handlers.onOpen?.();
    };
    ws.onmessage = (ev) => {
      try {
        handlers.onEvent(JSON.parse(ev.data) as WsEvent);
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onclose = () => {
      handlers.onClose?.();
      if (!closed) {
        attempt += 1;
        timer = setTimeout(open, Math.min(1000 * attempt, 8000));
      }
    };
    ws.onerror = () => ws?.close();
  };

  open();

  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    ws?.close();
  };
}
