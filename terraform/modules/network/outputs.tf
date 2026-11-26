output "vpc_id" {
  description = "TicketDesk VPC ID"
  value       = aws_vpc.ticketdesk.id
}

output "public_subnet_id" {
  description = "Public application subnet ID"
  value       = aws_subnet.public_app.id
}

output "private_db_subnet_ids" {
  description = "Private database subnet IDs"
  value       = aws_subnet.private_db[*].id
}

output "internet_gateway_id" {
  description = "Internet Gateway ID"
  value       = aws_internet_gateway.ticketdesk.id
}

output "public_route_table_id" {
  description = "Public route table ID"
  value       = aws_route_table.public.id
}

output "private_route_table_id" {
  description = "Private database route table ID"
  value       = aws_route_table.private_db.id
}
