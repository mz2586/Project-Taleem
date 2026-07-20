# Terraform settings only. Provider + module bodies are added when FD-02 (cloud/residency) resolves.
# This file is intentionally provisioning-free so `terraform validate` on the skeleton stays honest.

terraform {
  required_version = ">= 1.6.0"
  # backend "..." {}          # remote state — region-bound, added with FD-02
  # required_providers {}     # provider pinned with FD-02
}

# Module layout (bodies pending FD-02):
#   module "network"  { source = "./modules/network"  ... }   # VPC, subnets, default-deny SGs (36 §3)
#   module "data"     { source = "./modules/data"     ... }   # sharded Postgres, Redis tiers, broker (54)
#   module "compute"  { source = "./modules/compute"  ... }   # K8s node pools (35 §4)
#   module "security" { source = "./modules/security" ... }   # KMS/HSM, secrets (FD-14, 13 §6)

locals {
  # Guardrail: fail fast if a region is used before the residency decision is made.
  residency_decided = var.region != ""
}
