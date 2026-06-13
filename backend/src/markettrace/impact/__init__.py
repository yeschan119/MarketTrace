"""Impact / abnormal-return computation module.

Public surface:
  - market_model.abnormal_return  — market-adjusted return (AR)
  - returns.cumulative_return     — positional trading-day return from a price frame
  - returns.compute_event_outcomes — list[OutcomeResult] for a given event date
  - returns.OutcomeResult         — frozen dataclass carrying per-horizon metrics
"""
