resource "aws_security_group" "app" {
  name        = "${var.project_name}-${var.environment}-EC2-SG"
  description = "Security group for TicketDesk application server"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP access to TicketDesk application"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = [var.allowed_http_cidr]
  }

  egress {
    description = "Outbound application traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-EC2-SG"
    Tier = "Application"
  }
}

resource "aws_security_group" "rds" {
  name        = "${var.project_name}-${var.environment}-RDS-SG"
  description = "Security group for private TicketDesk PostgreSQL database"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL access only from TicketDesk application server"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-RDS-SG"
    Tier = "Database"
  }
}
