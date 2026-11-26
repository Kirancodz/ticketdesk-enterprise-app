output "db_instance_id" {
  description = "RDS PostgreSQL instance identifier"
  value       = aws_db_instance.ticketdesk.id
}

output "db_endpoint" {
  description = "RDS PostgreSQL connection endpoint"
  value       = aws_db_instance.ticketdesk.endpoint
}

output "db_address" {
  description = "RDS PostgreSQL hostname"
  value       = aws_db_instance.ticketdesk.address
}

output "db_port" {
  description = "RDS PostgreSQL port"
  value       = aws_db_instance.ticketdesk.port
}

output "db_subnet_group_name" {
  description = "Private RDS subnet group name"
  value       = aws_db_subnet_group.ticketdesk.name
}

output "master_secret_arn" {
  description = "ARN of the AWS-managed master credential secret"
  value       = aws_db_instance.ticketdesk.master_user_secret[0].secret_arn
}
