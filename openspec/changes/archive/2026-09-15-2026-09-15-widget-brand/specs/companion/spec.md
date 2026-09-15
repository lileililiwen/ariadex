## ADDED Requirements

### Requirement: Product brand is visible on the widget

The mini-player titlebar MUST show the fixed brand `Ariadex` ahead of
the state word in every indicator state, because the window-manager
title is hidden and screenshots must identify the product.

#### Scenario: Shared screenshot shows the brand

- **WHEN** the widget shows any state (working, paused, waiting, …)
- **THEN** the titlebar reads `Ariadex — {STATE}` and the headless
  text equivalent carries the brand
