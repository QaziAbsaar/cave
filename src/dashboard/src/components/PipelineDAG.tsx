import {
  ReactFlow,
  Background,
  Node,
  Edge,
  Position,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Database, Server, Code2, Shield, LucideIcon } from "lucide-react";

export type AgentStatus = "pending" | "running" | "success" | "failed" | "intervention_needed";

interface PipelineDAGProps {
  statuses?: Record<string, AgentStatus>;
  activeAgent?: string;
}

interface AgentNode {
  id: string;
  label: string;
  icon: LucideIcon;
  status: AgentStatus;
}

const AGENTS: AgentNode[] = [
  { id: "database_agent", label: "Database", icon: Database, status: "pending" },
  { id: "backend_agent", label: "Backend", icon: Server, status: "pending" },
  { id: "frontend_agent", label: "Frontend", icon: Code2, status: "pending" },
  { id: "security_agent", label: "Security", icon: Shield, status: "pending" },
];

function AgentNodeComponent({ data }: { data: { label: string; icon: string; status: AgentStatus; active: boolean } }) {
  const statusColors: Record<string, string> = {
    pending: "border-cave-600 bg-cave-800 text-cave-400",
    running: "border-blue-500 bg-blue-500/10 text-blue-400 shadow-lg shadow-blue-500/10",
    success: "border-accent-500 bg-accent-500/10 text-accent-400",
    failed: "border-red-500 bg-red-500/10 text-red-400",
    intervention_needed: "border-amber-500 bg-amber-500/10 text-amber-400",
  };

  return (
    <div
      className={`px-6 py-4 rounded-xl border-2 flex items-center gap-3 transition-all duration-300 min-w-[160px] ${
        statusColors[data.status]
      } ${data.active ? "scale-105" : ""}`}
    >
      <span className="text-lg">{data.icon}</span>
      <span className="font-semibold text-sm">{data.label}</span>
    </div>
  );
}

export function PipelineDAG({ statuses = {}, activeAgent }: PipelineDAGProps) {
  const nodes: Node[] = AGENTS.map((agent, idx) => {
    const status = statuses[agent.id] || "pending";
    return {
      id: agent.id,
      type: "agentNode",
      position: { x: idx * 220 + 40, y: 60 },
      data: {
        label: agent.label,
        icon: getIconChar(agent.icon),
        status,
        active: agent.id === activeAgent,
      },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    };
  });

  const edges: Edge[] = AGENTS.slice(0, -1).map((agent, idx) => ({
    id: `${agent.id}->${AGENTS[idx + 1].id}`,
    source: agent.id,
    target: AGENTS[idx + 1].id,
    type: "smoothstep",
    animated: statuses[agent.id] === "success",
    style: { stroke: "#334155", strokeWidth: 2 },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#334155" },
  }));

  return (
    <div className="card h-[240px]">
      <h3 className="text-sm font-semibold text-cave-300 mb-3 uppercase tracking-wider">
        Agent Pipeline
      </h3>
      <div className="h-[180px]">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={{ agentNode: AgentNodeComponent }}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#1E293B" gap={20} />
        </ReactFlow>
      </div>
    </div>
  );
}

function getIconChar(icon: LucideIcon): string {
  const name = icon.name;
  if (name === "Database") return "🗄️";
  if (name === "Server") return "⚙️";
  if (name === "Code2") return "📄";
  if (name === "Shield") return "🛡️";
  return "⬡";
}
