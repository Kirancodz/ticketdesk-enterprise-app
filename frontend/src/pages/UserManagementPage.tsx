import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  Edit3,
  Eye,
  EyeOff,
  KeyRound,
  Mail,
  Phone,
  Plus,
  Search,
  Shield,
  Trash2,
  UserCheck,
  UserPlus,
  UserX,
  Users,
  X,
} from "lucide-react";
import { ApiError, apiRequest } from "../services/api";
import {
  DepartmentInfo,
  RoleType,
  SupportTeamInfo,
  UserDetail,
} from "../types";
import { RoleBadge } from "../components/ui/Badges";
import { formatDateTime } from "../utils/format";

interface PaginatedUsers {
  items: UserDetail[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export const UserManagementPage: React.FC = () => {
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [deptFilter, setDeptFilter] = useState("all");
  const [teamFilter, setTeamFilter] = useState("all");
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editUser, setEditUser] = useState<UserDetail | null>(null);
  const [teamModalOpen, setTeamModalOpen] = useState(false);
  // Admin-assisted password reset
  const [resetUser, setResetUser] = useState<UserDetail | null>(null);
  const [recoveryTicketId, setRecoveryTicketId] = useState("");
  const [verificationMethod, setVerificationMethod] = useState<
    "in_person_id" | "manager_callback" | "hr_confirmation"
  >("in_person_id");
  const [verificationConfirmed, setVerificationConfirmed] = useState(false);
  const [resetTemporaryPassword, setResetTemporaryPassword] = useState<string | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);

  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Create user form state
  const [newEmail, setNewEmail] = useState("");
  const [newName, setNewName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(true);
  const [newEmpId, setNewEmpId] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newRole, setNewRole] = useState<RoleType>("agent");
  const [newDeptId, setNewDeptId] = useState<string>("");
  const [newTeamId, setNewTeamId] = useState<string>("");
  const [newDepartmentName, setNewDepartmentName] = useState("");
  const [newSupportTeamName, setNewSupportTeamName] = useState("");

