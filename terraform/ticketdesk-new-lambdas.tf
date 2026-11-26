provider "aws" {
  alias  = "lambda_untagged"
  region = var.aws_region
}

locals {
  ticketdesk_new_lambdas = toset([
    "ticketdesk-folder-creator",
    "ticketdesk-discussion-sync",
    "ticketdesk-log-processor"
  ])
}

resource "aws_lambda_function" "ticketdesk_new" {
  provider = aws.lambda_untagged
  for_each = local.ticketdesk_new_lambdas

  function_name = each.value
  description   = "TicketDesk ticket automation - initial infrastructure"

  role    = module.iam.lambda_role_arn
  runtime = "python3.13"
  handler = "handler.lambda_handler"

  filename = each.value == "ticketdesk-folder-creator" ? "${path.module}/ticketdesk-folder-creator.zip" : each.value == "ticketdesk-discussion-sync" ? "${path.module}/ticketdesk-discussion-sync.zip" : each.value == "ticketdesk-log-processor" ? "${path.module}/ticketdesk-log-processor.zip" : "${path.module}/ticketdesk-lambda-bootstrap.zip"

  source_code_hash = each.value == "ticketdesk-folder-creator" ? filebase64sha256("${path.module}/ticketdesk-folder-creator.zip") : each.value == "ticketdesk-discussion-sync" ? filebase64sha256("${path.module}/ticketdesk-discussion-sync.zip") : each.value == "ticketdesk-log-processor" ? filebase64sha256("${path.module}/ticketdesk-log-processor.zip") : filebase64sha256("${path.module}/ticketdesk-lambda-bootstrap.zip")

  timeout     = 15
  memory_size = 128

  dynamic "environment" {
    for_each = [1]

    content {
      variables = {
        TICKETDESK_BUCKET = module.s3.bucket_name
      }
    }
  }
}
