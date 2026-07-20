output "residency_decided" {
  description = "True once a residency-compliant region is set (FD-02)."
  value       = local.residency_decided
}

output "environment" {
  value = var.environment
}
