import { StatusBadge } from "./StatusBadge";
import { Database, Server, Code2, Shield, LucideIcon } from "lucide-react";

type AgentName = "database_agent" | "backend_agent" | "frontend_agent" | "security_agent";

interface AgentStatusCardProps {
  name: AgentName;
  status: string;
  step?: number;
  active?: boolean;
}

const AGENT_META: Record<AgentName, { label: string; icon: LucideIcon; description: string }> = {
  database_agent: {
    label: "Database Agent",
    icon: Database,
    description: "Schema design & DDL generation",
  },
  backend_agent: {
    label: "Backend Agent",
    icon: Server,
    description: "FastAPI code generation",
  },
  frontend_agent: {
    label: "Frontend Agent",
    icon: Code2,
    description: "React + Tailwind UI",
  },
  security_agent: {
    label: "Security Agent",
    icon: Shield,
    description: "SAST & QA review",
  },
};

export function AgentStatusCard({ name, status, active = false }: AgentStatusCardProps) {
  const meta = AGENT_META[name];
  const Icon = meta.icon;

  return (
    <div
      className={`card flex items-start gap-4 ${
        active ? "ring-1 ring-accent-500/50" : ""
      }`}
    >
      <div
        className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
          active ? "bg-accent-500/10 text-accent-400" : "bg-cave-800 text-cave-400"
        }`}
      >
        <Icon size={20} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-semibold text-cave-50 text-sm">{meta.label}</h3>
          <StatusBadge status={status as any} />
        </div>
        <p className="text-xs text-cave-400">{meta.description}</p>
      </div>
    </div>
  );
}
