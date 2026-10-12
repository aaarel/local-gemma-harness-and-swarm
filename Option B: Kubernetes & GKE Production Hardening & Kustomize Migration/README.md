# Option B: Kubernetes & GKE Production Hardening & Kustomize Migration
## Production GKE Hardening, NetworkPolicies & Kustomize Multi-Tier Overlays

This folder contains the dedicated implementation, execution scripts, sample input workloads, and documentation for **Option B**: migrating raw development microservices (Docker Compose / basic YAML) into a production-grade, security-hardened **Google Kubernetes Engine (GKE)** deployment using **Kustomize**.

---

## 🏛️ Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                        INPUT UNHARDENED WORKLOAD                       │
│    input_workload/docker-compose.yaml & raw-deployment.yaml            │
│    (Runs as root, plaintext secrets, no probes, no resource limits)    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   STAGE 1: CLOUD GEMINI (GKE Architect)                │
│ • Model: Cloud Gemini via Antigravity CLI (agy)                        │
│ • Authentication: Zero API keys needed (active agy session)            │
│ • Emits: Structured Kustomize Blueprint (base/, dev/, prod/)           │
│   incorporating Pod Security Standards (Restricted) & NetworkPolicies  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Kustomize Blueprint
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  STAGE 2: ON-DEVICE GEMMA 4 (Worker)                   │
│ • Model: Gemma 4 26B A4B on Apple Silicon Metal via LiteRT             │
│ • Offline Tools: write_to_file, replace_file_content, run_command      │
│ • Scaffolds: base/, overlays/dev/, overlays/prod/                      │
│ • Authors: Comprehensive operational RUNBOOK.md                        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Generated Manifests & Runbook
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│          STAGE 3: ON-DEVICE GEMMA 4 (GKE Security Auditor)             │
│ • Execution: Fresh, isolated context (Zero drafting bias)              │
│ • Audits against: CIS GKE Benchmark v1.4 & PSS Restricted              │
│ • Emits: Audit Report with [PASS] or [REVISION NEEDED]                 │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Audit Findings
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│              STAGE 4: REMEDIATION LOOP & CLI VERIFICATION              │
│ • Worker automatically patches manifests if findings are reported      │
│ • Runs: PyYAML syntax verification & kustomize build                   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Folder Contents

| File / Directory | Purpose |
| :--- | :--- |
| **`run_gke_swarm.py`** | Dedicated CLI runner executing the GKE hardening swarm. |
| **`input_workload/`** | Sample unhardened development files (`docker-compose.yaml` and `raw-deployment.yaml`) serving as the test fixture. |
| **`README.md`** | This architectural runbook and specification. |

---

## 🚀 How to Run

### Execute the GKE Hardening Swarm
From this folder or the repository root:
```bash
# Using Antigravity CLI (zero API keys needed)
.venv/bin/python "Option B: Kubernetes & GKE Production Hardening & Kustomize Migration/run_gke_swarm.py"

# Or if you are inside this directory:
cd "Option B: Kubernetes & GKE Production Hardening & Kustomize Migration"
../../.venv/bin/python run_gke_swarm.py
```

---

## 📦 Deliverables Produced

Generated Kustomize manifests and operational documentation are output to `workspaces/gke-production-hardening/`:

```text
workspaces/gke-production-hardening/
├── RUNBOOK.md                       # Complete operational deployment runbook
├── base/
│   ├── deployment.yaml              # Hardened deployment with securityContext & probes
│   ├── service.yaml                 # ClusterIP service
│   ├── configmap.yaml               # Externalized configuration
│   ├── hpa.yaml                     # HorizontalPodAutoscaler (autoscaling/v2)
│   ├── pdb.yaml                     # PodDisruptionBudget (policy/v1 minAvailable: 1)
│   ├── networkpolicy.yaml           # Ingress/egress traffic segmentation
│   └── kustomization.yaml           # Base resource list
├── overlays/
│   ├── dev/
│   │   ├── kustomization.yaml       # Dev replica count (1) & relaxed resource limits
│   │   └── patch_replicas.yaml
│   └── prod/
│       ├── kustomization.yaml       # Prod replica count (3), multi-zone anti-affinity
│       └── patch_resources.yaml
```

---

## 🛡️ Security & Reliability Controls Enforced

1. **Pod Security Standards (Restricted)**:
   - `securityContext.runAsNonRoot: true` and `runAsUser: 10001` (Non-root user).
   - `securityContext.readOnlyRootFilesystem: true` (Immutable container filesystem).
   - `securityContext.allowPrivilegeEscalation: false` (Prevents setuid escalation).
   - `securityContext.capabilities.drop: ["ALL"]` (Drops unnecessary Linux capabilities).
   - `seccompProfile.type: RuntimeDefault` (Default seccomp syscall filtering).

2. **GKE Workload Identity Federation**:
   - Annotates Kubernetes ServiceAccount (`iam.gke.io/gcp-service-account: <gsa>`).
   - Zero static Google Cloud service account keys stored in Kubernetes Secrets.

3. **Traffic Segmentation (NetworkPolicies)**:
   - Default-deny ingress and egress rules.
   - Explicit allow rules for required pod-to-pod and egress ports (e.g. DNS port 53, Redis 6379).

4. **Availability & Resilience**:
   - **HorizontalPodAutoscaler (HPA v2)**: Automatic scaling based on 70% CPU / 80% Memory targets.
   - **PodDisruptionBudget (PDB)**: Guarantees at least 1 pod available during GKE node pool maintenance upgrades.
   - **Probes**: Configured `livenessProbe`, `readinessProbe`, and `startupProbe` to eliminate false restarts during initialization.
   - **Resource Governance**: Guaranteed CPU & Memory requests and limits preventing noisy-neighbor starvation.
