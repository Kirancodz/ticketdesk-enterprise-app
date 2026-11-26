output "app_security_group_id" {
  description = "TicketDesk EC2 application security group ID"
  value       = aws_security_group.app.id
}

output "rds_security_group_id" {
  description = "TicketDesk RDS security group ID"
  value       = aws_security_group.rds.id
}
