resource "aws_vpc" "ticketdesk" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.project_name}-${var.environment}-VPC"
  }
}

resource "aws_internet_gateway" "ticketdesk" {
  vpc_id = aws_vpc.ticketdesk.id

  tags = {
    Name = "${var.project_name}-${var.environment}-IGW"
  }
}

resource "aws_subnet" "public_app" {
  vpc_id                  = aws_vpc.ticketdesk.id
  cidr_block              = "10.30.1.0/24"
  availability_zone       = var.public_az
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-Public-App-Subnet"
    Tier = "Public"
  }
}

resource "aws_subnet" "private_db" {
  count = length(var.private_db_azs)

  vpc_id            = aws_vpc.ticketdesk.id
  cidr_block        = "10.30.${11 + count.index}.0/24"
  availability_zone = var.private_db_azs[count.index]

  tags = {
    Name = "${var.project_name}-Private-DB-Subnet-${count.index + 1}"
    Tier = "Private"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.ticketdesk.id

  tags = {
    Name = "${var.project_name}-Public-Route-Table"
  }
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.ticketdesk.id
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public_app.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private_db" {
  vpc_id = aws_vpc.ticketdesk.id

  tags = {
    Name = "${var.project_name}-Private-DB-Route-Table"
  }
}

resource "aws_route_table_association" "private_db" {
  count = length(aws_subnet.private_db)

  subnet_id      = aws_subnet.private_db[count.index].id
  route_table_id = aws_route_table.private_db.id
}
