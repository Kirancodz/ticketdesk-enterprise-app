import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { PriorityBadge, StatusBadge } from "../components/ui/Badges";
import { useAuth } from "../contexts/AuthContext";
import { apiRequest } from "../services/api";
import { PaginatedTickets } from "../types";
import { formatDateTime } from "../utils/format";

export const SLAAlertsPage: React.FC = () => {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["sla-alerts", user?.id, page],
    queryFn: ({ signal }) =>
      apiRequest<PaginatedTickets>(`/notifications/sla-alerts?page=${page}&page_size=20`, {
        signal,
      }),
  });

  const pageButtonClass =
    "rounded border border-slate-200 bg-white px-2.5 py-1.5 text-slate-700 disabled:opacity-40";

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">SLA Alerts</h1>
        {data && (
          <p className="mt-1 text-sm text-slate-600">
            Outstanding resolution SLA breaches <strong>{data.total}</strong>
          </p>
        )}
      </header>

      {isPending && (
        <p role="status" className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
          Loading SLA alerts…
        </p>
      )}

      {isError && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <p>Unable to load SLA alerts.</p>
          <button type="button" onClick={() => void refetch()} className="font-semibold underline">
            Try again
          </button>
        </div>
      )}

      {data && (
        <section aria-label="Outstanding resolution SLA breaches" className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          {data.items.length === 0 ? (
            <p className="p-6 text-center text-sm text-slate-600">
              {data.total === 0
                ? "No outstanding resolution SLA breaches."
                : "No SLA alerts on this page."}
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {data.items.map((ticket) => (
                <li key={ticket.id} className="space-y-3 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <Link
                      to={`/tickets/${ticket.ticket_number}`}
                      className="text-sm font-semibold text-blue-700 hover:underline"
                    >
                      <span className="font-mono">{ticket.ticket_number}</span>
                      <span className="ml-2">{ticket.subject}</span>
                    </Link>
                    <div className="flex flex-wrap gap-2">
                      <PriorityBadge priority={ticket.priority} />
                      <StatusBadge status={ticket.status} />
                    </div>
                  </div>
                  <p className="text-xs font-semibold text-red-700">Resolution SLA breached</p>
                  <dl className="grid gap-3 text-sm text-slate-700 sm:grid-cols-3">
                    <div>
                      <dt className="text-xs font-medium text-slate-500">Requester</dt>
                      <dd>{ticket.requester.full_name}</dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium text-slate-500">Assignee and team</dt>
                      <dd>
                        {ticket.assigned_agent?.full_name ?? "Unassigned"}
                        {ticket.support_team_name && ` / ${ticket.support_team_name}`}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium text-slate-500">Resolution due</dt>
                      <dd>{formatDateTime(ticket.resolution_due_at)}</dd>
                    </div>
                  </dl>
                </li>
              ))}
            </ul>
          )}

          {(page > 1 || data.total_pages > 1) && (
            <nav aria-label="SLA alert pages" className="flex items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-4 py-3 text-xs">
              <span className="text-slate-600">Page {data.page}</span>
              <div className="flex gap-2">
                <button type="button" className={pageButtonClass} disabled={page <= 1} onClick={() => setPage(page - 1)}>
                  Previous
                </button>
                <button type="button" className={pageButtonClass} disabled={page >= data.total_pages} onClick={() => setPage(page + 1)}>
                  Next
                </button>
              </div>
            </nav>
          )}
        </section>
      )}
    </div>
  );
};
