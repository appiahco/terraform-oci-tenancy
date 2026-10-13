# Security Zone on Production with an excluded edge compartment

Production is guarded by a Security Zone using a custom recipe rather than Oracle's Maximum Security Recipe, which cannot be edited, does not document its contents and would forbid the public load-balancer subnet and gateways our network needs. The recipe keeps `deny_public_subnets`, so the one public subnet and its load balancers live in a `production/edge` subcompartment excluded from the zone: a small, explicit hole rather than dropping the public-subnet guard for all of Production. Staging gets a matching unzoned `staging/edge` so both environments share one layout.

## Consequences

- The recipe lists its policies explicitly; policies Oracle adds later are adopted only by a reviewed change.
- The gateway, DRG and public-load-balancer policies are omitted because the network design requires them.
- The four Vault-key policies are omitted while there is no Vault; adopting Vault should revisit them.
