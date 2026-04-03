import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import Layout from "@/components/Layout";
import LoginPage from "@/pages/LoginPage";
import TelecallerDashboard from "@/pages/telecaller/TelecallerDashboard";
import CreateOrder from "@/pages/telecaller/CreateOrder";
import Customers from "@/pages/telecaller/Customers";
import PackagingDashboard from "@/pages/packaging/PackagingDashboard";
import DispatchDashboard from "@/pages/dispatch/DispatchDashboard";
import AdminDashboard from "@/pages/admin/AdminDashboard";
import UserManagement from "@/pages/admin/UserManagement";
import AccountsDashboard from "@/pages/accounts/AccountsDashboard";
import OrderDetail from "@/pages/OrderDetail";
import EditOrder from "@/pages/EditOrder";
import PIBuilder from "@/pages/PIBuilder";
import ItemAnalytics from "@/pages/ItemAnalytics";
import AllOrders from "@/pages/AllOrders";
import AmazonOrders from "@/pages/amazon/AmazonOrders";
import AmazonOrderDetail from "@/pages/amazon/AmazonOrderDetail";
import AmazonPacking from "@/pages/amazon/AmazonPacking";
import AmazonDispatch from "@/pages/amazon/AmazonDispatch";
import AdminAccounts from "@/pages/admin/AdminAccounts";
import DTDCCalculator from "@/pages/DTDCCalculator";
import AnjaniChecker from "@/pages/AnjaniChecker";

function ProtectedRoute({ children, allowedRoles }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex items-center justify-center h-screen text-muted-foreground">Loading...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (allowedRoles && !allowedRoles.includes(user.role)) return <Navigate to="/" replace />;
  return <Layout>{children}</Layout>;
}

function DashboardRouter() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  switch (user.role) {
    case "admin": return <AdminDashboard />;
    case "telecaller": return <TelecallerDashboard />;
    case "packaging": return <PackagingDashboard />;
    case "dispatch": return <DispatchDashboard />;
    case "accounts": return <AccountsDashboard />;
    default: return <TelecallerDashboard />;
  }
}

function AppRoutes() {
  const { user, loading } = useAuth();

  if (loading) return <div className="flex items-center justify-center h-screen text-muted-foreground">Loading...</div>;

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route path="/" element={<ProtectedRoute><DashboardRouter /></ProtectedRoute>} />
      <Route path="/create-order" element={<ProtectedRoute allowedRoles={["telecaller", "admin"]}><CreateOrder /></ProtectedRoute>} />
      <Route path="/customers" element={<ProtectedRoute allowedRoles={["telecaller", "admin", "accounts"]}><Customers /></ProtectedRoute>} />
      <Route path="/packaging" element={<ProtectedRoute allowedRoles={["packaging", "admin"]}><PackagingDashboard /></ProtectedRoute>} />
      <Route path="/dispatch" element={<ProtectedRoute allowedRoles={["dispatch", "packaging", "admin"]}><DispatchDashboard /></ProtectedRoute>} />
      <Route path="/all-orders" element={<ProtectedRoute><AllOrders /></ProtectedRoute>} />
      <Route path="/orders/:orderId/edit" element={<ProtectedRoute><EditOrder /></ProtectedRoute>} />
      <Route path="/orders/:orderId" element={<ProtectedRoute><OrderDetail /></ProtectedRoute>} />
      <Route path="/pi/:piId/convert" element={<ProtectedRoute allowedRoles={["telecaller", "admin"]}><CreateOrder /></ProtectedRoute>} />
      <Route path="/proforma" element={<ProtectedRoute allowedRoles={["telecaller", "admin"]}><PIBuilder /></ProtectedRoute>} />
      <Route path="/item-analytics" element={<ProtectedRoute allowedRoles={["admin"]}><ItemAnalytics /></ProtectedRoute>} />
      <Route path="/users" element={<ProtectedRoute allowedRoles={["admin"]}><UserManagement /></ProtectedRoute>} />
      <Route path="/amazon-orders" element={<ProtectedRoute allowedRoles={["admin", "packaging"]}><AmazonOrders /></ProtectedRoute>} />
      <Route path="/amazon-orders/:id" element={<ProtectedRoute allowedRoles={["admin", "packaging", "dispatch"]}><AmazonOrderDetail /></ProtectedRoute>} />
      <Route path="/amazon-packing" element={<ProtectedRoute allowedRoles={["admin", "packaging"]}><AmazonPacking /></ProtectedRoute>} />
      <Route path="/amazon-dispatch" element={<ProtectedRoute allowedRoles={["admin", "packaging", "dispatch"]}><AmazonDispatch /></ProtectedRoute>} />
      <Route path="/accounts" element={<ProtectedRoute allowedRoles={["admin"]}><AdminAccounts /></ProtectedRoute>} />
      <Route path="/dtdc" element={<ProtectedRoute><DTDCCalculator /></ProtectedRoute>} />
      <Route path="/anjani" element={<ProtectedRoute><AnjaniChecker /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <ThemeProvider defaultTheme="light">
      <AuthProvider>
        <BrowserRouter>
          <AppRoutes />
          <Toaster position="top-right" richColors />
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
