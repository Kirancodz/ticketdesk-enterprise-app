output "bucket_name" {
  description = "TicketDesk attachment bucket name"
  value       = aws_s3_bucket.attachments.id
}

output "bucket_arn" {
  description = "TicketDesk attachment bucket ARN"
  value       = aws_s3_bucket.attachments.arn
}
