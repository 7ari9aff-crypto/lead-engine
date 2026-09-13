# OpenManus 24/7 AWS Cloud Runner Architecture

This document specifies the production cloud deployment of the **OpenManus Autonomous Research Runtime** and **Model Gateway**, provisioned on AWS EC2 to operate 24/7 as the deep-browsing backbone for Lead Engine.

---

## 1. Cloud Infrastructure Overview

| Component | AWS Resource / Specification |
| :--- | :--- |
| **Instance Type** | AWS EC2 `t3.medium` (2 vCPUs, 4.0 GiB RAM) |
| **Storage** | 40 GB NVMe GP3 SSD (3000 IOPS, 125 MB/s throughput) |
| **Swap Space** | 4.0 GiB SSD Swap (`/swapfile`) &rarr; **8.0 GiB Total Virtual Memory** |
| **Operating System** | Ubuntu 24.04 LTS (Noble Numbat) |
| **Region** | `us-east-1` (N. Virginia) |
| **Static Public IP** | `3.234.58.194` (AWS Elastic IP) |
| **Open Ports** | TCP 22 (SSH), 80 (HTTP), 443 (HTTPS), 8000 (Gateway), 8600 (OpenManus Wrapper) |

---

## 2. Service Architecture & Daemons

Two isolated `systemd` daemons run 24/7 on the cloud runner with automatic failure restart (`Restart=always`, `RestartSec=3`):

### A. Model Gateway (`model-gateway.service` on Port 8000)
- **Role**: High-availability AI model router and key quota governor.
- **Provider Pool**: 19 active Google AI Studio / Gemini project slots + 17 Exa.ai neural search accounts.
- **Target Model**: `gemini-3.8-flash` (strictly preserved without silent downgrades).
- **In-Flight Failover**: Automatically cycles through account slots upon temporary RPM 429 limits without failing caller requests.
- **Health & Status Dashboard**:
  - Health: `GET http://3.234.58.194:8000/health`
  - Real-Time Quota Dashboard: `GET http://3.234.58.194:8000/status`

### B. OpenManus Wrapper (`openmanus-wrapper.service` on Port 8600)
- **Role**: REST Bridge exposing asynchronous research and browser automation tasks to Lead Engine.
- **Contract Compliance**: Implements `POST /tasks`, `GET /tasks/{id}`, and `GET /health` adhering strictly to `docs/openmanus-contract.md`.
- **Headless Browser**: Chromium 134 headless shell powered by Playwright.
- **Security & Fail-Closed**: Bearer token authentication enforced. Rejects unauthenticated traffic with HTTP 401.

---

## 3. Connecting Lead Engine to the Cloud Runner

In your deployment environment (e.g. Vercel, Docker, or local `.env`):

```bash
# Point Lead Engine to the 24/7 AWS Runner
OPENMANUS_BASE_URL=http://3.234.58.194:8600
OPENMANUS_TOKEN=<OPENMANUS_WRAPPER_TOKEN>
```

When configured, Lead Engine's `lead_engine.research.orchestrator` and `lead_engine.research.openmanus` automatically dispatch deep research jobs to the AWS runner, collect provenanced facts (phone, email, decision-makers, city), and ingest them directly into the Truth Layer.
