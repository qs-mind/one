"""The QS Calc Engine: the AI writes a formula, this package computes it exactly.

Formulas are data, never code. Values are `Decimal` and exact decimal text, never floats. All
arithmetic runs inside `decimal.localcontext(CONTEXT)`, never the global context.
"""

import decimal

# Stored on every calculation, so a later change to the rules can find what older rules computed.
ENGINE_VERSION = 1

CONTEXT = decimal.Context(
    prec=50,
    rounding=decimal.ROUND_HALF_EVEN,
    Emax=999_999,
    Emin=-999_999,
    traps=[decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow],
)
