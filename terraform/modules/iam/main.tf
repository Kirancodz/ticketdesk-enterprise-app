# EC2 trust policy
data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

# EC2 application role
resource "aws_iam_role" "ec2" {
  name               = "ticketdesk-${lower(var.environment)}-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json

  tags = {
    Name = "${var.project_name}-${var.environment}-EC2-Role"
  }
}

# EC2 instance profile
resource "aws_iam_instance_profile" "ec2" {
  name = "ticketdesk-${lower(var.environment)}-ec2-profile"
  role = aws_iam_role.ec2.name
}

# Systems Manager access for EC2 administration
resource "aws_iam_role_policy_attachment" "ec2_ssm" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Lambda trust policy
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# Lambda execution role
resource "aws_iam_role" "lambda" {
  name               = "ticketdesk-${lower(var.environment)}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = {
    Name = "${var.project_name}-${var.environment}-Lambda-Role"
  }
}

# CloudWatch logging permissions for Lambda
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
