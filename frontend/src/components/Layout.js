import { useState, useEffect, useRef, useCallback } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Package, Truck, Users, BarChart3, ClipboardList, Settings,
  LogOut, Sun, Moon, Menu, X, Plus, UserCircle, Home, Search,
  FileText, TrendingUp, Bell, ShoppingBag, Calculator, MapPinCheck, Megaphone,
  ChevronDown, Layers,
} from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";
import { AlertListener } from "@/components/AlertListener";

const NAV_ITEMS = {
  telecaller: [
    { label: "Dashboard", icon: Home, path: "/" },
    { label: "All Orders", icon: ClipboardList, path: "/all-orders" },
    { label: "Create Order", icon: Plus, path: "/create-order" },
    { label: "Customers", icon: Users, path: "/customers" },
    { label: "Proforma Invoice", icon: FileText, path: "/proforma" },
    { label: "Anjani", icon: MapPinCheck, path: "/anjani" },
    { label: "DTDC", icon: Calculator, path: "/dtdc" },
  ],
  packaging: [
    { label: "Dashboard", icon: Home, path: "/" },
    { label: "All Orders", icon: ClipboardList, path: "/all-orders" },
    { label: "Packaging Queue", icon: Package, path: "/packaging" },
    { label: "Amazon Orders", icon: ShoppingBag, path: "/amazon-orders" },
    { label: "Amazon Packing", icon: ShoppingBag, path: "/amazon-packing" },
    { label: "Amazon Dispatch", icon: Truck, path: "/amazon-dispatch" },
    { label: "Dispatch", icon: Truck, path: "/dispatch" },
    { label: "Anjani", icon: MapPinCheck, path: "/anjani" },
    { label: "DTDC", icon: Calculator, path: "/dtdc" },
  ],
  dispatch: [
    { label: "Dashboard", icon: Home, path: "/" },
    { label: "All Orders", icon: ClipboardList, path: "/all-orders" },
    { label: "Dispatch Queue", icon: Truck, path: "/dispatch" },
    { label: "Amazon Dispatch", icon: ShoppingBag, path: "/amazon-dispatch" },
    { label: "Anjani", icon: MapPinCheck, path: "/anjani" },
    { label: "DTDC", icon: Calculator, path: "/dtdc" },
  ],
  admin: [
    { label: "Dashboard", icon: Home, path: "/" },
    { label: "All Orders", icon: ClipboardList, path: "/all-orders" },
    { label: "Create Order", icon: Plus, path: "/create-order" },
    { label: "Customers", icon: Users, path: "/customers" },
    { label: "Proforma Invoice", icon: FileText, path: "/proforma" },
    { label: "Packaging", icon: Package, path: "/packaging" },
    { label: "Dispatch", icon: Truck, path: "/dispatch" },
    {
      label: "Amazon", icon: ShoppingBag, group: true,
      children: [
        { label: "Amazon Orders", icon: ShoppingBag, path: "/amazon-orders" },
        { label: "Amazon Packing", icon: Package, path: "/amazon-packing" },
        { label: "Amazon Dispatch", icon: Truck, path: "/amazon-dispatch" },
      ],
    },
    { label: "Accounts", icon: BarChart3, path: "/accounts" },
    { label: "Item Analytics", icon: TrendingUp, path: "/item-analytics" },
    { label: "Users", icon: Settings, path: "/users" },
    { label: "Alerts", icon: Megaphone, path: "/admin-alerts" },
    { label: "Anjani", icon: MapPinCheck, path: "/anjani" },
    { label: "DTDC", icon: Calculator, path: "/dtdc" },
  ],
  accounts: [
    { label: "Dashboard", icon: Home, path: "/" },
    { label: "All Orders", icon: ClipboardList, path: "/all-orders" },
    { label: "Customers", icon: Users, path: "/customers" },
    { label: "Anjani", icon: MapPinCheck, path: "/anjani" },
    { label: "DTDC", icon: Calculator, path: "/dtdc" },
  ],
};

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const { setTheme, resolvedTheme } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifCount, setNotifCount] = useState(0);
  const [expandedGroup, setExpandedGroup] = useState(null);
  const [hoverGroup, setHoverGroup] = useState(null);
  const hoverTimeout = useRef(null);
  const lastCheckRef = useRef(localStorage.getItem("citspray_last_notif_check") || new Date(Date.now() - 86400000).toISOString());

  const navItems = NAV_ITEMS[user?.role] || [];

  // Auto-expand group if a child route is active
  useEffect(() => {
    for (const item of navItems) {
      if (item.group && item.children?.some(c => c.path === location.pathname)) {
        setExpandedGroup(item.label);
        break;
      }
    }
  }, [location.pathname]);

  const isMobile = () => typeof window !== "undefined" && window.innerWidth < 1024;

  const handleGroupInteraction = (label) => {
    setExpandedGroup(prev => prev === label ? null : label);
  };

  const handleGroupMouseEnter = (label) => {
    if (isMobile()) return;
    clearTimeout(hoverTimeout.current);
    setHoverGroup(label);
  };

  const handleGroupMouseLeave = () => {
    if (isMobile()) return;
    hoverTimeout.current = setTimeout(() => setHoverGroup(null), 200);
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const playNotifSound = useCallback(() => {
    try {
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.type = "sine"; osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.setValueAtTime(660, ctx.currentTime + 0.1);
      gain.gain.setValueAtTime(0.4, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
      osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.5);
    } catch { /* audio context not available */ }
  }, []);

  // Load persistent notification count
  const refreshNotifCount = useCallback(async () => {
    if (user?.role !== "telecaller") return;
    try {
      const res = await api.get("/notifications");
      setNotifCount(res.data?.length || 0);
    } catch {}
  }, [user?.role]);

  useEffect(() => {
    refreshNotifCount();
  }, [refreshNotifCount]);

  useEffect(() => {
    if (user?.role !== "telecaller") return;
    const poll = async () => {
      try {
        const since = lastCheckRef.current;
        const res = await api.get(`/orders/my-notifications?since=${encodeURIComponent(since)}`);
        const notifs = res.data || [];
        if (notifs.length > 0) {
          const newSince = new Date().toISOString();
          lastCheckRef.current = newSince;
          localStorage.setItem("citspray_last_notif_check", newSince);
          // Persist each notification to DB
          for (const n of notifs) {
            try {
              await api.post("/notifications", {
                order_id: n.id,
                order_number: n.order_number,
                customer_name: n.customer_name,
                type: n.status,
                shipping_method: n.shipping_method,
              });
            } catch {}
          }
          refreshNotifCount();
          notifs.forEach(n => {
            const msg = n.status === "packed"
              ? `Order ${n.order_number} is Packed and ready!`
              : `Order ${n.order_number} has been Dispatched!`;
            toast.success(msg, { duration: 8000, description: n.customer_name });
          });
          playNotifSound();
        }
      } catch { /* silent */ }
    };
    poll(); // immediate check on mount
    const interval = setInterval(poll, 30000);
    return () => clearInterval(interval);
  }, [user?.role, playNotifSound, refreshNotifCount]);

  return (
    <div className="flex h-screen overflow-hidden" data-testid="app-layout">
      {/* Sidebar Overlay (mobile) */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 w-64 bg-card border-r border-border flex flex-col transition-transform duration-300 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        }`}
        data-testid="sidebar"
      >
        {/* Brand */}
        <div className="h-16 flex items-center px-6 border-b border-border">
          <Link to="/" className="flex items-center gap-2" data-testid="brand-logo">
            <img src="/logo.png" alt="CitSpray" className="h-8 w-8 rounded-lg object-contain" />
            <span className="text-lg font-bold tracking-tight">CitSpray</span>
          </Link>
          <Button
            variant="ghost" size="icon"
            className="ml-auto lg:hidden"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="w-5 h-5" />
          </Button>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto" data-testid="sidebar-nav">
          {navItems.map((item) => {
            if (item.group) {
              const Icon = item.icon;
              const isChildActive = item.children?.some(c => c.path === location.pathname);
              const isOpen = expandedGroup === item.label || hoverGroup === item.label;
              return (
                <div
                  key={item.label}
                  onMouseEnter={() => handleGroupMouseEnter(item.label)}
                  onMouseLeave={handleGroupMouseLeave}
                  data-testid={`nav-group-${item.label.toLowerCase()}`}
                >
                  <button
                    onClick={() => handleGroupInteraction(item.label)}
                    className={`sidebar-nav-item w-full justify-between ${isChildActive ? "active" : "text-muted-foreground"}`}
                    data-testid={`nav-group-toggle-${item.label.toLowerCase()}`}
                  >
                    <span className="flex items-center gap-3">
                      <Icon className="w-4 h-4" />
                      {item.label}
                    </span>
                    <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
                  </button>
                  <div
                    className={`overflow-hidden transition-all duration-200 ${isOpen ? "max-h-60 opacity-100" : "max-h-0 opacity-0"}`}
                  >
                    <div className="pl-4 mt-0.5 space-y-0.5 border-l-2 border-border ml-5">
                      {item.children.map(child => {
                        const ChildIcon = child.icon;
                        const childActive = location.pathname === child.path;
                        return (
                          <Link
                            key={child.path}
                            to={child.path}
                            data-testid={`nav-${child.label.toLowerCase().replace(/\s/g, "-")}`}
                            className={`sidebar-nav-item text-sm py-1.5 ${childActive ? "active" : "text-muted-foreground"}`}
                            onClick={() => setSidebarOpen(false)}
                          >
                            <ChildIcon className="w-3.5 h-3.5" />
                            {child.label}
                          </Link>
                        );
                      })}
                    </div>
                  </div>
                </div>
              );
            }
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                data-testid={`nav-${item.label.toLowerCase().replace(/\s/g, "-")}`}
                className={`sidebar-nav-item ${isActive ? "active" : "text-muted-foreground"}`}
                onClick={() => setSidebarOpen(false)}
              >
                <Icon className="w-4 h-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* User info */}
        <div className="p-4 border-t border-border">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center">
              <UserCircle className="w-5 h-5 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{user?.name}</p>
              <p className="text-xs text-muted-foreground capitalize">{user?.role}</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-16 glass-header flex items-center px-4 lg:px-6 gap-4 z-30 sticky top-0" data-testid="app-header">
          <Button
            variant="ghost" size="icon"
            className="lg:hidden"
            onClick={() => setSidebarOpen(true)}
            data-testid="sidebar-toggle"
          >
            <Menu className="w-5 h-5" />
          </Button>

          <div className="flex-1" />

          {user?.role === "telecaller" && notifCount > 0 && (
            <button
              className="relative p-2 rounded-lg hover:bg-accent transition-colors"
              onClick={() => navigate("/")}
              data-testid="notification-bell"
            >
              <Bell className="w-5 h-5" />
              <span className="absolute top-1 right-1 w-4 h-4 bg-red-500 text-white text-xs rounded-full flex items-center justify-center font-bold">
                {notifCount > 9 ? "9+" : notifCount}
              </span>
            </button>
          )}

          <Button
            variant="ghost" size="icon"
            onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
            data-testid="theme-toggle"
          >
            {resolvedTheme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" data-testid="user-menu-trigger">
                <UserCircle className="w-5 h-5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>{user?.name}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleLogout} data-testid="logout-btn">
                <LogOut className="w-4 h-4 mr-2" />
                Logout
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto p-4 lg:p-6" data-testid="main-content">
          {children}
        </main>
      </div>
      <AlertListener />
    </div>
  );
}
