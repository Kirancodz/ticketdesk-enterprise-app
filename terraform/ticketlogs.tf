# Provider without automatic S3 object tags
provider "aws" {
  alias  = "untagged_ticketlogs"
  region = var.aws_region
}

# Create TicketLogs/Tickets/ in existing S3 bucket
resource "aws_s3_object" "ticketlogs_tickets_prefix" {
  provider = aws.untagged_ticketlogs

  bucket  = module.s3.bucket_name
  key     = "TicketLogs/Tickets/"
  content = ""
}
