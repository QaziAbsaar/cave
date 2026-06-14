/// API client for Project Cave backend

const BASE = ""; // Uses Vite proxy → localhost:8000

interface CreateProjectResponse {
  project_id: string;
  ws_url: string;
  status: string;
}

interface ProjectStatusResponse {
  project_id: string;
  status: string;
  current_agent?: string;
  step_number?: number;
}

export async function createProject(
  initialPrompt: string,
  title?: string
): Promise<CreateProjectResponse> {
  const res = await fetch(`${BASE}/api/v1/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ initial_prompt: initialPrompt, title }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to create project");
  }

  return res.json();
}

export async function getProject(id: string): Promise<ProjectStatusResponse> {
  const res = await fetch(`${BASE}/api/v1/projects/${id}`);

  if (!res.ok) {
    if (res.status === 404) throw new Error("Project not found");
    throw new Error("Failed to fetch project");
  }

  return res.json();
}

export async function pauseProject(id: string): Promise<{ status: string }> {
  const res = await fetch(`${BASE}/api/v1/projects/${id}/pause`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to pause project");
  return res.json();
}

export async function resumeProject(id: string): Promise<{ status: string }> {
  const res = await fetch(`${BASE}/api/v1/projects/${id}/resume`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to resume project");
  return res.json();
}
