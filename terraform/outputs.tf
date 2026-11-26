output "vpc_id" {
  description = "TicketDesk VPC ID"
  value       = module.network.vpc_id
}

output "public_subnet_id" {
  description = "Public application subnet ID"
  value       = module.network.public_subnet_id
}

output "private_db_subnet_ids" {
  description = "Private database subnet IDs"
  value       = module.network.private_db_subnet_ids
}

output "internet_gateway_id" {
  description = "Internet Gateway ID"
  value       = module.network.internet_gateway_id
}

output "public_route_table_id" {
  description = "Public route table ID"
  value       = module.network.public_route_table_id
}

output "private_route_table_id" {
  description = "Private database route table ID"
  value       = module.network.private_route_table_id
}

output "app_security_group_id" {
  description = "EC2 application security group ID"
  value       = module.security.app_security_group_id
}

output "rds_security_group_id" {
  description = "RDS security group ID"
  value       = module.security.rds_security_group_id
}

output "ec2_role_arn" {
  description = "EC2 IAM role ARN"
  value       = module.iam.ec2_role_arn
}

output "ec2_instance_profile_name" {
  description = "EC2 instance profile name"
  value       = module.iam.ec2_instance_profile_name
}

output "lambda_role_arn" {
  description = "Lambda execution role ARN"
  value       = module.iam.lambda_role_arn
}

output "attachments_bucket_name" {
  description = "S3 attachment bucket name"
  value       = module.s3.bucket_name
}

output "attachments_bucket_arn" {
  description = "S3 attachment bucket ARN"
  value       = module.s3.bucket_arn
}

output "rds_instance_id" {
  description = "RDS PostgreSQL instance ID"
  value       = module.rds.db_instance_id
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.rds.db_endpoint
}

output "rds_address" {
  description = "RDS PostgreSQL hostname"
  value       = module.rds.db_address
}

output "rds_port" {
  description = "RDS PostgreSQL port"
  value       = module.rds.db_port
}

output "rds_subnet_group_name" {
  description = "Private RDS subnet group"
  value       = module.rds.db_subnet_group_name
}

output "rds_master_secret_arn" {
  description = "AWS-managed RDS master secret ARN"
  value       = module.rds.master_secret_arn
}
