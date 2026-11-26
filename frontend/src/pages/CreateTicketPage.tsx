import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowLeft,
  Building2,
  Clock,
  FileUp,
  Send,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { ApiError, apiRequest } from "../services/api";
import {
  CategoryItem,
  DepartmentInfo,
  SLAPolicyItem,
  SupportTeamInfo,
  TicketDetail,
} from "../types";
import { formatFileSize } from "../utils/format";

const createTicketSchema = z.object({
  subject: z
    .string()
    .min(5, "Subject must be at least 5 characters")
    .max(255, "Subject cannot exceed 255 characters"),
  category_id: z.coerce.number().min(1, "Please select an IT category"),
  subcategory: z.string().optional(),
  custom_subcategory: z.string().max(120).optional(),
  priority: z.enum(["critical", "high", "medium", "low"]),
  department_id: z.coerce.number().optional(),
  support_team_id: z.coerce.number().min(1, "Please select the responsible support team"),
  affected_service: z.string().max(150).optional(),
  description: z
    .string()
    .min(10, "Please provide at least 10 characters describing the issue and steps to reproduce"),
});

type CreateTicketFormInput = z.input<typeof createTicketSchema>;
type CreateTicketFormValues = z.output<typeof createTicketSchema>;

export const CreateTicketPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const { data: categories } = useQuery<CategoryItem[]>({
    queryKey: ["ticket-categories"],
    queryFn: () => apiRequest<CategoryItem[]>("/tickets/categories"),
    staleTime: 0,
    refetchOnMount: "always",
  });

  const { data: departments } = useQuery<DepartmentInfo[]>({
    queryKey: ["departments"],
    queryFn: () => apiRequest<DepartmentInfo[]>("/users/departments"),
    staleTime: 0,
    refetchOnMount: "always",
  });

  const { data: supportTeams } = useQuery<SupportTeamInfo[]>({
    queryKey: ["support-teams"],
    queryFn: () => apiRequest<SupportTeamInfo[]>("/users/support-teams"),
    staleTime: 0,
    refetchOnMount: "always",
  });

  const { data: slaPolicies } = useQuery<SLAPolicyItem[]>({
    queryKey: ["sla-policies"],
    queryFn: () => apiRequest<SLAPolicyItem[]>("/sla"),
  });

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<CreateTicketFormInput, unknown, CreateTicketFormValues>({
    resolver: zodResolver(createTicketSchema),
    defaultValues: {
      subject: "",
      category_id: 0,
      subcategory: "",
      custom_subcategory: "",
      priority: "medium",
      department_id: user?.department?.id || undefined,
      support_team_id: undefined,
      affected_service: "",
      description: "",
    },
  });

  const watchedCategoryId = Number(watch("category_id"));
  const watchedSubcategory = watch("subcategory");
  const watchedPriority = watch("priority");

  const activeCategory = categories?.find((c) => c.id === watchedCategoryId);
  const activeSLA = slaPolicies?.find((p) => p.priority === watchedPriority);

  // Guarantee "Others" is always present in subcategory options
  const subcategoryOptions: string[] = React.useMemo(() => {
    if (!activeCategory) return ["Others"];
    const base = [...(activeCategory.subcategories || [])];
    if (!base.some((s) => s.toLowerCase() === "others" || s.toLowerCase() === "other")) {
      base.push("Others");
    }
    return base;
  }, [activeCategory]);

  // Filter Knowledge Base articles matching the selected category (or top articles if none selected)


  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
  };

  const onSubmit = async (values: CreateTicketFormValues) => {
    setSubmitError(null);
    const resolvedSubcategory =
      values.subcategory === "Others" && values.custom_subcategory?.trim()
        ? `Others (${values.custom_subcategory.trim()})`
        : values.subcategory || null;

    try {
      const created = await apiRequest<TicketDetail>("/tickets", {
        method: "POST",
        body: JSON.stringify({
          subject: values.subject,
          category_id: Number(values.category_id),
          subcategory: resolvedSubcategory,
          priority: values.priority,
          department_id: values.department_id ? Number(values.department_id) : null,
          support_team_id: values.support_team_id ? Number(values.support_team_id) : null,
          affected_service: values.affected_service || null,
          description: values.description,
        }),
      });

      if (selectedFile) {
        const formData = new FormData();
        formData.append("file", selectedFile);
        await apiRequest(`/tickets/${created.ticket_number}/attachments`, {
          method: "POST",
          body: formData,
        });
      }

      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
      navigate(`/tickets/${created.ticket_number}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setSubmitError(err.message);
      } else {
        setSubmitError("Failed to create support ticket. Please check your input and try again.");
      }
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 mb-2 cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to Workspace
          </button>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Submit New IT Support Ticket
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Provide technical details and select a target support team so our engineers can resolve your request rapidly.
          </p>
        </div>
      </div>

      {submitError && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 flex items-start gap-3 text-xs text-red-700">
          <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
          <span>{submitError}</span>
        </div>
      )}

      <form onSubmit={handleSubmit(onSubmit)} className="grid grid-cols-1 lg:grid-cols-3 gap-6" noValidate>
        {/* Main Form Panel */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 p-6 shadow-2xs space-y-5">
          {/* Subject */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Ticket Subject *
            </label>
            <input
              type="text"
              placeholder="e.g., GlobalProtect VPN failing TLS handshake on macOS 15.1"
              {...register("subject")}
              className="w-full px-3.5 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 focus:bg-white transition-all"
            />
            {errors.subject && (
              <p className="mt-1 text-xs text-red-600">{errors.subject.message}</p>
            )}
          </div>

          {/* Category & Subcategory (with "Others" option) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                Category *
              </label>
              <select
                {...register("category_id", {
                  onChange: () => setValue("subcategory", ""),
                })}
                className="w-full px-3.5 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:border-blue-600 focus:bg-white"
              >
                <option value={0}>Select Category...</option>
                {categories?.map((cat) => (
                  <option key={cat.id} value={cat.id}>
                    {cat.name}
                  </option>
                ))}
              </select>
              {errors.category_id && (
                <p className="mt-1 text-xs text-red-600">{errors.category_id.message}</p>
              )}
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                Subcategory
              </label>
              <select
                {...register("subcategory")}
                disabled={!activeCategory}
                className="w-full px-3.5 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:border-blue-600 focus:bg-white disabled:opacity-50"
              >
                <option value="">Select Subcategory...</option>
                {subcategoryOptions.map((sub) => (
                  <option key={sub} value={sub}>
                    {sub}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Optional Custom Specification when "Others" Subcategory is chosen */}
          {watchedSubcategory === "Others" && (
            <div className="p-3.5 rounded-lg bg-blue-50/50 border border-blue-200/80 space-y-1.5">
              <label className="block text-xs font-bold uppercase tracking-wider text-blue-800">
                Specify "Others" Subcategory Detail (Optional)
              </label>
              <input
                type="text"
                placeholder="Briefly specify the hardware, software, or service subcategory..."
                {...register("custom_subcategory")}
                className="w-full px-3 py-2 text-xs bg-white border border-blue-200 rounded-lg focus:outline-none focus:border-blue-600"
              />
            </div>
          )}

          {/* Priority & Affected Service */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                Impact & Priority *
              </label>
              <select
                {...register("priority")}
                className="w-full px-3.5 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:border-blue-600 focus:bg-white"
              >
                <option value="low">Low (P4) — Minor inquiry / request</option>
                <option value="medium">Medium (P3) — Standard single-user issue</option>
                <option value="high">High (P2) — Severe workflow blocker</option>
                <option value="critical">Critical (P1) — Production / multi-user outage</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                Affected Application or Service
              </label>
              <input
                type="text"
                placeholder="e.g., Okta SSO, AWS Direct Connect, MacBook Pro"
                {...register("affected_service")}
                className="w-full px-3.5 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:border-blue-600 focus:bg-white"
              />
            </div>
          </div>

          {/* Department AND Support Team Dropdown (Synced live from Admin Support Teams) */}
          <div className="space-y-4 pt-1 border-t border-slate-100">
            <div>
              <label className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                <Building2 className="w-3.5 h-3.5 text-blue-600" />
                Department
              </label>
              <select
                {...register("department_id")}
                className="w-full px-3.5 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:border-blue-600 focus:bg-white"
              >
                <option value="">Default ({user?.department?.name || "Corporate"})</option>
                {departments?.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.code})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                <span className="inline-flex items-center gap-1.5">
                  <Users className="w-3.5 h-3.5 text-blue-600" />
                  Support Team
                </span>
                <span className="text-[10px] font-medium text-slate-400 normal-case">
                  Synced with Admin Support Teams
                </span>
              </label>
              <select
                {...register("support_team_id")}
                aria-label="Support Team"
                className="w-full px-3.5 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:border-blue-600 focus:bg-white"
              >
                <option value="">Auto-Route / General IT Triage</option>
                {supportTeams?.map((team) => (
                  <option key={team.id} value={team.id}>
                    {team.name} ({team.code})
                    {team.specialization ? ` — ${team.specialization}` : ""}
                  </option>
                ))}
              </select>
              {errors.support_team_id && <p className="mt-1 text-xs text-red-600">{errors.support_team_id.message}</p>}
            </div>
          </div>

          {/* Detailed Technical Description */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Detailed Technical Description *
            </label>
            <textarea
              rows={6}
              placeholder="Include exact error messages, timestamps, affected hostname/device, and steps already attempted..."
              {...register("description")}
              className="w-full px-3.5 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 focus:bg-white"
            />
            {errors.description && (
              <p className="mt-1 text-xs text-red-600">{errors.description.message}</p>
            )}
          </div>

          {/* Attachment Upload */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Supporting Attachment (Screenshot, Log, PDF)
            </label>
            {!selectedFile ? (
              <label className="flex flex-col items-center justify-center border-2 border-dashed border-slate-300 hover:border-blue-500 rounded-xl p-5 cursor-pointer bg-slate-50/60 hover:bg-blue-50/20 transition-colors">
                <FileUp className="w-6 h-6 text-slate-400 mb-1.5" />
                <span className="text-xs font-semibold text-slate-700">
                  Click to attach diagnostic file or screenshot
                </span>
                <span className="text-[11px] text-slate-400 mt-0.5">
                  Supported formats: PDF, PNG, JPG, JPEG, TXT (Max 10 MB)
                </span>
                <input
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg,.txt"
                  onChange={handleFileChange}
                  className="hidden"
                />
              </label>
            ) : (
              <div className="flex items-center justify-between px-4 py-3 rounded-lg bg-blue-50/60 border border-blue-200 text-xs">
                <div>
                  <p className="font-semibold text-slate-800">{selectedFile.name}</p>
                  <p className="text-[11px] text-slate-500">{formatFileSize(selectedFile.size)}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedFile(null)}
                  className="p-1 text-slate-500 hover:text-red-600"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>

          <div className="pt-2 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="px-4 py-2.5 rounded-lg border border-slate-300 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
            >
              <Send className="w-4 h-4" />
              <span>{isSubmitting ? "Submitting Ticket..." : "Submit Support Ticket"}</span>
            </button>
          </div>
        </div>

        {/* Requester and Live SLA Preview */}
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-2xs space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Requester Identity
              </h3>
              <button
                type="button"
                onClick={() => navigate("/profile")}
                className="text-[11px] font-semibold text-blue-600 hover:underline cursor-pointer"
              >
                View Profile
              </button>
            </div>
            <div className="text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-slate-500">Name:</span>
                <span className="font-semibold text-slate-800">{user?.full_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Email:</span>
                <span className="font-mono text-slate-700">{user?.email}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Employee ID:</span>
                <span className="font-mono text-slate-700">{user?.employee_id || "—"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Department:</span>
                <span className="font-medium text-slate-800">
                  {user?.department?.name || "Enterprise"}
                </span>
              </div>
            </div>
          </div>

          {activeSLA && (
            <div className="bg-navy-900 text-white rounded-xl p-5 shadow-2xs space-y-3">
              <div className="flex items-center gap-2 text-blue-400">
                <Clock className="w-4 h-4" />
                <h3 className="text-xs font-bold uppercase tracking-wider">
                  Active SLA Target Preview
                </h3>
              </div>
              <p className="text-xs font-semibold text-white">{activeSLA.name}</p>
              <p className="text-[11px] text-slate-300 leading-relaxed">{activeSLA.description}</p>
              <div className="pt-2 border-t border-slate-800 grid grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-[10px] uppercase text-slate-400 block">
                    First Response
                  </span>
                  <span className="font-bold text-white">
                    {activeSLA.response_target_minutes >= 60
                      ? `${activeSLA.response_target_minutes / 60} hour(s)`
                      : `${activeSLA.response_target_minutes} mins`}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] uppercase text-slate-400 block">
                    Target Resolution
                  </span>
                  <span className="font-bold text-emerald-400">
                    {activeSLA.resolution_target_minutes / 60} hours
                  </span>
                </div>
              </div>
            </div>
          )}

        </div>
      </form>


    </div>
  );
};
