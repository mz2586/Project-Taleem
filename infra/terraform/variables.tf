# Provider-agnostic inputs. Provider + region bound once FOUNDER_DECISIONS FD-02 resolves.

variable "environment" {
  description = "Deployment environment (staging|production)."
  type        = string
  default     = "staging"
}

variable "region" {
  description = "Cloud region. MUST satisfy the data-residency decision (FD-02/FD-03)."
  type        = string
  default     = "" # intentionally empty until FD-02
}

variable "core_api_replicas" {
  description = "Baseline Core API replica count (see 54-capacity-and-scale-model §3)."
  type        = number
  default     = 3
}

variable "postgres_shard_count" {
  description = "Number of Postgres shards for high-volume contexts (54 §4)."
  type        = number
  default     = 8
}
