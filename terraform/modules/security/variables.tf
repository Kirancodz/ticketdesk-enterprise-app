variable "vpc_id" {
  description = "TicketDesk VPC ID"
  type        = string
}

variable "project_name" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "allowed_http_cidr" {
  description = "Source CIDR allowed to access the web application"
  type        = string
  default     = "0.0.0.0/0"
}
