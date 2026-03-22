import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { UserPlus, Edit, Trash2, Shield, Phone, Package, Truck } from "lucide-react";

const ROLE_ICONS = {
  admin: Shield,
  telecaller: Phone,
  packaging: Package,
  dispatch: Truck,
};

const ROLE_COLORS = {
  admin: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  telecaller: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  packaging: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400",
  dispatch: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
};

export default function UserManagement() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [form, setForm] = useState({ username: "", password: "", name: "", role: "telecaller" });

  useEffect(() => { loadUsers(); }, []);

  const loadUsers = async () => {
    try {
      const res = await api.get("/users");
      setUsers(res.data);
    } catch { } finally { setLoading(false); }
  };

  const openNew = () => {
    setEditingUser(null);
    setForm({ username: "", password: "", name: "", role: "telecaller" });
    setShowDialog(true);
  };

  const openEdit = (u) => {
    setEditingUser(u);
    setForm({ username: u.username, password: "", name: u.name, role: u.role });
    setShowDialog(true);
  };

  const handleSave = async () => {
    if (!form.name || !form.username) return toast.error("Name and username are required");
    try {
      if (editingUser) {
        const payload = { name: form.name, role: form.role };
        if (form.password) payload.password = form.password;
        await api.put(`/users/${editingUser.id}`, payload);
        toast.success("User updated");
      } else {
        if (!form.password) return toast.error("Password is required");
        await api.post("/users", form);
        toast.success("User created");
      }
      setShowDialog(false);
      loadUsers();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };

  const toggleActive = async (u) => {
    try {
      await api.put(`/users/${u.id}`, { active: !u.active });
      toast.success(`User ${u.active ? "deactivated" : "activated"}`);
      loadUsers();
    } catch { toast.error("Failed"); }
  };

  const deleteUser = async (u) => {
    if (!window.confirm(`Delete user "${u.name}"?`)) return;
    try {
      await api.delete(`/users/${u.id}`);
      toast.success("User deleted");
      loadUsers();
    } catch { toast.error("Failed"); }
  };

  return (
    <div className="space-y-6" data-testid="user-management">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">User Management</h1>
        <Button onClick={openNew} className="rounded-lg" data-testid="add-user-btn">
          <UserPlus className="w-4 h-4 mr-2" /> Add User
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6">
          {loading ? (
            <p className="text-center py-8 text-muted-foreground">Loading...</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs uppercase tracking-wider">Name</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Username</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Role</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Status</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Created</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id} data-testid={`user-row-${u.username}`}>
                    <TableCell className="font-medium">{u.name}</TableCell>
                    <TableCell className="font-mono text-sm">{u.username}</TableCell>
                    <TableCell>
                      <Badge variant="secondary" className={`${ROLE_COLORS[u.role]} text-xs uppercase`}>
                        {u.role}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Switch
                        checked={u.active !== false}
                        onCheckedChange={() => toggleActive(u)}
                        data-testid={`toggle-active-${u.username}`}
                      />
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {u.created_at ? new Date(u.created_at).toLocaleDateString("en-IN") : "-"}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" onClick={() => openEdit(u)} data-testid={`edit-user-${u.username}`}>
                          <Edit className="w-4 h-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingUser ? "Edit User" : "Create User"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Full Name *</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="user-name-input" />
            </div>
            <div>
              <Label>Username *</Label>
              <Input
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                disabled={!!editingUser}
                data-testid="user-username-input"
              />
            </div>
            <div>
              <Label>{editingUser ? "New Password (leave blank to keep)" : "Password *"}</Label>
              <Input
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                data-testid="user-password-input"
              />
            </div>
            <div>
              <Label>Role</Label>
              <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                <SelectTrigger data-testid="user-role-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="telecaller">Telecaller</SelectItem>
                  <SelectItem value="packaging">Packaging</SelectItem>
                  <SelectItem value="dispatch">Dispatch</SelectItem>
                  <SelectItem value="accounts">Accounts</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDialog(false)}>Cancel</Button>
            <Button onClick={handleSave} data-testid="save-user-btn">{editingUser ? "Update" : "Create"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
