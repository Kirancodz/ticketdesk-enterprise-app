# Least-privilege permissions for TicketDesk attachments
data "aws_iam_policy_document" "ec2_s3_attachments" {
  statement {
    sid       = "ListTicketDeskAttachments"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [module.s3.bucket_arn]
  }

  statement {
    sid    = "ManageTicketDeskAttachmentObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ]
    resources = ["${module.s3.bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "ec2_s3_attachments" {
  name   = "ticketdesk-poc-ec2-s3-attachments"
  role   = module.iam.ec2_role_name
  policy = data.aws_iam_policy_document.ec2_s3_attachments.json
}
