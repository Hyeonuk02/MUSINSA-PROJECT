# Prince Mart legacy source snapshot

This directory contains the three services selected as the legacy reference for
the Musinsa project:

- `order-service`
- `coupon-service`
- `payment-service`

## Provenance

- Upstream: <https://github.com/PrajwalSH1930/prince-mart-e-commerce-backend>
- Commit: `c56bac8de91bfc1cdd8863bd720cfe7e4568276d`
- License: EPL-2.0 (see `LICENSE`)

The source is copied without functional modifications. Generated Maven output,
IDE metadata, and per-service Maven wrapper files were intentionally omitted.
The original `pom.xml`, application source, resources, tests, and Docker files
for the three selected services are retained.

## Current role

This is an upstream baseline, not yet the locally runnable experiment stack.
It still contains dependencies on services outside the selected scope, such as
Cart, Inventory, Identity, Address, Shipping, Audit, Notification, and Razorpay.
Those dependencies must be removed or replaced with deterministic stubs before
this snapshot can serve as the controlled Legacy system.
