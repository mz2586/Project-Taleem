# Infrastructure as Code (Terraform) — skeleton

**Status: structure only.** The concrete cloud provider and region are a **Phase-1.5 founder decision**
([FOUNDER_DECISIONS.md](../../FOUNDER_DECISIONS.md) FD-02, coupled to data residency FD-03). No provider
block is committed until that decision lands — so this scaffold is provider-agnostic and does **not**
provision anything yet.

What is here (governance-safe):

- `variables.tf` — the inputs every environment needs (region, environment name, sizing), so the moment
  FD-02 resolves, only the provider block + module bodies are filled in.
- `main.tf` — the `terraform` settings block + module layout stubs (network, data, compute) with `null`
  placeholders.
- `outputs.tf` — the outputs downstream tooling will consume.

When FD-02 lands: add the provider block, remote state backend (region-bound), and the module bodies per
[36 Infrastructure](../../docs/02-architecture/36-infrastructure-architecture.md) and
[54 Capacity](../../docs/02-architecture/54-capacity-and-scale-model.md) (sharded Postgres, Redis split by
workload, broker, CDN, KMS/HSM per FD-14). Everything is Terraform-managed; no click-ops (04-NFR MNT-04).
