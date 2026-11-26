variable "project_name" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
}

variable "public_az" {
  description = "Availability Zone for public subnet"
  type        = string
}

variable "private_db_azs" {
  description = "Availability Zones for private database subnets"
  type        = list(string)
}
