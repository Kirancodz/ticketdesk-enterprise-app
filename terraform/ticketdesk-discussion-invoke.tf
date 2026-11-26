resource "aws_iam_role_policy" "ticketdesk_ec2_invoke_discussion_sync" {
  name = "ticketdesk-ec2-invoke-discussion-sync"
  role = "ticketdesk-poc-ec2-role"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = "arn:aws:lambda:ap-south-1:635476133762:function:ticketdesk-discussion-sync"
      }
    ]
  })
}
