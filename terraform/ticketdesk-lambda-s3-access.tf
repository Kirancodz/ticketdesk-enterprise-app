resource "aws_iam_role_policy" "ticketdesk_lambda_ticketlogs" {
  name = "ticketdesk-poc-lambda-ticketlogs-access"
  role = split("/", module.iam.lambda_role_arn)[1]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ListTicketLogs"
        Effect = "Allow"
        Action = ["s3:ListBucket"]

        Resource = module.s3.bucket_arn

        Condition = {
          StringLike = {
            "s3:prefix" = [
              "TicketLogs/Tickets/",
              "TicketLogs/Tickets/*"
            ]
          }
        }
      },
      {
        Sid    = "ReadWriteTicketLogs"
        Effect = "Allow"

        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]

        Resource = "${module.s3.bucket_arn}/TicketLogs/Tickets/*"
      }
    ]
  })
}
