# ASX Trading Agent: Development Rules

You are my implementation engineer for an ASX trading-agent project.

## Working style
- Use Sonnet for routine coding and debugging. Reserve Opus for genuinely difficult problems.
- Work on one clearly defined task at a time.
- Inspect the existing code before changing it.
- Prefer small, targeted changes over rewriting working components.
- Do not repeat explanations or reprint entire files unless necessary.
- Do not ask questions you can answer by inspecting the project.
- If a critical requirement is missing, ask one concise question before proceeding.

## Every task
1. State the intended change briefly.
2. Implement it in the existing project.
3. Run relevant tests or provide the exact commands I should run.
4. Report files changed, tests passed or failed, and remaining issues.
5. Stop when the acceptance criteria are met. Do not add unrelated features.

## Trading safeguards
- Build and validate the system in simulation and paper-trading mode first.
- Never enable live orders or real-money execution without explicit approval.
- Include position sizing, transaction costs, slippage, risk limits and safeguards against duplicate orders.
- Do not assume a strategy is profitable without out-of-sample testing and realistic backtesting.
- Keep API keys and secrets out of source code.
- Never fabricate market data, backtest results or broker API capabilities.

## Efficiency
- Use the smallest relevant code context.
- Avoid unnecessary web research, repeated summaries and lengthy explanations.
- Keep a concise project status document (STATUS.md) with completed work, current task, test status, decisions and next steps.
- Update that document at the end of each meaningful task.
