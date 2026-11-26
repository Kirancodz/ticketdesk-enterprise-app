module "network" {
  source = "./modules/network"

  project_name   = var.project_name
  environment    = var.environment
  vpc_cidr       = var.vpc_cidr
  public_az      = var.public_az
  private_db_azs = var.private_db_azs
}

module "security" {
  source = "./modules/security"

  vpc_id            = module.network.vpc_id
  project_name      = var.project_name
  environment       = var.environment
  allowed_http_cidr = "0.0.0.0/0"
}

module "iam" {
  source = "./modules/iam"

  project_name = var.project_name
  environment  = var.environment
}

module "s3" {
  source = "./modules/s3"

  bucket_name  = "ticketdesk-poc-attachments-635476133762-ap-south-1"
  project_name = var.project_name
  environment  = var.environment
}

module "rds" {
  source = "./modules/rds"

  project_name = var.project_name
  environment  = var.environment

  private_subnet_ids    = module.network.private_db_subnet_ids
  rds_security_group_id = module.security.rds_security_group_id
}

module "ec2" {
  source = "./modules/ec2"

  project_name          = "TicketDesk"
  environment           = "POC"
  public_subnet_id      = module.network.public_subnet_id
  app_security_group_id = module.security.app_security_group_id
  instance_profile_name = module.iam.ec2_instance_profile_name
  instance_type         = "t3.small"
}
