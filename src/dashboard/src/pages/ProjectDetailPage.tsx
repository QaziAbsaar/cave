import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Play, Pause } from "lucide-react";
import { PipelineDAG } from "../components/PipelineDAG";
import { AgentStatusCard } from "../components/AgentStatusCard";
import { EventStream } from "../components/EventStream";
import { ArtifactViewer } from "../components/ArtifactViewer";

type AgentName = "database_agent" | "backend_agent" | "frontend_agent" | "security_agent";

interface ProjectDetail {
  project_id: string;
  status: string;
  current_agent?: string;
}

const AGENTS: AgentName[] = [
  "database_agent",
  "backend_agent",
  "frontend_agent",
  "security_agent",
];

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!projectId) return;

    const fetchProject = async () => {
      try {
        const res = await fetch(`/api/v1/projects/${projectId}`);
        if (res.ok) {
          const data = await res.json();
          setProject(data);
        }
      } catch (err) {
        console.error("Failed to load project:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchProject();
  }, [projectId]);

  // Simulate real-time status updates via WebSocket
  useEffect(() => {
    if (!projectId) return;

    // Mock: update agent statuses progressively
    const timers: ReturnType<typeof setTimeout>[] = [];
    AGENTS.forEach((agent, idx) => {
      const t = setTimeout(() => {
        setAgentStatuses((prev) => ({ ...prev, [agent]: "running" }));
        // Mark previous as success
        if (idx > 0) {
          setAgentStatuses((prev) => ({ ...prev, [AGENTS[idx - 1]]: "success" }));
        }
      }, (idx + 1) * 5000);
      timers.push(t);
    });

    // Final: mark last as success
    const finalTimer = setTimeout(() => {
      setAgentStatuses((prev) => ({ ...prev, security_agent: "success" }));
      setProject((prev) => (prev ? { ...prev, status: "success" } : prev));
    }, AGENTS.length * 5000 + 1000);
    timers.push(finalTimer);

    return () => timers.forEach(clearTimeout);
  }, [projectId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="text-center py-16">
        <h2 className="text-xl font-semibold text-cave-300 mb-2">Project Not Found</h2>
        <p className="text-sm text-cave-500 mb-4">The project you're looking for doesn't exist.</p>
        <button onClick={() => navigate("/")} className="btn-secondary text-sm">
          Back to Dashboard
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate("/")} className="btn-ghost cursor-pointer">
          <ArrowLeft size={20} />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-cave-50">
            Project {project.project_id.slice(0, 8)}
          </h1>
          <p className="text-sm text-cave-400 mt-0.5 capitalize">
            Status: {project.status}
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary flex items-center gap-2 text-sm">
            <Pause size={14} />
            Pause
          </button>
          <button className="btn-primary flex items-center gap-2 text-sm">
            <Play size={14} />
            Resume
          </button>
        </div>
      </div>

      {/* Pipeline DAG */}
      <PipelineDAG statuses={agentStatuses as Record<string, any>} activeAgent={project.current_agent} />

      {/* Agent cards */}
      <div className="grid grid-cols-2 gap-4">
        {AGENTS.map((agent) => (
          <AgentStatusCard
            key={agent}
            name={agent}
            status={agentStatuses[agent] || "pending"}
            active={agent === project.current_agent}
          />
        ))}
      </div>

      {/* Event stream + Artifacts */}
      <div className="grid grid-cols-2 gap-4">
        <EventStream projectId={projectId!} />
        <ArtifactViewer />
      </div>
    </div>
  );
}
