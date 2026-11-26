variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "public_subnet_id" {
  description = "Subnet for the EC2 application server"
  type        = string
}

variable "app_security_group_id" {
  description = "Security group for the application server"
  type        = string
}

variable "instance_profile_name" {
  description = "IAM instance profile attached to EC2"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"
}
