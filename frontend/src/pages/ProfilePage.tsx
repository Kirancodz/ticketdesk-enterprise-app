import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowLeft,
  BadgeCheck,
  Building2,
  Calendar,
  CheckCircle2,
  Clock,
  Edit3,
  IdCard,
  KeyRound,
  Lock,
  Mail,
  MapPin,
  Phone,
  Save,
  Shield,
  Ticket,
  UserCheck,
  Users,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { ApiError, apiRequest } from "../services/api";
import { DashboardSummary } from "../types";
import { RoleBadge } from "../components/ui/Badges";
import { formatDateTime } from "../utils/format";

export const ProfilePage: React.FC = () => {
  const { user, refreshProfile } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const isAdmin = user?.role === "admin";

  // Editable state for Administrator profile
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [phone, setPhone] = useState("");
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      setFullName(user.full_name || "");
      setEmail(user.email || "");
      setEmployeeId(user.employee_id || "");
      setJobTitle(user.job_title || "");
      setPhone(user.phone || "");
    }
  }, [user]);

  const { data: summary } = useQuery<DashboardSummary>({
    queryKey: ["dashboard-summary"],
    queryFn: () => apiRequest<DashboardSummary>("/dashboard/summary"),
  });

  const updateAdminProfileMutation = useMutation({
    mutationFn: () =>
      apiRequest("/auth/me", {
        method: "PUT",
        body: JSON.stringify({
          full_name: fullName,
          email,
          employee_id: employeeId || null,
          job_title: jobTitle || null,
          phone: phone || null,
        }),
      }),
    onSuccess: async () => {
      setSaveError(null);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 4000);
      await refreshProfile();
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (err: unknown) => {
      setSaveError(err instanceof ApiError ? err.message : "Failed to save profile changes.");
    },
  });

  if (!user) return null;

  const initials = (isAdmin ? fullName || user.full_name : user.full_name)
    .split(" ")
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const readOnlyFields = [
    {
      label: "Full Legal Name",
      value: user.full_name,
      icon: UserCheck,
      mono: false,
    },
    {
      label: "Employee ID",
      value: user.employee_id || `EMP-${String(user.id).padStart(4, "0")}`,
      icon: IdCard,
      mono: true,
    },
    {
      label: "Corporate Email Address",
      value: user.email,
      icon: Mail,
      mono: true,
    },
    {
      label: "Job Title / Designation",
      value: user.job_title || "Corporate Staff Member",
      icon: BadgeCheck,
      mono: false,
    },
    {
      label: "Department",
      value: user.department
        ? `${user.department.name} (${user.department.code})`
        : "Corporate Operations",
      icon: Building2,
      mono: false,
    },
    {
      label: "Office Location",
      value: user.department?.location || "San Francisco HQ — Enterprise Campus",
      icon: MapPin,
      mono: false,
    },
    {
      label: "Work Phone / Extension",
      value: user.phone || "Not configured",
      icon: Phone,
      mono: true,
    },
    {
      label: "Access Role & Clearance",
      value: user.role_info?.display_name || user.role.toUpperCase(),
      icon: Shield,
      mono: false,
    },
    {
      label: "Account Provisioned Date",
      value: formatDateTime(user.created_at),
      icon: Calendar,
      mono: false,
    },
    {
      label: "Last Authenticated Login",
      value: formatDateTime(user.last_login_at),
      icon: Clock,
      mono: false,
    },
  ];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Top Navigation & Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <button
            type="button"
            onClick={() => navigate("/dashboard")}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 mb-2 cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to Workspace
          </button>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            {isAdmin ? "Administrator Identity & Profile Settings" : "Corporate Employee Profile"}
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {isAdmin
              ? "Update your administrator identity and contact phone number."
              : "Verified enterprise directory record synchronized with Corporate Active Directory & SSO."}
          </p>
        </div>

        {isAdmin ? (
          <span className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-blue-50 text-blue-700 border border-blue-200 text-xs font-semibold self-start sm:self-auto">
            <Edit3 className="w-3.5 h-3.5 text-blue-600" />
            Editable Administrator Profile
          </span>
        ) : (
          <span className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-900 text-white text-xs font-semibold shadow-2xs self-start sm:self-auto">
            <Lock className="w-3.5 h-3.5 text-amber-400" />
            Read-Only Identity Record
          </span>
        )}
      </div>

      {/* Non-Editable Governance Notice Banner (Shown ONLY for non-admin roles) */}
      {!isAdmin && (
        <div className="p-4 rounded-xl bg-amber-50/80 border border-amber-200 flex items-start gap-3 text-xs text-amber-900">
          <Lock className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <p className="font-bold">
              Directory Profile Locked — Managed by Enterprise IT Governance
            </p>
            <p className="text-amber-800/90 mt-0.5 leading-relaxed">
              In accordance with corporate security policy, employee identity details (Name, Employee ID, Email, Department, and Role) are strictly read-only and cannot be edited by the employee. To request a directory change, please submit an Access / HR ticket.
            </p>
          </div>
        </div>
      )}

      {saveSuccess && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center gap-2.5 text-xs font-semibold text-emerald-800">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>Administrator profile changes saved to PostgreSQL successfully!</span>
        </div>
      )}

      {saveError && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 flex items-center justify-between text-xs text-red-700">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{saveError}</span>
          </div>
          <button onClick={() => setSaveError(null)} className="font-bold underline">
            Dismiss
          </button>
        </div>
      )}

      {/* User Hero Card */}
      <div className="bg-navy-900 text-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
        <div className="flex items-center gap-5">
          <div className="w-16 h-16 rounded-2xl bg-blue-600 text-white font-bold text-xl flex items-center justify-center shadow-lg shadow-blue-600/30 border border-blue-400/30 shrink-0">
            {initials}
          </div>
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2.5">
              <h2 className="text-xl font-bold text-white">
                {isAdmin ? fullName || user.full_name : user.full_name}
              </h2>
              <RoleBadge role={user.role} />
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                Active SSO Session
              </span>
            </div>
            <p className="text-xs text-slate-300 font-medium">
              {(isAdmin ? jobTitle : user.job_title) || "Corporate Staff"} •{" "}
              {isAdmin ? "All Departments" : user.department?.name || "Enterprise IT"}
            </p>
            <p className="text-xs font-mono text-blue-400">{isAdmin ? email : user.email}</p>
          </div>
        </div>

        {summary && (
          <div className="grid grid-cols-3 gap-3 w-full md:w-auto pt-4 md:pt-0 border-t md:border-t-0 border-slate-800">
            <div className="px-4 py-2.5 rounded-xl bg-slate-800/90 border border-slate-700 text-center">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block">
                Total Tickets
              </span>
              <span className="text-lg font-bold text-white">{summary.total_tickets}</span>
            </div>
            <div className="px-4 py-2.5 rounded-xl bg-slate-800/90 border border-slate-700 text-center">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block">
                Active Open
              </span>
              <span className="text-lg font-bold text-amber-400">
                {summary.open_tickets + summary.assigned_tickets + summary.in_progress_tickets}
              </span>
            </div>
            <div className="px-4 py-2.5 rounded-xl bg-slate-800/90 border border-slate-700 text-center">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block">
                Resolved
              </span>
              <span className="text-lg font-bold text-emerald-400">
                {summary.resolved_tickets + summary.closed_tickets}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* ADMIN VIEW: Editable Profile Form with Save Option Button */}
      {isAdmin ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            updateAdminProfileMutation.mutate();
          }}
          className="bg-white rounded-xl border border-slate-200 p-6 shadow-2xs space-y-5"
        >
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-bold text-slate-900">
                Edit Administrator Profile Details
              </h3>
              <p className="text-xs text-slate-500">
                Modify your administrator account information and click Save Profile Changes above
              </p>
            </div>
            <button
              type="submit"
              disabled={updateAdminProfileMutation.isPending || !fullName.trim() || !email.trim()}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
            >
              <Save className="w-3.5 h-3.5" />
              <span>
                {updateAdminProfileMutation.isPending ? "Saving..." : "Save Profile Changes"}
              </span>
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-700">
                <UserCheck className="w-3.5 h-3.5 text-blue-600" />
                Full Legal Name *
              </label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                className="w-full px-3.5 py-2.5 text-xs rounded-lg bg-slate-50 border border-slate-300 text-slate-900 font-semibold focus:outline-none focus:border-blue-600 focus:bg-white"
              />
            </div>

            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-700">
                <IdCard className="w-3.5 h-3.5 text-blue-600" />
                Employee ID
              </label>
              <input
                type="text"
                value={employeeId}
                onChange={(e) => setEmployeeId(e.target.value)}
                placeholder="EMP-1001"
                className="w-full px-3.5 py-2.5 text-xs rounded-lg bg-slate-50 border border-slate-300 text-slate-900 font-mono font-semibold focus:outline-none focus:border-blue-600 focus:bg-white"
              />
            </div>

            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-700">
                <Mail className="w-3.5 h-3.5 text-blue-600" />
                Corporate Email Address *
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full px-3.5 py-2.5 text-xs rounded-lg bg-slate-50 border border-slate-300 text-slate-900 font-mono font-semibold focus:outline-none focus:border-blue-600 focus:bg-white"
              />
            </div>

            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-700">
                <BadgeCheck className="w-3.5 h-3.5 text-blue-600" />
                Job Title / Designation
              </label>
              <input
                type="text"
                value={jobTitle}
                onChange={(e) => setJobTitle(e.target.value)}
                placeholder="Director of Enterprise IT & ITSM"
                className="w-full px-3.5 py-2.5 text-xs rounded-lg bg-slate-50 border border-slate-300 text-slate-900 font-semibold focus:outline-none focus:border-blue-600 focus:bg-white"
              />
            </div>

            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-700">
                <Phone className="w-3.5 h-3.5 text-blue-600" />
                Work Phone Number
              </label>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+1 (415) 890-1001"
                className="w-full px-3.5 py-2.5 text-xs rounded-lg bg-slate-50 border border-slate-300 text-slate-900 font-mono font-semibold focus:outline-none focus:border-blue-600 focus:bg-white"
              />
            </div>

            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-700">
                <KeyRound className="w-3.5 h-3.5 text-blue-600" />
                Password Security
              </label>
              <button
                type="button"
                onClick={() => navigate("/change-password")}
                className="w-full px-3.5 py-2.5 text-xs rounded-lg bg-blue-50 border border-blue-200 text-blue-700 font-semibold hover:bg-blue-100"
              >
                Change Password Securely
              </button>
            </div>
          </div>

          <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
            <span className="text-xs text-slate-500">
              Last Login: <strong>{formatDateTime(user.last_login_at)}</strong>
            </span>
          </div>
        </form>
      ) : (
        /* EMPLOYEE / NON-ADMIN VIEW: Strictly Read-Only Directory Attributes */
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-2xs space-y-5">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-bold text-slate-900">
                Employee Directory Attributes (Non-Editable)
              </h3>
              <p className="text-xs text-slate-500">
                All fields below are locked and synchronized from the central HRIS / Identity Provider
              </p>
            </div>
            <span className="text-[11px] font-mono text-slate-400">
              IDP: Okta-Enterprise-AD
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {readOnlyFields.map((field) => {
              const Icon = field.icon;
              return (
                <div key={field.label} className="space-y-1.5">
                  <label className="flex items-center justify-between text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    <span className="inline-flex items-center gap-1.5">
                      <Icon className="w-3.5 h-3.5 text-slate-400" />
                      {field.label}
                    </span>
                    <Lock className="w-3 h-3 text-slate-300" />
                  </label>
                  <input
                    type="text"
                    value={field.value}
                    readOnly
                    disabled
                    aria-label={field.label}
                    className={`w-full px-3.5 py-2.5 text-xs rounded-lg bg-slate-100/90 border border-slate-200 text-slate-700 font-semibold cursor-not-allowed select-all ${
                      field.mono ? "font-mono" : ""
                    }`}
                  />
                </div>
              );
            })}
          </div>

          <div className="pt-4 border-t border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <p className="text-xs text-slate-500">
              Need to update your department, phone extension, or hardware asset assignment?
            </p>
            <button
              type="button"
              onClick={() => navigate("/tickets/new")}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold transition-colors cursor-pointer self-start sm:self-auto"
            >
              <Ticket className="w-3.5 h-3.5" />
              Request Directory Update via IT Ticket
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
