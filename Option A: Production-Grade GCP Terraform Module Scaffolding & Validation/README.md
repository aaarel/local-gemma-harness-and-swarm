# Option A: Production-Grade GCP Terraform Module Scaffolding & Validation
## Cloud Foundation Fabric FAST Landing Zone Swarm

This folder contains the dedicated implementation, execution scripts, and documentation for **Option A**: an off-the-shelf, production-grade **Google Cloud Foundation Fabric FAST** landing zone and Terraform module generator powered by a hybrid multi-agent swarm.

---

## 🏛️ Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                        USER INFRASTRUCTURE TASK                        │
│   "Plan & scaffold an off-the-shelf Fabric FAST landing zone for SMB"  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   STAGE 1: CLOUD GEMINI (Planner)                      │
│ • Model: Cloud Gemini via Antigravity CLI (agy)                        │
│ • Authentication: Zero API keys needed (active agy session)            │
│ • Emits: Structured 4-stage FAST Blueprint & RUNBOOK.md specifications │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Execution Blueprint
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  STAGE 2: ON-DEVICE GEMMA 4 (Worker)                   │
│ • Model: Gemma 4 26B A4B on Apple Silicon Metal via LiteRT             │
│ • Offline Tools: write_to_file, replace_file_content, run_command      │
│ • Scaffolds: 0-bootstrap, 1-resman, 2-networking, 3-project-factory    │
│ • Authors: RUNBOOK.md with full Day-0 to Day-2 operational steps       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Generated Code & Runbook
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│          STAGE 3: ON-DEVICE GEMMA 4 (Security Auditor)                 │
│ • Execution: Fresh, isolated context (Zero drafting bias)              │
│ • Audits against: CIS GCP Benchmark v3.0 Level 1 & Fabric Best Practice│
│ • Emits: Audit Report with [PASS] or [REVISION NEEDED]                 │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Audit Findings
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│              STAGE 4: REMEDIATION LOOP & CLI VERIFICATION              │
│ • Worker automatically patches code if findings are reported           │
│ • Runs: terraform -chdir=<stage> init -backend=false && validate       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Folder Contents

| File | Purpose |
| :--- | :--- |
| **`run_fast_swarm.py`** | Dedicated CLI runner for generating the Cloud Foundation Fabric FAST landing zone (4 stages + `RUNBOOK.md`). |
| **`run_hybrid.py`** | Specialized runner for scaffolding a Private Cloud Run v2 + Private Cloud SQL module. |
| **`README.md`** | This runbook and architecture specification. |

---

## 🚀 How to Run

### 1. Run the Cloud Foundation Fabric FAST Swarm
From this folder or the repository root:
```bash
# Using Antigravity CLI (zero API keys needed)
.venv/bin/python "Option A: Production-Grade GCP Terraform Module Scaffolding & Validation/run_fast_swarm.py"

# Or if you are inside this directory:
cd "Option A: Production-Grade GCP Terraform Module Scaffolding & Validation"
../../.venv/bin/python run_fast_swarm.py
```

### 2. Run the Private Cloud Run & Cloud SQL Swarm
```bash
.venv/bin/python "Option A: Production-Grade GCP Terraform Module Scaffolding & Validation/run_hybrid.py"
```

---

## 📦 Deliverables Produced

Generated infrastructure files and operational documentation are output to `workspaces/fast-landing-zone/`:

```text
workspaces/fast-landing-zone/
├── RUNBOOK.md                       # Complete operational deployment runbook
├── 0-bootstrap/
│   ├── main.tf                      # Automation project, state bucket, CI/CD SAs
│   ├── variables.tf                 # org_id, billing_account, prefix
│   ├── outputs.tf                   # bucket name, SA emails, project_id
│   └── terraform.tfvars.example     # Customer inputs template
├── 1-resman/
│   ├── main.tf                      # Folders (Platform/Workloads), Org Policies, group IAM
│   ├── variables.tf
│   ├── outputs.tf                   # folder IDs, org policy status
│   └── terraform.tfvars.example
├── 2-networking/
│   ├── main.tf                      # Shared VPC, subnets (prod/dev), Cloud NAT, firewalls
│   ├── variables.tf
│   ├── outputs.tf                   # vpc_self_link, subnet_ids
│   └── terraform.tfvars.example
└── 3-project-factory/
    ├── main.tf                      # Workload tenant project & Shared VPC attachment
    ├── variables.tf
    ├── outputs.tf
    └── terraform.tfvars.example
```

---

## 🛡️ Security & Compliance Standards Enforced

1. **CIS GCP Foundations Benchmark v3.0 (Level 1)**:
   - `compute.skipDefaultNetworkCreation = true` (Default network deleted/disabled).
   - `iam.disableServiceAccountKeyCreation = true` (External SA key downloads blocked).
   - `storage.uniformBucketLevelAccess = true` (Strict uniform ACLs on all GCS buckets).
2. **Network Perimeter**:
   - Zero external public IPv4 addresses on compute instances.
   - Cloud NAT provides outbound internet access.
   - Private Google Access enabled on all subnets.
3. **Identity & State**:
   - Dedicated Terraform state bucket with object versioning.
   - Workload Identity Federation enabled for tenant projects.
