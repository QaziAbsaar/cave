import { useState } from "react";
import { X } from "lucide-react";

interface NewProjectModalProps {
  onClose: () => void;
}

export function NewProjectModal({ onClose }: NewProjectModalProps) {
  const [prompt, setPrompt] = useState("");
  const [title, setTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    setSubmitting(true);

    try {
      const res = await fetch("/api/v1/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initial_prompt: prompt, title: title || undefined }),
      });
      const data = await res.json();
      if (res.ok) {
        window.location.href = `/projects/${data.project_id}`;
      }
    } catch (err) {
      console.error("Failed to create project:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Overlay */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* Modal */}
      <div className="relative bg-cave-900 rounded-2xl p-8 max-w-lg w-full mx-4 shadow-2xl border border-cave-700/50">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-cave-50">New Project</h2>
          <button
            onClick={onClose}
            className="btn-ghost p-1 cursor-pointer"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-cave-300 mb-1">
              Project Title <span className="text-cave-500">(optional)</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="My Awesome App"
              className="input"
              maxLength={200}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-cave-300 mb-1">
              Project Brief <span className="text-red-400">*</span>
            </label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe the application you want to build..."
              className="input min-h-[120px] resize-y"
              maxLength={2000}
              required
            />
            <p className="text-xs text-cave-500 mt-1">{prompt.length}/2000</p>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary text-sm">
              Cancel
            </button>
            <button
              type="submit"
              disabled={!prompt.trim() || submitting}
              className="btn-primary text-sm"
            >
              {submitting ? "Creating..." : "Create Project"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
