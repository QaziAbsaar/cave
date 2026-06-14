import { createContext, useContext, useState, ReactNode } from "react";

interface ProjectContextType {
  activeProjectId: string | null;
  setActiveProjectId: (id: string | null) => void;
}

const ProjectContext = createContext<ProjectContextType>({
  activeProjectId: null,
  setActiveProjectId: () => {},
});

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);

  return (
    <ProjectContext.Provider value={{ activeProjectId, setActiveProjectId }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  return useContext(ProjectContext);
}
