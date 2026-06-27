# /structuring - the P2 package

The product / strategy / quant rulebook. **P2 owns the methodology; P1 implements it in the backend; P3 builds the UI.** Docs only - no backend code, no changes to `contracts/` or the OMS.

## Read in this order
1. **product-tiers.md** - the product shape (templates seed it, the builder is the product).
2. **METHODOLOGY.md** - how a view becomes a hedged position (incl. linkage & hedge effectiveness).
3. **templates.md** / **templates.json** - the 5 starter combos + machine-readable config.
4. **hedge-classifier.md** - implementation spec for P1's layer-3 (formulas, thresholds, pseudocode, output).
5. **strategy-schema.proposal.md** - `StrategyIntent` -> `OrderPlan` (DRAFT, for P1 to ratify into `/contracts`).
6. **demo_classifier.py** - runnable reference implementation. `python3 demo_classifier.py`.
7. **builder-ux.md** - the 3 tiers as screens, for P3.
8. **regulatory-approach.md** - compliance stance + phasing.
9. **yc-onepager.md** - the pitch.

Diagrams: `methodology-scheme.png`, `linkage-hedge-graph.png`, `demo-results.png`, `product-tiers.png`.

## Boundary (no overlap)
- **P2** = the rules: hedge math, templates, calibration (`move_adverse`), residual-risk definition, the schema shape.
- **P1** = the engine: relationship engine, hedge classifier, payoff engine, OMS, connectors, ledger.
- **P3** = the builder UI.
See METHODOLOGY.md section 8.

## Open questions waiting on P1 (Abransh)
1. Full offset vs a premium-budget cap.
2. Atomic basket vs allow a primary-only fill if the hedge can't fill.
3. `move_adverse` source - templates.json vs a config service.
4. Binary only vs multi-outcome markets in v1.
