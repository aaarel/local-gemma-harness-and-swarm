# Hybrid Cloud & On-Device Multi-Agent Use Cases
## Google Cloud Platform & Infrastructure Engineering Runbook

This document defines concrete, production-grade infrastructure engineering use cases designed for a **Hybrid AI Swarm**:
* **Cloud Gemini (Planner & Architect)**: High-level architectural reasoning, Google Cloud best practices, CIS benchmark compliance, security blueprinting, and structured execution plans.
* **On-Device Gemma 4 26B (Worker & Coder)**: 100% offline local implementation on Apple Silicon Metal via LiteRT and Google Antigravity tools (`write_to_file`, `replace_file_content`, `run_command`, `view_file`).
* **Future On-Device 3B Model (Linter & Validator)**: Fast local syntax verification, schema validation, and parameter sanity checking.

---

## 🏛 Architecture Pattern: Why Hybrid Infra Orchestration?

```
┌────────────────────────────────────────────────────────────────────────┐
│                        USER INFRASTRUCTURE TASK                        │
│             "Build a private Cloud Run + Cloud SQL module"             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   STAGE 1: CLOUD GEMINI (Planner)                      │
│ • Model: gemini-2.5-pro / gemini-2.5-flash                             │
│ • Ingests: Abstract objective & file signatures (Zero sensitive data)  │
│ • Emits: Structured Execution Blueprint (HCL schema, IAM bindings,    │
│          security guardrails, verification criteria)                   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Structured Plan
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  STAGE 2: ON-DEVICE GEMMA 4 (Worker)                   │
│ • Model: Gemma 4 26B A4B on Apple Silicon Metal via LiteRT             │
│ • Local Agent: Reads local workspace files, writes HCL code,           │
│   refactors modules, applies targeted diffs                            │
│ • Runs Local Tools: write_to_file, replace_file_content, run_command   │
│ • Zero Cloud Cost: Generates hundreds of lines of code locally         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Generated Code & Diffs
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               STAGE 3: VERIFIER & VALIDATOR (Local / 3B)               │
│ • Runs local CLI verification: terraform validate, tflint, kubeconform │
│ • Validates syntax, parameter constraints, and security policies       │
└────────────────────────────────────────────────────────────────────────┘
```

### Key Value Drivers for Infra Engineering:
1. **Zero Data Leakage**: Sensitive infrastructure state files, project IDs, VPC CIDRs, and credentials never leave the engineer's workstation.
2. **Infinite Token Budget for Iteration**: Code authoring and repetitive linter fixing happen locally at ~30 tokens/sec with $0 API cost.
3. **Top-Tier Architecture**: Gemini provides cutting-edge knowledge of GCP features, provider updates (`hashicorp/google ~> 6.0`), and security standards.

---

## 📋 Evaluated Use Cases

### Option A: Production-Grade GCP Terraform Module Scaffolding & Validation
*Domain: Infrastructure as Code (IaC) & Cloud Security Architecture*

#### Problem Statement
Engineering teams often create ad-hoc Terraform configurations that violate cloud security benchmarks: exposing Cloud SQL on public IPs, using primitive IAM roles (`roles/editor`), hardcoding secrets in environment variables, or omitting Serverless VPC Access connectors. Writing production-grade, modular Terraform that adheres to CIS GCP Benchmarks requires significant boilerplate across multiple files (`main.tf`, `variables.tf`, `outputs.tf`, `iam.tf`, `versions.tf`).

#### Component Architecture Stack
- **Compute**: Google Cloud Run v2 service with Direct VPC Egress or Serverless VPC Access Connector.
- **Database**: Cloud SQL PostgreSQL instance configured exclusively with Private IP (RFC 1918) within a VPC Peering / Service Networking connection and Cloud SQL IAM Database Authentication.
- **Security & IAM**: Dedicated least-privilege service accounts (no primitive roles), Secret Manager accessor bindings, and CMEK encryption stubs.
- **Networking**: VPC subnet, Serverless connector / Direct Egress, Private Service Access (Service Networking).

#### Division of Responsibilities
* **Cloud Gemini (Planner)**:
  - Formulates the exact module layout and dependency graph.
  - Dictates provider constraints (`hashicorp/google ~> 6.0`, `google-beta`).
  - Defines the variable interface with strict types, descriptions, and validation blocks.
  - Enforces CIS GCP Benchmark guardrails (e.g. `ipv4_enabled = false`, `require_ssl = true`, `deletion_protection = true`).
  - Emits an actionable, step-by-step implementation plan for the local coder.
* **Local Gemma 4 (Worker)**:
  - Scaffolds the modular file tree using `write_to_file`.
  - Implements the complete HCL resource blocks according to the plan.
  - Executes local verification commands (`terraform init -backend=false`, `terraform validate`, `tflint`).
  - Iteratively fixes any syntax or schema mismatches until 100% clean.
* **Future 3B Local Agent**:
  - Performs quick HCL syntax linting and ensures all declared variables have descriptions and types.

---

### Option B: Kubernetes / GKE Production Hardening & Kustomize Migration
*Domain: Container Platform Engineering & GKE Security*

#### Problem Statement
Development services often run in local Docker Compose or raw Kubernetes deployment YAMLs without production guardrails. Deploying these directly to Google Kubernetes Engine (GKE) leads to security risks, resource starvation, and downtime during node pool upgrades.

