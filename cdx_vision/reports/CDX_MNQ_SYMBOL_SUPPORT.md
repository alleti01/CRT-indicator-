# MNQ symbol support

Vision price ticks stay 0.25 for both NQ and MNQ. Dollar value is not part of the reader.

Accepted chart text:

- MNQ1!
- MNQ 12-26
- NQ1!
- NQ

`MNQ` is matched before `NQ`, so MNQ is not treated as NQ by a prefix check.

ES1! is rejected.

The golden NQ short (30909.50 / 30947.00 / 30872.00 / 30845.00) still passes the existing fixture test.
