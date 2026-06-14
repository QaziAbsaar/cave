import { useState } from "react";
import { FileCode, FileText, Shield } from "lucide-react";

interface ArtifactViewerProps {
  artifacts?: {
    db_schema_ddl?: string;
    backend_code?: Record<string, string>;
    frontend_code?: Record<string, string>;
    test_report?: Record<string, unknown>;
  };
}

type Tab = "db" | "backend" | "frontend" | "security";

export function ArtifactViewer({ artifacts }: ArtifactViewerProps) {
  const [activeTab, setActiveTab] = useState<Tab>("backend");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);

  if (!artifacts) {
    return (
      <div className="card">
        <p className="text-cave-400 text-sm italic">
          No artifacts generated yet. Run a project to see code output.
        </p>
      </div>
    );
  }

  const tabs: { id: Tab; label: string; icon: typeof FileCode; count: number }[] = [
    { id: "db", label: "Database", icon: FileText, count: artifacts.db_schema_ddl ? 1 : 0 },
    { id: "backend", label: "Backend", icon: FileCode, count: Object.keys(artifacts.backend_code || {}).length },
    { id: "frontend", label: "Frontend", icon: FileCode, count: Object.keys(artifacts.frontend_code || {}).length },
    { id: "security", label: "Security", icon: Shield, count: artifacts.test_report ? 1 : 0 },
  ];

  const getFileList = (): string[] => {
    switch (activeTab) {
      case "db":
        return ["schema.sql"];
      case "backend":
        return Object.keys(artifacts.backend_code || {});
      case "frontend":
        return Object.keys(artifacts.frontend_code || {});
      case "security":
        return ["test_report.json"];
      default:
        return [];
    }
  };

  const getCode = (filename: string): string => {
    switch (activeTab) {
      case "db":
        return artifacts.db_schema_ddl || "-- No schema generated";
      case "backend":
        return (artifacts.backend_code || {})[filename] || "// No code";
      case "frontend":
        return (artifacts.frontend_code || {})[filename] || "// No code";
      case "security":
        return JSON.stringify(artifacts.test_report || {}, null, 2);
      default:
        return "";
    }
  };

  const files = getFileList();
  const selected = selectedFile || files[0] || "";

  return (
    <div className="card">
      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-cave-700/50 pb-2">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id);
                setSelectedFile(null);
              }}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer ${
                activeTab === tab.id
                  ? "bg-accent-500/10 text-accent-400"
                  : "text-cave-400 hover:text-cave-100 hover:bg-cave-800"
              }`}
            >
              <Icon size={16} />
              {tab.label}
              {tab.count > 0 && (
                <span className="bg-cave-800 text-cave-400 text-xs px-1.5 py-0.5 rounded-full">
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex gap-4">
        {/* File list */}
        <div className="w-40 flex-shrink-0 space-y-0.5">
          {files.map((f) => (
            <button
              key={f}
              onClick={() => setSelectedFile(f)}
              className={`w-full text-left px-3 py-1.5 rounded-md text-xs transition-all duration-200 cursor-pointer ${
                selected === f
                  ? "bg-accent-500/10 text-accent-400"
                  : "text-cave-400 hover:text-cave-100 hover:bg-cave-800"
              }`}
            >
              <FileCode size={12} className="inline mr-1.5" />
              {f.split("/").pop()}
            </button>
          ))}
        </div>

        {/* Code viewer */}
        <div className="flex-1">
          <pre className="bg-cave-950 rounded-lg p-4 overflow-x-auto text-xs leading-relaxed max-h-[400px] overflow-y-auto">
            <code>{getCode(selected)}</code>
          </pre>
        </div>
      </div>
    </div>
  );
}
