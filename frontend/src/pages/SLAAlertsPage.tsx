import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { apiRequest } from "../services/api";
import { PaginatedTickets } from "../types";
import { PriorityBadge, StatusBadge } from "../components/ui/Badges";
import { formatDateTime } from "../utils/format";

export const SLAAlertsPage: React.FC = () => {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, refetch } = useQuery<PaginatedTickets>({
    queryKey: ["sla-alerts", user?.id, page],
    queryFn: () => apiRequest<PaginatedTickets>(`/notifications/sla-alerts?page=${page}&page_size=20`),
    refetchInterval: 20000,
    staleTime: 0,
    refetchOnMount: "always",
  });
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">SLA Alerts</h1>
          <p className="mt-1 text-sm text-slate-500">
            {user?.role === "admin" ? "Unresolved tickets past their resolution deadline across all teams."
              : "Unresolved tickets past their resolution deadline, assigned to you or waiting in your team's unassigned queue."}
          </p>
          <p className="mt-1 text-xs text-slate-500">Updates every 20 seconds. Resolved and closed tickets leave this list automatically.</p>
        </div>
        <button onClick={() => refetch()} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold">
          <RotateCcw className="h-4 w-4" /> Refresh
        </button>
      </div>
      {isError ? (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
          Unable to load SLA alerts. Please try Refresh.
        </div>
      ) : isLoading ? <p role="status" className="text-sm text-slate-500">Loading SLA alerts...</p> : (
        <>
          <p className="text-sm font-semibold text-slate-700">{data?.total || 0} outstanding SLA alerts</p>
          {data?.total === 0 && <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-600">No outstanding resolution SLA breaches.</div>}
          <div className="space-y-3">
            {data?.items.map(ticket => (
              <article key={ticket.id} className="rounded-xl border border-red-200 bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="mb-1 flex items-center gap-2 text-xs font-bold text-red-700"><AlertTriangle className="h-4 w-4" /> Resolution SLA breached</p>
                    <Link to={`/tickets/${ticket.ticket_number}`} className="break-words font-semibold text-blue-700 hover:underline">{ticket.ticket_number} — {ticket.subject}</Link>
                  </div>
                  <div className="flex items-center gap-2"><PriorityBadge priority={ticket.priority} /><StatusBadge status={ticket.status} /></div>
                </div>
                <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
                  <div><dt className="text-slate-500">Resolution deadline</dt><dd className="mt-1 font-semibold text-red-700">{formatDateTime(ticket.resolution_due_at)}</dd></div>
                  <div><dt className="text-slate-500">Overdue by</dt><dd className="mt-1 font-semibold text-red-700">{Math.max(1, Math.floor((Date.now() - new Date(ticket.resolution_due_at!).getTime()) / 60000))} minutes</dd></div>
                  <div><dt className="text-slate-500">Employee / requester</dt><dd className="mt-1 text-slate-800">{ticket.requester.full_name}</dd></div>
                  <div><dt className="text-slate-500">Consultant / support team</dt><dd className="mt-1 text-slate-800">{ticket.assigned_agent?.full_name || "Unassigned"} / {ticket.support_team_name || "No team"}</dd></div>
                </dl>
              </article>
            ))}
          </div>
          {data && data.total_pages > 1 && <div className="flex items-center justify-end gap-3 text-sm">
            <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded border px-3 py-2 disabled:opacity-40">Previous</button>
            <span>Page {page} of {data.total_pages}</span>
            <button disabled={page >= data.total_pages} onClick={() => setPage(page + 1)} className="rounded border px-3 py-2 disabled:opacity-40">Next</button>
          </div>}
        </>
      )}
    </div>
  );
};
