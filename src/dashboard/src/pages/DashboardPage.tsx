import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Box, Clock, CheckCircle, AlertCircle } from "lucide-react";
import { StatusBadge } from "../components/StatusBadge";

interface ProjectSummary {
  project_id: string;
  status: string;
  current_agent?: string;
}

export function DashboardPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    // Fetch projects (mock for now — real API later)
    const timer = setTimeout(() => {
      setProjects([]);
      setLoading(false);
    }, 1000);
    return () => clearTimeout(timer);
  }, []);

  const stats = [
    { label: "Total Projects", value: projects.length, icon: Box, color: "text-blue-400" },
    { label: "Running", value: projects.filter((p) => p.status === "running").length, icon: Clock, color: "text-accent-400" },
    { label: "Completed", value: projects.filter((p) => p.status === "success").length, icon: CheckCircle, color: "text-emerald-400" },
    { label: "Failed", value: projects.filter((p) => p.status === "failed").length, icon: AlertCircle, color: "text-red-400" },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-cave-50">Projects</h1>
          <p className="text-sm text-cave-400 mt-1">
            Monitor and manage your AI-generated applications
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <div key={stat.label} className="card">
              <div className="flex items-center gap-3 mb-2">
                <Icon size={20} className={stat.color} />
                <span className="text-xs font-medium text-cave-400 uppercase tracking-wider">
                  {stat.label}
                </span>
              </div>
              <p className="text-2xl font-bold text-cave-50">{stat.value}</p>
            </div>
          );
        })}
      </div>

      {/* Project list */}
      <div className="card">
        <h2 className="text-sm font-semibold text-cave-300 uppercase tracking-wider mb-4">
          Recent Projects
        </h2>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 bg-cave-800 rounded-lg animate-pulse" />
            ))}
          </div>
        ) : projects.length === 0 ? (
          <div className="text-center py-12">
            <Box size={48} className="mx-auto text-cave-600 mb-4" />
            <h3 className="text-lg font-semibold text-cave-300 mb-2">No projects yet</h3>
            <p className="text-sm text-cave-500 mb-6">
              Create your first project to see it here
            </p>
            <button
              onClick={() => navigate("/")}
              className="btn-primary inline-flex items-center gap-2"
            >
              <Plus size={16} />
              New Project
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            {projects.map((project) => (
              <div
                key={project.project_id}
                onClick={() => navigate(`/projects/${project.project_id}`)}
                className="flex items-center justify-between p-4 rounded-lg bg-cave-800/50 hover:bg-cave-800 cursor-pointer transition-all duration-200"
              >
                <div>
                  <p className="font-medium text-cave-50 text-sm">
                    {project.project_id.slice(0, 8)}...
                  </p>
                  <p className="text-xs text-cave-500 mt-0.5">
                    Agent: {project.current_agent || "—"}
                  </p>
                </div>
                <StatusBadge status={project.status as any} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
