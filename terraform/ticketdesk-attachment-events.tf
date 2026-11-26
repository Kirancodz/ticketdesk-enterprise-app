data "aws_lambda_function" "ticketdesk_file_processor" {
  provider      = aws.lambda_untagged
  function_name = "ticketdesk-file-processor"
}

resource "aws_cloudwatch_event_rule" "ticketdesk_attachment_created" {
  provider    = aws.lambda_untagged
  name        = "ticketdesk-attachment-created"
  description = "Process new TicketDesk attachments"

  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created"]

    detail = {
      bucket = {
        name = [module.s3.bucket_name]
      }

      object = {
        key = [
          {
            wildcard = "TicketLogs/Tickets/*/Attachments/*"
          }
        ]
      }
    }
  })
}

resource "aws_lambda_permission" "ticketdesk_file_processor_eventbridge" {
  provider      = aws.lambda_untagged
  statement_id  = "AllowTicketDeskAttachmentEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = data.aws_lambda_function.ticketdesk_file_processor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ticketdesk_attachment_created.arn
}

resource "aws_cloudwatch_event_target" "ticketdesk_attachment_processor" {
  provider  = aws.lambda_untagged
  rule      = aws_cloudwatch_event_rule.ticketdesk_attachment_created.name
  target_id = "TicketDeskFileProcessor"
  arn       = data.aws_lambda_function.ticketdesk_file_processor.arn

  depends_on = [
    aws_lambda_permission.ticketdesk_file_processor_eventbridge
  ]
}

resource "aws_s3_bucket_notification" "ticketdesk_eventbridge" {
  provider    = aws.lambda_untagged
  bucket      = module.s3.bucket_name
  eventbridge = true

  depends_on = [
    aws_cloudwatch_event_target.ticketdesk_attachment_processor
  ]
}

