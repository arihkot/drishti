import { X, CheckCircle, AlertCircle, Info } from "lucide-react";
import { useStore } from "../stores/useStore";

const config = {
  success: { bg: "bg-green-500", Icon: CheckCircle },
  error: { bg: "bg-red-500", Icon: AlertCircle },
  info: { bg: "bg-blue-500", Icon: Info },
} as const;

export default function Toast() {
  const toast = useStore((s) => s.toast);
  const clearToast = useStore((s) => s.clearToast);

  if (!toast) return null;

  const { bg, Icon } = config[toast.type];

  return (
    <div
      className={`fixed bottom-4 right-4 z-[9999] flex items-center gap-3 rounded-lg shadow-lg px-4 py-3 text-white animate-in fade-in slide-in-from-bottom-2 duration-300 ${bg}`}
    >
      <Icon size={18} className="shrink-0" />
      <span className="text-sm">{toast.message}</span>
      <button
        onClick={clearToast}
        className="ml-2 p-0.5 rounded hover:bg-white/20 transition-colors"
        aria-label="Dismiss"
      >
        <X size={16} />
      </button>
    </div>
  );
}
