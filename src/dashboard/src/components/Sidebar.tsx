import { useNavigate, useLocation } from "react-router-dom";
import { LayoutDashboard, Box, Settings, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

const NAV_ITEMS = [
  { label: "Dashboard", icon: LayoutDashboard, path: "/" },
  { label: "Projects", icon: Box, path: "/" },
  { label: "Settings", icon: Settings, path: "/" },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <aside
      className={`bg-cave-900 border-r border-cave-700/50 flex flex-col transition-all duration-300 ${
        collapsed ? "w-16" : "w-64"
      }`}
    >
      {/* Logo */}
      <div className="h-16 flex items-center gap-3 px-4 border-b border-cave-700/50">
        <div className="w-8 h-8 rounded-lg bg-accent-500 flex items-center justify-center flex-shrink-0">
          <span className="text-white font-bold text-sm">C</span>
        </div>
        {!collapsed && (
          <span className="font-semibold text-cave-50 text-lg">Project Cave</span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-2 space-y-1">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = location.pathname === item.path;
          return (
            <button
              key={item.label}
              onClick={() => navigate(item.path)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 cursor-pointer ${
                active
                  ? "bg-accent-500/10 text-accent-400"
                  : "text-cave-400 hover:text-cave-100 hover:bg-cave-800"
              }`}
            >
              <Icon size={20} className="flex-shrink-0" />
              {!collapsed && <span className="text-sm font-medium">{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {/* Collapse toggle */}
      <div className="p-2 border-t border-cave-700/50">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-center p-2 rounded-lg text-cave-400 hover:text-cave-100 hover:bg-cave-800 transition-all duration-200 cursor-pointer"
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>
    </aside>
  );
}
