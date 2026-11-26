# Allow the TicketDesk EC2 application to retrieve its RDS credential.
# The secret value itself is never read into Terraform state.

data "aws_iam_policy_document" "ec2_rds_secret" {
  statement {
    sid    = "ReadTicketDeskRdsSecret"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]

    resources = [module.rds.master_secret_arn]
  }
}

resource "aws_iam_role_policy" "ec2_rds_secret" {
  name   = "ticketdesk-poc-ec2-rds-secret"
  role   = module.iam.ec2_role_name
  policy = data.aws_iam_policy_document.ec2_rds_secret.json
}
