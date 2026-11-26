variable "aws_region" {
  description = "AWS deployment region"
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  description = "Project name used for resource tagging"
  type        = string
  default     = "TicketDesk"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "POC"
}

variable "vpc_cidr" {
  description = "CIDR block for the TicketDesk VPC"
  type        = string
  default     = "10.30.0.0/16"
}

variable "public_az" {
  description = "Availability Zone for the public application subnet"
  type        = string
  default     = "ap-south-1a"
}

variable "private_db_azs" {
  description = "Availability Zones for private database subnets"
  type        = list(string)
  default     = ["ap-south-1b", "ap-south-1c"]

  validation {
    condition     = length(var.private_db_azs) >= 2
    error_message = "At least two Availability Zones are required for the database subnets."
  }
}
