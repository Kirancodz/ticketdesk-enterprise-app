resource "aws_iam_role_policy" "ticketdesk_ec2_invoke_folder_creator" {
  name = "ticketdesk-poc-ec2-invoke-folder-creator"

  role = split("/", module.iam.ec2_role_arn)[1]

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Sid    = "InvokeTicketFolderCreator"
        Effect = "Allow"

        Action = [
          "lambda:InvokeFunction"
        ]

        Resource = aws_lambda_function.ticketdesk_new["ticketdesk-folder-creator"].arn
      }
    ]
  })
}