#### Component Architecture Stack
- **Target Platform**: GKE Autopilot / Standard with GKE Workload Identity Federation.
- **Security Standards**: Pod Security Standards (`restricted` / `baseline`), non-root user enforcement, read-only root filesystems, drop `ALL` Linux capabilities.
- **Availability & Scaling**: Horizontal Pod Autoscaler (`autoscaling/v2`), PodDisruptionBudgets (`policy/v1`), structured readiness/liveness/startup probes, and explicit CPU/memory requests and limits.
- **Traffic Control**: GKE NetworkPolicy ingress and egress rules restricting pod-to-pod communication.

#### Division of Responsibilities
* **Cloud Gemini (Planner)**:
  - Ingests the raw Docker Compose or basic deployment manifest.
  - Translates docker environment variables into Secret / ConfigMap architectures with Workload Identity GCP IAM mappings.
  - Designs the Kustomize overlay structure (`base/`, `overlays/dev/`, `overlays/prod/`).
  - Specifies exact NetworkPolicy CIDR and label selectors.
* **Local Gemma 4 (Worker)**:
  - Generates the complete K8s resource manifests and `kustomization.yaml` files locally.
  - Executes validation tools locally using `run_command` (`kustomize build overlays/prod/`, `kubeconform -strict -kubernetes-version 1.30.0`).
  - Verifies zero schema errors and correct indentation.
* **Future 3B Local Agent**:
  - Runs YAML syntax checks and checks for missing label selectors.

---

### Option C: Automated GCP FinOps & Resource Right-Sizing Remediation
*Domain: Cloud Financial Operations (FinOps) & Cost Optimization*

#### Problem Statement
Enterprise GCP bills accumulate substantial waste: unattached Persistent Disks, over-provisioned Compute Engine VM instances running at <5% CPU, Cloud Storage buckets storing petabytes without Object Lifecycle Management (standard storage instead of Nearline/Coldline/Archive), and Cloud Run services running with excessive minimum instances or memory allocations.

#### Component Architecture Stack
- **Input Data**: Simulated GCP Cloud Billing / Cloud Asset Inventory / Recommender API JSON report.
- **Remediation Targets**: Compute Engine VM family modernization (`n1`/`e2` to `c3d` or spot), GCS Object Lifecycle Management rules (abort incomplete multipart uploads, transition to Coldline after 30 days, delete after 365 days), and Cloud Run concurrency tuning.

#### Division of Responsibilities
* **Cloud Gemini (Planner)**:
  - Ingests the utilization metrics report.
  - Applies cost optimization logic and GCP pricing heuristics to project monthly dollar savings.
  - Formulates a prioritised remediation blueprint ranked by ROI and operational risk.
* **Local Gemma 4 (Worker)**:
  - Reads existing Terraform files or local automation scripts.
  - Writes remediation automation scripts (e.g. Python script utilizing `google-cloud-storage` and `google-cloud-compute` client libraries, or patches existing Terraform modules).
  - Executes dry-run tests against mock GCP APIs locally.
* **Future 3B Local Agent**:
  - Parses CSV/JSON output tables and validates that calculated savings numbers match defined formulas.

---

### Option D: SRE Incident Triage & Automated Runbook Generator
*Domain: Site Reliability Engineering (SRE) & Incident Automation*

#### Problem Statement
During a production incident on GCP, on-call engineers must rapidly parse disparate error logs across Cloud Logging, Cloud Trace, and Error Reporting, formulate an emergency mitigation, and author post-incident runbooks to automate recovery in future occurrences.

#### Component Architecture Stack
- **Input Data**: Multi-service log dump from Cloud Logging (HTTP 503s, database connection pool saturation, Cloud SQL authorization failures, container OOMKilled events).
- **Output Artifacts**: Post-Mortem Root Cause Analysis (RCA), executable automated diagnosis/mitigation script, and Cloud Monitoring Alerting Policy definitions (Terraform / YAML).

#### Division of Responsibilities
* **Cloud Gemini (Planner)**:
  - Correlates distributed log timestamps and traces across services.
  - Pinpoints the root cause (e.g. max connections reached on Cloud SQL replica due to improper connection pooling in Cloud Run).
  - Authors an SRE Incident Post-Mortem and mitigation strategy.
* **Local Gemma 4 (Worker)**:
  - Writes an executable Python/Bash SRE runbook script with exponential backoff and error handling to test connection pools and restart crashed services safely.
  - Generates Terraform configurations for Cloud Monitoring alert policies and dashboards.
  - Runs local unit tests verifying the runbook logic.
* **Future 3B Local Agent**:
  - Validates bash/python script syntax and regex patterns.

---

## 🎯 Current Target: Option A Implementation Plan

We are executing **Option A: Production-Grade GCP Terraform Module Scaffolding & Validation**.

### Pipeline Stages
1. **Input Task**: User requests a secure, modular GCP Terraform module (e.g., Private Cloud Run v2 + Cloud SQL PostgreSQL with Private IP + Secret Manager + Least-Privilege IAM).
2. **Stage 1 (Cloud Gemini Planner)**:
   - Uses `google-genai` SDK with `gemini-2.5-flash` or `gemini-2.5-pro`.
   - Sends the task specification and receives a structured, step-by-step implementation blueprint.
3. **Stage 2 (Local Gemma 4 Worker)**:
   - Uses LiteRT Metal inference (`gemma-4-26B-A4B-it-gpu.litertlm`).
   - Scaffolds module directory in `./workspace/terraform-gcp-secure-cloudrun/`.
   - Writes `versions.tf`, `variables.tf`, `main.tf`, `iam.tf`, `outputs.tf`, and an `example/main.tf`.
   - Executes `terraform init -backend=false` and `terraform validate` locally.
4. **Stage 3 (Reviewer / Verifier)**:
   - Verifies all files against the plan, checks `terraform validate` exit code, and reports final summary.
