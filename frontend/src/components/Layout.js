import { useState, useEffect, useRef } from "react";
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
  FileText, TrendingUp, Bell,
} from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";

const NAV_ITEMS = {
  telecaller: [
    { label: "Dashboard", icon: Home, path: "/" },
    { label: "All Orders", icon: ClipboardList, path: "/all-orders" },
    { label: "Create Order", icon: Plus, path: "/create-order" },
    { label: "Customers", icon: Users, path: "/customers" },
    { label: "Proforma Invoice", icon: FileText, path: "/proforma" },
  ],
  packaging: [
    { label: "Dashboard", icon: Home, path: "/" },
    { label: "All Orders", icon: ClipboardList, path: "/all-orders" },
    { label: "Packaging Queue", icon: Package, path: "/packaging" },
    { label: "Dispatch", icon: Truck, path: "/dispatch" },
  ],
  dispatch: [
    { label: "Dashboard", icon: Home, path: "/" },
    { label: "All Orders", icon: ClipboardList, path: "/all-orders" },
    { label: "Dispatch Queue", icon: Truck, path: "/dispatch" },
  ],
  admin: [
    { label: "Dashboard", icon: Home, path: "/" },
    { label: "All Orders", icon: ClipboardList, path: "/all-orders" },
    { label: "Create Order", icon: Plus, path: "/create-order" },
    { label: "Customers", icon: Users, path: "/customers" },
    { label: "Proforma Invoice", icon: FileText, path: "/proforma" },
    { label: "Packaging", icon: Package, path: "/packaging" },
    { label: "Dispatch", icon: Truck, path: "/dispatch" },
    { label: "Item Analytics", icon: TrendingUp, path: "/item-analytics" },
    { label: "Users", icon: Settings, path: "/users" },
  ],
  accounts: [
    { label: "Dashboard", icon: Home, path: "/" },
    { label: "All Orders", icon: ClipboardList, path: "/all-orders" },
    { label: "Customers", icon: Users, path: "/customers" },
  ],
  field_manager: [
    { label: "Dashboard", icon: Home, path: "/" },
    { label: "All Orders", icon: ClipboardList, path: "/all-orders" },
    { label: "Create Order", icon: Plus, path: "/create-order" },
    { label: "Customers", icon: Users, path: "/customers" },
    { label: "Proforma Invoice", icon: FileText, path: "/proforma" },
  ],
};

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const { setTheme, resolvedTheme } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifCount, setNotifCount] = useState(0);
  const lastCheckRef = useRef(localStorage.getItem("citspray_last_notif_check") || new Date(Date.now() - 86400000).toISOString());

  const navItems = NAV_ITEMS[user?.role] || [];

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const playNotifSound = () => {
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
  };

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
          setNotifCount(c => c + notifs.length);
          notifs.forEach(n => {
            const msg = n.status === "packed"
              ? `Order ${n.order_number} is Packed and ready!`
              : `Order ${n.order_number} has been Dispatched!`;
            toast.success(msg, { duration: 6000, description: n.customer_name });
          });
          playNotifSound();
        }
      } catch { /* silent */ }
    };
    poll(); // immediate check on mount
    const interval = setInterval(poll, 30000);
    return () => clearInterval(interval);
  }, [user?.role]);

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
              onClick={() => setNotifCount(0)}
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
    </div>
  );
}
