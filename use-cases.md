# Hybrid Cloud & On-Device Multi-Agent Use Cases
## Google Cloud Platform & Infrastructure Engineering Runbook

This document defines concrete, production-grade infrastructure engineering use cases designed for a **Hybrid AI Swarm**:
* **Cloud Gemini (Planner & Architect)**: High-level architectural reasoning, Google Cloud best practices, CIS benchmark compliance, security blueprinting, and structured execution plans.
* **On-Device Gemma 4 26B (Worker & Coder)**: On-device implementation on Apple Silicon Metal via LiteRT and Google Antigravity file tools (`create_file`, `edit_file`, `view_file`).
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
│ • Runs Local Tools: create_file, edit_file, view_file                  │
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

### Option A: Cloud Foundation Fabric FAST Landing Zone & Operational Runbook (Small Customer)
*Domain: Enterprise Landing Zones, Infrastructure as Code (IaC) & Cloud Foundation Fabric*

#### Problem Statement
Setting up a secure, production-ready Google Cloud organization from scratch requires weeks of manual effort or complex bespoke Terraform code. Google Cloud's Professional Services Organization (PSO) created **Cloud Foundation Fabric FAST** to accelerate production setups. For small-to-medium customers (SMBs, startups), an off-the-shelf, streamlined landing zone is needed that can be rapidly configured, audited, and handed off with a clear operational runbook, without deploying premature enterprise complexity.

#### Component Architecture Stack
- **Toolkit**: Google Cloud Foundation Fabric FAST (`GoogleCloudPlatform/cloud-foundation-fabric/fast`).
- **Stage 00 (`0-bootstrap`)**: Automation project (`fast-bootstrap`), Terraform state GCS bucket with uniform bucket-level access & versioning, CI/CD service accounts, centralized billing budget alerts, and org-level audit log sink.
- **Stage 01 (`1-resman`)**: Streamlined folder hierarchy (`Platform` and `Workloads`), baseline CIS GCP v3.0 Level 1 Organization Policies (skip default VPC creation, disable external service account keys, enforce uniform bucket access), and group IAM role mappings.
- **Stage 02 (`2-networking`)**: Single Shared VPC network, environment subnets (`prod` and `dev` in primary region `europe-west1`), Cloud NAT & Cloud Router (zero external public IPs on compute instances), Private Google Access, and secure firewall rules.
- **Stage 03 (`3-project-factory`)**: Standardized tenant workload project attached as a service project to the Shared VPC with Workload Identity Federation.
- **Operational Guide (`RUNBOOK.md`)**: Comprehensive Day-0 prerequisites, bootstrap execution, state migration to GCS, sequential stage execution order, and Day-2 operations.

#### Division of Responsibilities
* **Cloud Gemini (Planner & Architect via Antigravity CLI `agy`)**:
  - Requires **zero API keys** (leverages active Antigravity CLI session).
  - Acts as Google Cloud PSO Lead Architect.
  - Designs stage layouts, parameter schemas (`.tfvars`), security guardrails, and runbook table of contents.
* **Local Gemma 4 26B (Worker & Coder on Apple Silicon Metal)**:
  - Generates the complete 4-stage Terraform codebase and `RUNBOOK.md` in `workspaces/fast-landing-zone/`.
  - Executes local tool calls offline with zero cloud billing.
* **Local Gemma 4 26B (Security & Compliance Auditor in Isolated Context)**:
  - Spins up in a fresh session to independently audit the generated HCL and `RUNBOOK.md` against CIS GCP Benchmark v3.0 Level 1.
  - Generates an Audit Report with findings and remediation diffs.
* **Iterative Remediation Loop**:
  - Worker receives audit findings and applies targeted fixes until verification passes.

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

## 🎯 Current Target: Option A — Cloud Foundation Fabric FAST Landing Zone Swarm

We are executing **Option A: Cloud Foundation Fabric FAST Landing Zone & Operational Runbook (Small Customer)**.

### Pipeline Stages
1. **Input Task**: User requests an off-the-shelf, production-grade Fabric FAST landing zone for a small customer (Acme Corp, `acme-corp.com`, prefix `fast`, region `europe-west1`).
2. **Stage 1 (Cloud Gemini Planner via Antigravity CLI `agy`)**:
   - Zero API keys required (authenticated via active Antigravity CLI session).
   - Generates the 4-stage FAST blueprint and RUNBOOK.md table of contents.
3. **Stage 2 (Local Gemma 4 Worker)**:
   - Uses LiteRT Metal inference (`gemma-4-26B-A4B-it-gpu.litertlm`).
   - Scaffolds `./workspaces/fast-landing-zone/` with `0-bootstrap`, `1-resman`, `2-networking`, `3-project-factory`, and `RUNBOOK.md`.
4. **Stage 3 (Local Gemma 4 Security Auditor in Isolated Context)**:
   - Independent audit of all files against CIS GCP Benchmark v3.0 Level 1.
   - Emits an Audit Findings Report with `[PASS]` or `[REVISION NEEDED]`.
5. **Stage 4 (Remediation Iteration Loop)**:
   - Worker applies any requested fixes using `edit_file` / `create_file`.
6. **Stage 5 (Automated CLI Verification)**:
   - Runs `terraform validate` across all generated stages and outputs summary.
