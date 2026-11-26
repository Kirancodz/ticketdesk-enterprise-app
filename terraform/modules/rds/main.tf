# Private subnet group for PostgreSQL
resource "aws_db_subnet_group" "ticketdesk" {
  name        = "ticketdesk-${lower(var.environment)}-db-subnets"
  description = "Private database subnets for TicketDesk"

  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "${var.project_name}-${var.environment}-DB-Subnets"
    Tier = "Database"
  }
}

# Private PostgreSQL database
resource "aws_db_instance" "ticketdesk" {
  identifier = "ticketdesk-${lower(var.environment)}-postgres"

  engine         = "postgres"
  engine_version = "16"

  instance_class    = "db.t3.micro"
  allocated_storage = 20
  storage_type      = "gp3"

  db_name  = "ticketdesk"
  username = "ticketdeskadmin"

  # AWS generates and stores the master password in Secrets Manager.
  # No database password is stored in Terraform configuration.
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.ticketdesk.name
  vpc_security_group_ids = [var.rds_security_group_id]

  publicly_accessible = false
  multi_az            = false

  storage_encrypted = true

  # Short retention for the POC
  backup_retention_period = 1

  # Disable unnecessary optional monitoring features for this POC
  performance_insights_enabled = false
  monitoring_interval          = 0

  # POC teardown settings: do not use with production data
  deletion_protection = false
  skip_final_snapshot = true

  auto_minor_version_upgrade = true
  apply_immediately          = true

  tags = {
    Name = "${var.project_name}-${var.environment}-PostgreSQL"
    Tier = "Database"
  }
}
