# OCI Tenancy

The `appiahco` Oracle Cloud tenancy, declared and enforced from this repository.

## Language

### Source of truth

**Tenancy**:
The `appiahco` Oracle Cloud account (home region us-ashburn-1) this repository governs.
_Avoid_: account, cloud

**Root**:
An independently applied unit of configuration with its own state: `bootstrap`, `foundation` or `workloads`.
_Avoid_: stack, layer, workspace

**Bootstrap**:
The root holding what the pipeline needs before it can run (apply user, plan user, their policies, the state bucket); applied by hand.

**Foundation**:
The root holding tenancy-wide structure: compartments, IAM, tagging, budgets, networking.

**Workloads**:
The root holding resources that run things: compute, databases, clusters.

**Drift**:
Any difference between the tenancy and what `main` declares.

**Revert**:
Applying `main` to erase drift; automatic only when the plan updates in place.

**Break-glass identity**:
A human administrator deliberately left unmanaged by this repository so a bad apply cannot lock it out.
_Avoid_: admin user, root user

**Apply user**:
The dedicated OCI user whose API key the pipeline uses to apply `main` and to run drift checks.
_Avoid_: CI user, service account, bot

**Plan user**:
The dedicated OCI user whose API key pull-request plans use; it can read the tenancy but never change it.
_Avoid_: read-only user, plan bot

### Compartments

**Platform**:
The compartment holding shared infrastructure (networking, security) used by both environments.
_Avoid_: shared, hub, core

**Production**:
The compartment holding live workloads.
_Avoid_: prod

**Staging**:
The compartment where changes are rehearsed before they reach Production.
_Avoid_: dev, nonprod, test

**Bootstrap compartment**:
The compartment owned by Bootstrap holding only the pipeline's state; the CI user cannot touch anything else in it.
_Avoid_: state compartment

### Network

**Platform VCN**:
The network in Platform holding shared access paths; every Environment VCN can reach it.
_Avoid_: hub

**Environment VCN**:
The network belonging to Production or Staging; it reaches the Platform VCN but never the other environment.
_Avoid_: spoke

**DRG**:
The router joining the Platform VCN to each Environment VCN and deciding which may talk to which.
_Avoid_: transit, gateway
