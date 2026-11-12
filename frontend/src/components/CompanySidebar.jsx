
import { useState } from "react";
import {
  Atom,
  LayoutDashboard,
  Clock3,
  FileText,
  Network,
  Users,
  BrainCircuit,
  Bot,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";

import "./CompanySidebar.css";

const navigationItems = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "timeline", label: "Product Timeline", icon: Clock3 },
  { id: "sources", label: "Sources", icon: FileText },
  { id: "graph", label: "Knowledge Graph", icon: Network },
  { id: "customers", label: "Customer Intelligence", icon: Users },
  { id: "proposals", label: "Proposal Analysis", icon: BrainCircuit },
  { id: "ai-assistant", label: "AI Assistant", icon: Bot },
];

export default function CompanySidebar({ onNavigate }) {
  const [collapsed, setCollapsed] = useState(false);
  const [activeItem, setActiveItem] = useState("overview");

  function handleNavigation(id) {
    setActiveItem(id);
    onNavigate?.(id);
  }

  return (
    <aside className={`nexus-sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="sidebar-brand">
        <div className="brand-icon">
          <Atom size={23} />
        </div>

        {!collapsed && <span>NEXUS</span>}
      </div>

      <div className="sidebar-section-label">
        {!collapsed && "WORKSPACE"}
      </div>

      <nav className="sidebar-navigation">
        {navigationItems.map((item) => {
          const Icon = item.icon;

          return (
            <button
              key={item.id}
              className={`sidebar-link ${
                activeItem === item.id ? "active" : ""
              }`}
              onClick={() => handleNavigation(item.id)}
              title={collapsed ? item.label : ""}
            >
              <Icon size={19} />
              {!collapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>

      <div className="sidebar-bottom">
        <button
          className="sidebar-collapse-button"
          onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <PanelLeftOpen size={19} />
          ) : (
            <PanelLeftClose size={19} />
          )}

          {!collapsed && <span>Collapse sidebar</span>}
        </button>
      </div>
    </aside>
  );
}