  // Edit user form state
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editEmpId, setEditEmpId] = useState("");
  const [editTitle, setEditTitle] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editRole, setEditRole] = useState<RoleType>("employee");
  const [editDeptId, setEditDeptId] = useState<string>("");
  const [editTeamId, setEditTeamId] = useState<string>("");
  const [editActive, setEditActive] = useState(true);

  // Create support team form state
  const [teamName, setTeamName] = useState("");
  const [teamCode, setTeamCode] = useState("");
  const [teamSpec, setTeamSpec] = useState("");

  const { data: departments } = useQuery<DepartmentInfo[]>({
    queryKey: ["departments"],
    queryFn: () => apiRequest<DepartmentInfo[]>("/users/departments"),
  });

  const { data: supportTeams } = useQuery<SupportTeamInfo[]>({
    queryKey: ["support-teams"],
    queryFn: () => apiRequest<SupportTeamInfo[]>("/users/support-teams"),
    staleTime: 0,
    refetchOnMount: "always",
  });

  const buildQuery = () => {
    const params = new URLSearchParams();
    params.set("page", "1");
    params.set("page_size", "50");
    if (search.trim()) params.set("search", search.trim());
    if (roleFilter !== "all") params.set("role", roleFilter);
    if (deptFilter !== "all") params.set("department_id", deptFilter);
    if (teamFilter !== "all") params.set("support_team_id", teamFilter);
    return params.toString();
  };

  const { data: usersData, isLoading } = useQuery<PaginatedUsers>({
    queryKey: ["admin-users", search, roleFilter, deptFilter, teamFilter],
    queryFn: () => apiRequest<PaginatedUsers>(`/users?${buildQuery()}`),
  });

  const showSuccess = (msg: string) => {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(null), 4000);
  };

  const createUserMutation = useMutation({
    mutationFn: () =>
      apiRequest<UserDetail>("/users", {
        method: "POST",
        body: JSON.stringify({
          email: newEmail,
          full_name: newName,
          password: newPassword,
          employee_id: newEmpId || null,
          job_title: newTitle || null,
          phone: newPhone || null,
          role: newRole,
            department_id: newDeptId && newDeptId !== "new" ? Number(newDeptId) : null,
            support_team_id: newTeamId && newTeamId !== "new" ? Number(newTeamId) : null,
            department_name: newDeptId === "new" ? newDepartmentName.trim() : undefined,
            support_team_name: newTeamId === "new" ? newSupportTeamName.trim() : undefined,
          is_active: true,
        }),
      }),
    onSuccess: (created) => {
      setCreateModalOpen(false);
      setNewEmail("");
      setNewName("");
      setNewPassword("");
      setNewEmpId("");
      setNewTitle("");
      setNewPhone("");
      setNewTeamId("");
      setNewRole("agent");
      setNewDeptId("");
      setNewDepartmentName("");
      setNewSupportTeamName("");
      setErrorMsg(null);
      queryClient.invalidateQueries({ queryKey: ["departments"] });
      queryClient.invalidateQueries({ queryKey: ["support-teams"] });
      showSuccess(`User '${created.full_name}' (${created.email}) created successfully. They can sign in with the email and password you entered.`);
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      queryClient.invalidateQueries({ queryKey: ["support-agents"] });
    },
    onError: (err: unknown) => {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to create user.");
    },
  });

  const saveEditUserMutation = useMutation({
    mutationFn: async () => {
      if (!editUser) return;
      await apiRequest(`/users/${editUser.id}`, {
        method: "PUT",
        body: JSON.stringify({
          full_name: editName,
          email: editEmail,
          employee_id: editEmpId,
          job_title: editTitle || null,
          phone: editPhone || null,
          ...(editRole !== "admin" ? {
            department_id: editDeptId ? Number(editDeptId) : 0,
            support_team_id: editTeamId ? Number(editTeamId) : 0,
          } : {}),
          is_active: editActive,
        }),
      });
      if (editRole !== editUser.role) {
        await apiRequest(`/users/${editUser.id}/role`, {
          method: "PATCH",
          body: JSON.stringify({
            role: editRole,
            support_team_id: editRole === "admin" ? 0 : editTeamId ? Number(editTeamId) : 0,
          }),
        });
      }
    },
    onSuccess: () => {
      setEditUser(null);
      setErrorMsg(null);
      showSuccess("User account updated in PostgreSQL.");
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      queryClient.invalidateQueries({ queryKey: ["support-agents"] });
    },
    onError: (err: unknown) => {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to update user.");
    },
  });

  const toggleActiveMutation = useMutation({
    mutationFn: (u: UserDetail) =>
      apiRequest(`/users/${u.id}`, {
        method: "PUT",
        body: JSON.stringify({ is_active: !u.is_active }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (err: unknown) => {
      setErrorMsg(err instanceof ApiError ? err.message : "Cannot change user status.");
    },
  });

  const deleteUserMutation = useMutation({
    mutationFn: (userId: number) =>
      apiRequest(`/users/${userId}`, { method: "DELETE" }),
    onSuccess: () => {
      showSuccess("User removed from database.");
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      queryClient.invalidateQueries({ queryKey: ["support-agents"] });
    },
    onError: (err: unknown) => {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to delete user.");
    },
  });


  const resetPasswordMutation = useMutation({
    mutationFn: async () => {
      if (!resetUser) throw new Error("No user selected.");
      const ticketId = Number(recoveryTicketId);

      if (!Number.isSafeInteger(ticketId) || ticketId < 1 || !verificationConfirmed) {
        throw new Error("Valid ticket ID and identity verification are required.");
      }

      return apiRequest<{ temporary_password: string }>(
        `/users/${resetUser.id}/reset-password`,
        {
          method: "POST",
          body: JSON.stringify({
            recovery_ticket_id: ticketId,
            identity_verified: true,
            verification_method: verificationMethod,
          }),
        }
      );
    },
    onSuccess: (data) => {
      setResetTemporaryPassword(data.temporary_password);
      setResetError(null);
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      resetPasswordMutation.reset();
    },
    onError: (err: unknown) => {
      setResetError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Password reset failed."
      );
    },
  });

  const createTeamMutation = useMutation({
    mutationFn: () =>
      apiRequest("/users/support-teams", {
        method: "POST",
        body: JSON.stringify({
          name: teamName,
          code: teamCode,
          specialization: teamSpec,
        }),
      }),
    onSuccess: () => {
      setTeamModalOpen(false);
      setTeamName("");
      setTeamCode("");
      setTeamSpec("");
      showSuccess("New IT Support Team created and active.");
      queryClient.invalidateQueries({ queryKey: ["support-teams"] });
    },
    onError: (err: unknown) => {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to create support team.");
    },
  });


  const openResetModal = (user: UserDetail) => {
    resetPasswordMutation.reset();
    setResetUser(user);
    setRecoveryTicketId("");
    setVerificationMethod("in_person_id");
    setVerificationConfirmed(false);
    setResetTemporaryPassword(null);
    setResetError(null);
  };

  const closeResetModal = () => {
    if (resetPasswordMutation.isPending) return;
    setResetUser(null);
    setRecoveryTicketId("");
    setVerificationConfirmed(false);
    setResetTemporaryPassword(null);
    setResetError(null);
    resetPasswordMutation.reset();
  };

  const openEditModal = (u: UserDetail) => {
    setEditUser(u);
    setEditName(u.full_name);
    setEditEmail(u.email);
    setEditEmpId(u.employee_id || "");
    setEditTitle(u.job_title || "");
    setEditPhone(u.phone || "");
    setEditRole(u.role);
    setEditDeptId(u.department_id ? String(u.department_id) : "");
    setEditTeamId(u.support_team_id ? String(u.support_team_id) : "");
    setEditActive(u.is_active);
    setErrorMsg(null);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            User, Role & Support Team Administration
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Provision custom Employee, Agent, and Admin accounts stored directly in PostgreSQL.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setTeamModalOpen(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-700 cursor-pointer"
          >
            <Building2 className="w-4 h-4 text-blue-600" />
            New Support Team
          </button>
          <button
            onClick={() => {
              setErrorMsg(null);
              setCreateModalOpen(true);
            }}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-xs cursor-pointer"
          >
            <UserPlus className="w-4 h-4" />
            Create User Account
          </button>
        </div>
      </div>

      {successMsg && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center gap-2.5 text-xs font-semibold text-emerald-800">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {errorMsg && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 flex items-center justify-between text-xs text-red-700">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600" />
            <span>{errorMsg}</span>
          </div>
          <button onClick={() => setErrorMsg(null)} className="font-bold underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Filters Bar (Search + Role + Department + Support Team Dropdown) */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-2xs grid grid-cols-1 md:grid-cols-5 gap-3">
        <div className="md:col-span-2 relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search users by name, email, employee ID, phone, or title..."
            className="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:border-blue-600 focus:bg-white"
          />
        </div>

        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          aria-label="Filter by role"
          className="px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg font-medium text-slate-700"
        >
          <option value="all">All Roles</option>
          <option value="admin">Administrators</option>
          <option value="agent">IT Support Agents</option>
          <option value="employee">Employees</option>
        </select>

        <select
          value={deptFilter}
          onChange={(e) => setDeptFilter(e.target.value)}
          aria-label="Filter by department"
          className="px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg font-medium text-slate-700"
        >
          <option value="all">All Departments</option>
          {departments?.map((d) => (
            <option key={d.id} value={String(d.id)}>
              {d.name}
            </option>
          ))}
        </select>

        <select
          value={teamFilter}
          onChange={(e) => setTeamFilter(e.target.value)}
          aria-label="Filter by support team dropdown"
          className="px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg font-medium text-slate-700"
        >
          <option value="all">All Support Teams</option>
          {supportTeams?.map((t) => (
            <option key={t.id} value={String(t.id)}>
              {t.name} ({t.code})
            </option>
          ))}
        </select>
      </div>

      {/* Users Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/80 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                <th className="py-3.5 px-5">User / Identity</th>
                <th className="py-3.5 px-4">Role</th>
                <th className="py-3.5 px-4">Department</th>
                <th className="py-3.5 px-4">Support Team</th>
                <th className="py-3.5 px-4">Phone</th>
                <th className="py-3.5 px-4">Status</th>
                <th className="py-3.5 px-4">Last Login</th>
                <th className="py-3.5 px-5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {isLoading ? (
                [...Array(3)].map((_, i) => (
                  <tr key={i} className="animate-pulse">
                    <td colSpan={8} className="py-4 px-5">
                      <div className="h-6 bg-slate-100 rounded" />
                    </td>
                  </tr>
                ))
              ) : (usersData?.items || []).length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-10 text-center text-slate-500">
                    No users match the selected filters. Click{" "}
                    <strong>Create User Account</strong> to add a new user to PostgreSQL.
                  </td>
                </tr>
              ) : (
                usersData?.items.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50/80">
                    <td className="py-3.5 px-5">
                      <div className="flex items-center gap-2.5">
                        <span className="font-bold text-slate-900">{u.full_name}</span>
                        {u.employee_id && (
                          <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-mono text-[10px]">
                            {u.employee_id}
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-500 font-mono">{u.email}</p>
                      {u.job_title && (
                        <p className="text-[11px] text-slate-400">{u.job_title}</p>
                      )}
                    </td>
                    <td className="py-3.5 px-4">
                      <RoleBadge role={u.role} />
                    </td>
                    <td className="py-3.5 px-4 text-slate-700 font-medium">
                      {u.role === "admin" ? "—" : u.department?.name || "—"}
                    </td>
                    <td className="py-3.5 px-4 text-slate-700">
                      {u.role !== "admin" && u.support_team ? (
                        <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 font-medium">
                          {u.support_team.name}
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-600">
                      {u.phone || <span className="text-slate-400">—</span>}
                    </td>
                    <td className="py-3.5 px-4">
                      {u.is_active ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 font-semibold border border-emerald-200">
                          <UserCheck className="w-3 h-3" />
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-red-50 text-red-700 font-semibold border border-red-200">
                          <UserX className="w-3 h-3" />
                          Deactivated
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-slate-500">
                      {formatDateTime(u.last_login_at)}
                    </td>
                    <td className="py-3.5 px-5 text-right space-x-1.5 whitespace-nowrap">
                      <button
                        onClick={() => openEditModal(u)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-semibold cursor-pointer"
                      >
                        <Edit3 className="w-3 h-3" />
                        Edit
                      </button>
                      {u.is_active && (
                        <button
                          type="button"
                          onClick={() => openResetModal(u)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-blue-200 bg-blue-50 hover:bg-blue-100 text-blue-700 font-semibold"
                        >
                          <KeyRound className="w-3 h-3" />
                          Reset Password
                        </button>
                      )}
                      <button
                        onClick={() => toggleActiveMutation.mutate(u)}
                        className={`px-2 py-1 rounded font-semibold cursor-pointer ${
                          u.is_active
                            ? "text-amber-700 hover:bg-amber-50"
                            : "text-emerald-600 hover:bg-emerald-50"
                        }`}
                      >
                        {u.is_active ? "Disable" : "Enable"}
                      </button>
                      {u.role !== "admin" && (
                        <button
                          onClick={() => deleteUserMutation.mutate(u.id)}
                          title="Delete User"
                          className="p-1.5 rounded text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors cursor-pointer"
                        >
                          <Trash2 className="w-3.5 h-3.5 inline" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create User Modal */}
      {createModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 overflow-y-auto">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-slate-900">Provision New Enterprise User</h3>
              <button onClick={() => setCreateModalOpen(false)} className="text-slate-400">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="sm:col-span-2">
                <label className="block font-bold uppercase text-slate-700 mb-1">Full Name *</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Enter name"
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:border-blue-600 focus:bg-white"
                />
              </div>
              <div className="sm:col-span-2 p-3.5 rounded-xl bg-blue-50/50 border border-blue-200/80 space-y-3">
                <p className="text-[11px] font-bold uppercase tracking-wider text-blue-800">
                  Login Credentials (Set by Administrator)
                </p>
                <div>
                  <label className="flex items-center gap-1 font-bold uppercase text-slate-700 mb-1">
                    <Mail className="w-3.5 h-3.5 text-blue-600" />
                    Corporate Email ID *
                  </label>
                  <input
                    type="email"
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    placeholder="Enter email ID"
                    className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg font-mono focus:outline-none focus:border-blue-600"
                  />
                </div>
                <div>
                  <label className="flex items-center justify-between font-bold uppercase text-slate-700 mb-1">
                    <span className="inline-flex items-center gap-1">
                      <KeyRound className="w-3.5 h-3.5 text-blue-600" />
                      Set Login Password *
                    </span>
                    <button
                      type="button"
                      onClick={() => setShowNewPassword(!showNewPassword)}
                      className="inline-flex items-center gap-1 text-[11px] text-blue-600 hover:underline normal-case font-semibold cursor-pointer"
                    >
                      {showNewPassword ? (
                        <>
                          <EyeOff className="w-3 h-3" /> Hide
                        </>
                      ) : (
                        <>
                          <Eye className="w-3 h-3" /> Show
                        </>
                      )}
                    </button>
                  </label>
                  <input
                    type={showNewPassword ? "text" : "password"}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="Enter password (minimum 4 characters)"
                    className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg font-mono focus:outline-none focus:border-blue-600"
                  />
                </div>
              </div>
              <div>
                <label className="flex items-center gap-1 font-bold uppercase text-slate-700 mb-1">
                  <Phone className="w-3 h-3 text-blue-600" />
                  Phone Number
                </label>
                <input
                  type="tel"
                  value={newPhone}
                  onChange={(e) => setNewPhone(e.target.value)}
                  placeholder="Enter mobile number"
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg font-mono"
                />
              </div>
              <div>
                <label className="block font-bold uppercase text-slate-700 mb-1">Employee ID</label>
                <input
                  type="text"
                  value={newEmpId}
                  onChange={(e) => setNewEmpId(e.target.value)}
                  placeholder="Enter employee ID"
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg font-mono"
                />
              </div>
              <div>
                <label className="block font-bold uppercase text-slate-700 mb-1">Role *</label>
                <select
                  aria-label="New account role"
                  value={newRole}
                  onChange={(e) => {
                    const role = e.target.value as RoleType;
                    setNewRole(role);
                    setErrorMsg(null);
                  }}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg"
                >
                  <option value="employee">Employee</option>
                  <option value="agent">IT Support Agent</option>
                  <option value="admin">Administrator</option>
                </select>
              </div>
              <div>
                <label className="block font-bold uppercase text-slate-700 mb-1">Job Title</label>
                <input
                  type="text"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="Enter job title"
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg"
                />
              </div>
              <>
              <div>
                <label className="block font-bold uppercase text-slate-700 mb-1">Department</label>
                <select
                  aria-label="New account department"
                  value={newDeptId}
                  onChange={(e) => setNewDeptId(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg"
                >
                  <option value="">Select Department...</option>
                  {departments?.map((d) => (
                    <option key={d.id} value={String(d.id)}>
                      {d.name}
                    </option>
                  ))}
                  <option value="new">Create new department...</option>
                </select>
                {newDeptId === "new" && <input aria-label="New department name" value={newDepartmentName}
                  onChange={e => setNewDepartmentName(e.target.value)} placeholder="Enter new department name"
                  minLength={2} maxLength={120} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2" />}
              </div>
              <div className="sm:col-span-2">
                <label className="block font-bold uppercase text-slate-700 mb-1">
                  Support Team (Active Teams)
                </label>
                <select
                  aria-label="New account support team"
                  value={newTeamId}
                  onChange={(e) => setNewTeamId(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg"
                >
                  <option value="">No support team</option>
                  {supportTeams?.map((t) => (
                    <option key={t.id} value={String(t.id)}>
                      {t.name} ({t.code})
                    </option>
                  ))}
                  <option value="new">Create new support team...</option>
                </select>
                {newTeamId === "new" && <input aria-label="New support team name" value={newSupportTeamName}
                  onChange={e => setNewSupportTeamName(e.target.value)} placeholder="Enter new support team name"
                  minLength={2} maxLength={120} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2" />}
                <p className="mt-2 text-[11px] text-slate-500">
                  IT Support Agents access the support dashboard. Administrators access the admin console.
                  Both sign in with the email and password assigned here.
                </p>
              </div>
              </>
            </div>
            {errorMsg && <p role="alert" className="rounded-lg bg-red-50 p-3 text-xs text-red-700">{errorMsg}</p>}

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-200">
              <button
                onClick={() => setCreateModalOpen(false)}
                className="px-4 py-2 rounded-lg border border-slate-300 text-xs font-semibold text-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={() => createUserMutation.mutate()}
                disabled={!newEmail.trim() || newName.trim().length < 2 || newPassword.length < 4 || createUserMutation.isPending ||
                  ((newDeptId === "new" && newDepartmentName.trim().length < 2) ||
                    (newTeamId === "new" && newSupportTeamName.trim().length < 2))}
                className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-semibold cursor-pointer"
              >
                {createUserMutation.isPending ? "Creating..." : "Create Account"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit User & Role Modal */}
      {editUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Shield className="w-4 h-4 text-blue-600" />
                <h3 className="text-base font-bold text-slate-900">
                  Manage User: {editUser.full_name}
                </h3>
              </div>
              <button onClick={() => setEditUser(null)} className="text-slate-400">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="sm:col-span-2">
                <label className="block font-bold uppercase text-slate-700 mb-1">Full Name</label>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg"
                />
              </div>
              <div className="sm:col-span-2">
                <label className="block font-bold uppercase text-slate-700 mb-1">
                  Corporate Email ID
                </label>
                <input
                  type="email"
                  value={editEmail}
                  onChange={(e) => setEditEmail(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg font-mono"
                />
              </div>
              <div>
                <label className="block font-bold uppercase text-slate-700 mb-1">
                  Assigned Role
                </label>
                <select
                  value={editRole}
                  onChange={(e) => setEditRole(e.target.value as RoleType)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg font-semibold"
                >
                  <option value="employee">Employee</option>
                  <option value="agent">IT Consultant (IT Support Agent)</option>
                  <option value="admin">Administrator</option>
                </select>
              </div>
              <div>
                <label className="block font-bold uppercase text-slate-700 mb-1">Employee ID</label>
                <input
                  type="text"
                  value={editEmpId}
                  onChange={(e) => setEditEmpId(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg font-mono"
                />
              </div>
              <div>
                <label className="block font-bold uppercase text-slate-700 mb-1">Job Title</label>
                <input
                  type="text"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg"
                />
              </div>
              <div>
                <label className="block font-bold uppercase text-slate-700 mb-1">
                  Phone Number
                </label>
                <input
                  type="tel"
                  value={editPhone}
                  onChange={(e) => setEditPhone(e.target.value)}
                  placeholder="Enter mobile number"
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg font-mono"
                />
              </div>
              {editRole !== "admin" && <>
              <div>
                <label className="block font-bold uppercase text-slate-700 mb-1">Department</label>
                <select
                  value={editDeptId}
                  onChange={(e) => setEditDeptId(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg"
                >
                  <option value="">Unassigned</option>
                  {departments?.map((d) => (
                    <option key={d.id} value={String(d.id)}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block font-bold uppercase text-slate-700 mb-1">Support Team</label>
                <select
                  value={editTeamId}
                  onChange={(e) => setEditTeamId(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg"
                >
                  <option value="">None</option>
                  {supportTeams?.map((t) => (
                    <option key={t.id} value={String(t.id)}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </div>
              </>}
              <div className="sm:col-span-2 pt-1">
                <label className="inline-flex items-center gap-2 font-semibold text-slate-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editActive}
                    onChange={(e) => setEditActive(e.target.checked)}
                    className="rounded border-slate-300 text-blue-600"
                  />
                  Account Active (Allow login & ticket assignment)
                </label>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-200">
              <button
                onClick={() => setEditUser(null)}
                className="px-4 py-2 rounded-lg border border-slate-300 text-xs font-semibold text-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={() => saveEditUserMutation.mutate()}
                disabled={saveEditUserMutation.isPending}
                className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold cursor-pointer"
              >
                {saveEditUserMutation.isPending ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      )}


      {/* Admin-assisted password reset */}
      {resetUser && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/70 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="admin-reset-title"
        >
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 id="admin-reset-title" className="text-lg font-bold text-slate-900">
                  Admin Password Reset
                </h3>
                <p className="text-sm text-slate-600 mt-1">
                  {resetUser.full_name} ({resetUser.email})
                </p>
              </div>
              <button
                type="button"
                onClick={closeResetModal}
                disabled={resetPasswordMutation.isPending}
                aria-label="Close password reset"
                className="text-slate-500 disabled:opacity-50"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {!resetTemporaryPassword ? (
              <div className="space-y-4">
                <p className="text-xs text-amber-800 bg-amber-50 rounded-lg p-3">
                  Verify the account holder independently before continuing.
                  Use the matching Critical IAM Password Recovery ticket.
                </p>

                <div>
                  <label
                    htmlFor="recovery-ticket-id"
                    className="block text-sm font-semibold text-slate-700 mb-1"
                  >
                    Recovery Ticket ID
                  </label>
                  <input
                    id="recovery-ticket-id"
                    type="number"
                    min="1"
                    step="1"
                    value={recoveryTicketId}
                    onChange={(e) => setRecoveryTicketId(e.target.value)}
                    placeholder="Ticket database ID"
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                  />
                  <p className="text-xs text-slate-500 mt-1">
                    Enter the numeric ticket ID, not the TKT ticket number.
                  </p>
                </div>

                <div>
                  <label
                    htmlFor="verification-method"
                    className="block text-sm font-semibold text-slate-700 mb-1"
                  >
                    Identity Verification Method
                  </label>
                  <select
                    id="verification-method"
                    value={verificationMethod}
                    onChange={(e) =>
                      setVerificationMethod(
                        e.target.value as
                          "in_person_id" | "manager_callback" | "hr_confirmation"
                      )
                    }
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                  >
                    <option value="in_person_id">In-person ID verification</option>
                    <option value="manager_callback">Manager callback</option>
                    <option value="hr_confirmation">HR confirmation</option>
                  </select>
                </div>

                <label className="flex items-start gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={verificationConfirmed}
                    onChange={(e) => setVerificationConfirmed(e.target.checked)}
                    className="mt-1"
                  />
                  I confirm that I independently verified this person's identity.
                </label>

                {resetError && (
                  <p className="text-sm text-red-700 bg-red-50 rounded-lg p-3">
                    {resetError}
                  </p>
                )}

                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={closeResetModal}
                    disabled={resetPasswordMutation.isPending}
                    className="border border-slate-300 rounded-lg px-4 py-2 text-sm"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => resetPasswordMutation.mutate()}
                    disabled={
                      resetPasswordMutation.isPending ||
                      !verificationConfirmed ||
                      !Number.isSafeInteger(Number(recoveryTicketId)) ||
                      Number(recoveryTicketId) < 1
                    }
                    className="bg-blue-600 text-white rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
                  >
                    {resetPasswordMutation.isPending
                      ? "Resetting..."
                      : "Generate Temporary Password"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-sm font-semibold text-emerald-700">
                  Password reset successful.
                </p>
                <p className="text-xs text-slate-600">
                  This temporary password is shown once. Share it only through
                  an approved secure channel with the verified account holder.
                  The user must change it at next sign-in.
                </p>
                <div className="bg-slate-100 rounded-lg p-4">
                  <code className="text-sm font-bold break-all select-all text-slate-900">
                    {resetTemporaryPassword}
                  </code>
                </div>
                <button
                  type="button"
                  onClick={closeResetModal}
                  className="w-full bg-blue-600 text-white rounded-lg px-4 py-2 text-sm font-semibold"
                >
                  Close and Clear Temporary Password
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Create Support Team Modal */}
      {teamModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-slate-900">Create IT Support Team</h3>
              <button onClick={() => setTeamModalOpen(false)} className="text-slate-400">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div>
                <label className="block font-bold uppercase text-slate-700 mb-1">Team Name *</label>
                <input
                  type="text"
                  value={teamName}
                  onChange={(e) => setTeamName(e.target.value)}
                  placeholder="Enter support team name"
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg"
                />
              </div>
              <div>
                <label className="block font-bold uppercase text-slate-700 mb-1">Short Code *</label>
                <input
                  type="text"
                  value={teamCode}
                  onChange={(e) => setTeamCode(e.target.value.toUpperCase())}
                  placeholder="Enter team code"
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg font-mono"
                />
              </div>
              <div>
                <label className="block font-bold uppercase text-slate-700 mb-1">
                  Specialization
                </label>
                <input
                  type="text"
                  value={teamSpec}
                  onChange={(e) => setTeamSpec(e.target.value)}
                  placeholder="Enter team specialization"
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-3 border-t border-slate-200">
              <button
                onClick={() => setTeamModalOpen(false)}
                className="px-4 py-2 rounded-lg border border-slate-300 text-xs font-semibold text-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={() => createTeamMutation.mutate()}
                disabled={!teamName || !teamCode || createTeamMutation.isPending}
                className="inline-flex items-center gap-1 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                Create Team
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
