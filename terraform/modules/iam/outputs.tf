output "ec2_role_arn" {
  description = "TicketDesk EC2 IAM role ARN"
  value       = aws_iam_role.ec2.arn
}

output "ec2_role_name" {
  description = "TicketDesk EC2 IAM role name"
  value       = aws_iam_role.ec2.name
}

output "ec2_instance_profile_name" {
  description = "TicketDesk EC2 instance profile"
  value       = aws_iam_instance_profile.ec2.name
}

output "lambda_role_arn" {
  description = "TicketDesk Lambda execution role ARN"
  value       = aws_iam_role.lambda.arn
}
