export type RoleType = "employee" | "agent" | "admin";

export type TicketPriority = "critical" | "high" | "medium" | "low";

export type TicketStatus =
  | "open"
  | "assigned"
  | "in_progress"
  | "pending"
  | "resolved"
  | "closed"
  | "transferred";

export interface UserRoleInfo {
  id: number;
  name: RoleType;
  display_name: string;
}

export interface DepartmentInfo {
  id: number;
  name: string;
  code: string;
  location?: string | null;
}

export interface SupportTeamInfo {
  id: number;
  name: string;
  code: string;
  specialization?: string | null;
}

export interface AuthUser {
  id: number;
  email: string;
  full_name: string;
  employee_id?: string | null;
  job_title?: string | null;
  phone?: string | null;
  is_active: boolean;
  must_change_password: boolean;
  role: RoleType;
  role_info?: UserRoleInfo | null;
  department?: DepartmentInfo | null;
  support_team?: SupportTeamInfo | null;
  last_login_at?: string | null;
  created_at: string;
}

export interface UserSummary {
  id: number;
  email: string;
  full_name: string;
  employee_id?: string | null;
  job_title?: string | null;
  role: RoleType;
  department_name?: string | null;
  support_team_name?: string | null;
  support_team_id?: number | null;
}

export interface UserDetail extends AuthUser {
  role_id: number;
  department_id?: number | null;
  support_team_id?: number | null;
  updated_at: string;
}

export interface CategoryItem {
  id: number;
  name: string;
  slug: string;
  description?: string | null;
  subcategories: string[];
  icon?: string | null;
  is_active: boolean;
}

export interface SLAPolicyItem {
  id: number;
  name: string;
  priority: TicketPriority;
  response_target_minutes: number;
  resolution_target_minutes: number;
  business_hours_only: boolean;
  description?: string | null;
  is_active: boolean;
  updated_at: string;
}

export interface SLAStatusInfo {
  policy_name: string;
  response_target_minutes: number;
  resolution_target_minutes: number;
  first_response_due_at?: string | null;
  first_responded_at?: string | null;
  resolution_due_at?: string | null;
  resolved_at?: string | null;
  response_breached: boolean;
  resolution_breached: boolean;
  is_overdue: boolean;
  remaining_minutes?: number | null;
  sla_health: "within_sla" | "at_risk" | "breached" | "met" | "closed";
}

export interface TicketListItem {
  id: number;
  ticket_number: string;
  subject: string;
  category_id: number;
  category_name: string;
  subcategory?: string | null;
  priority: TicketPriority;
  status: TicketStatus;
  closed_at?: string | null;
  transferred_at?: string | null;
  transfer_outcome?: string | null;
  routed_by?: UserSummary | null;
  previous_ticket_number?: string | null;
  requester: UserSummary;
  assigned_agent?: UserSummary | null;
  department_name?: string | null;
  support_team_name?: string | null;
  affected_service?: string | null;
  resolution_due_at?: string | null;
  is_overdue: boolean;
  sla_health: "within_sla" | "at_risk" | "breached" | "met" | "closed";
  comment_count: number;
  attachment_count: number;
  created_at: string;
  updated_at: string;
}

export interface TicketCommentItem {
  id: number;
  ticket_id: number;
  author_id: number;
  author: UserSummary;
  body: string;
  is_internal: boolean;
  created_at: string;
  updated_at: string;
}

export interface TicketAttachmentItem {
  id: number;
  ticket_id: number;
  uploaded_by_id: number;
  uploaded_by_name: string;
  original_filename: string;
  content_type: string;
  file_size: number;
  storage_provider: string;
  created_at: string;
}

export interface TicketHistoryItem {
  id: number;
  ticket_id: number;
  actor_id?: number | null;
  actor_name: string;
  actor_role?: string | null;
  action: string;
  field_name?: string | null;
  old_value?: string | null;
  new_value?: string | null;
  description: string;
  created_at: string;
}

export interface TicketDetail extends TicketListItem {
  description: string;
  department_id?: number | null;
  support_team_id?: number | null;
  reopened_count: number;
  sla: SLAStatusInfo;
  comments: TicketCommentItem[];
  attachments: TicketAttachmentItem[];
  history: TicketHistoryItem[];
  team_received_at?: string | null;
  work_started_at?: string | null;
  original_submitted_at?: string | null;
  can_accept?: boolean;
  can_manage?: boolean;
  can_chat?: boolean;
  lineage?: { id: number; ticket_number: string; status: TicketStatus; support_team_name?: string; relation: string; can_open: boolean }[];
}

export interface PaginatedTickets {
  items: TicketListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface DashboardSummary {
  total_tickets: number;
  open_tickets: number;
  assigned_tickets: number;
  in_progress_tickets: number;
  pending_tickets: number;
  resolved_tickets: number;
  closed_tickets: number;
  transferred_tickets?: number;
  overdue_tickets: number;
  sla_alerts_today?: number;
  avg_resolution_hours: number;
  sla_compliance_percentage: number;
  my_assigned_count: number;
  unassigned_queue_count: number;
}

export interface TrendPoint {
  label: string;
  date: string;
  created: number;
  resolved: number;
}

export interface DashboardTrends {
  daily: TrendPoint[];
  weekly: TrendPoint[];
  monthly: TrendPoint[];
}

export interface DistributionItem {
  name: string;
  key: string;
  value: number;
  percentage: number;
}

export interface AgentPerformanceItem {
  agent_id: number;
  agent_name: string;
  email: string;
  support_team: string;
  assigned_total: number;
  resolved_count: number;
  pending_workload: number;
  sla_compliance_rate: number;
  avg_resolution_hours: number;
}

export interface DashboardDistribution {
  by_status: DistributionItem[];
  by_priority: DistributionItem[];
  by_category: DistributionItem[];
  recent_tickets: TicketListItem[];
  agent_performance: AgentPerformanceItem[];
}

export interface NotificationItem {
  id: number;
  user_id: number;
  ticket_id?: number | null;
  ticket_number?: string | null;
  title: string;
  message: string;
  notification_type: string;
  is_read: boolean;
  read_at?: string | null;
  created_at: string;
}

export interface NotificationList {
  items: NotificationItem[];
  unread_count: number;
  total: number;
}

export interface KnowledgeArticleItem {
  id: number;
  title: string;
  slug: string;
  summary: string;
  content: string;
  category_id?: number | null;
  category_name?: string | null;
  author_id: number;
  author_name: string;
  tags: string[];
  is_published: boolean;
  view_count: number;
  helpful_count: number;
  created_at: string;
  updated_at: string;
}

export interface AuditLogItem {
  id: number;
  user_id?: number | null;
  user_name: string;
  user_email?: string | null;
  user_role?: string | null;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  ip_address?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface PaginatedAuditLogs {
  items: AuditLogItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface SystemSettingItem {
  id: number;
  key: string;
  value: string;
  category: string;
  description?: string | null;
  updated_by_name?: string | null;
  updated_at: string;
}
