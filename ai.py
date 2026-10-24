"""AI helpers for the Iron Paw race: the Risk Manager (Claude Haiku 5.5) and the Coach (Claude Sonnet 5.5).

Paper money only. The key comes from the ANTHROPIC_API_KEY env var. Every reply is constrained to a JSON
schema. The risk manager fails safe: any error, refusal or unreadable reply counts as a block.
"""
import json
import os

import anthropic

RISK_MODEL = "claude-haiku-5-5"
COACH_MODEL = "claude-sonnet-5-5"
RISK_SYSTEM = ("You are a strict risk manager for a paper trading account. Approve or block this trade. Block it if it risks "
               "more than 2% of the account, fees are too high for the size, it adds too much to one sector, or the bot is losing "
               "heavily today. Reply in JSON: {\"decision\": \"approve\" or \"block\", \"reason\": \"one plain-English sentence\"}.")
RISK_SCHEMA = {"type": "object", "properties": {"decision": {"type": "string", "enum": ["approve", "block"]}, "reason": {"type": "string"}},
               "required": ["decision", "reason"], "additionalProperties": False}

# Sector of each name in the race (GICS sector for ASX shares; all coins count as one "Crypto" sector)
SECTORS = {"ALL.AX": "Consumer Discretionary", "ANZ.AX": "Financials", "BHP.AX": "Materials", "BOE.AX": "Energy", "CBA.AX": "Financials",
           "COL.AX": "Consumer Staples", "CSL.AX": "Health Care", "EVN.AX": "Materials", "FMG.AX": "Materials", "GMG.AX": "Real Estate",
           "IGO.AX": "Materials", "LYC.AX": "Materials", "MIN.AX": "Materials", "MQG.AX": "Financials", "NAB.AX": "Financials",
           "NST.AX": "Materials", "PDN.AX": "Energy", "PLS.AX": "Materials", "QBE.AX": "Financials", "REA.AX": "Communication Services",
           "RIO.AX": "Materials", "STO.AX": "Energy", "TCL.AX": "Industrials", "TLS.AX": "Communication Services", "WBC.AX": "Financials",
           "WDS.AX": "Energy", "WES.AX": "Consumer Discretionary", "WOW.AX": "Consumer Staples", "WTC.AX": "Information Technology",
           "XRO.AX": "Information Technology", "VAS.AX": "Index fund"}


def sector(ticker):
    return "Crypto" if ticker.endswith("-AUD") else SECTORS.get(ticker, "Unknown")


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(timeout=60.0, max_retries=2)


def _json_reply(response):
    if response.stop_reason == "refusal":
        raise RuntimeError("the model declined to answer")
    text = next((b.text for b in response.content if b.type == "text"), "")
    return json.loads(text)


def risk_review(payload):
    """Ask the risk manager. Returns (approved, reason). Any failure is a block."""
    try:
        r = _client().with_options(timeout=30.0).messages.create(
            model=RISK_MODEL, max_tokens=2000, system=RISK_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": RISK_SCHEMA}})
        data = _json_reply(r)
        decision, reason = data.get("decision"), str(data.get("reason", "")).strip()
        if decision not in ("approve", "block") or not reason:
            return False, "Blocked: the risk manager's reply could not be read."
        return decision == "approve", reason
    except Exception as e:
        return False, f"Blocked to be safe: the risk manager was unavailable ({type(e).__name__})."


def coach_json(system, payload, schema, max_tokens=16000):
    """One Coach call with a JSON-schema reply. Raises on any failure (the caller reports it, never guesses)."""
    r = _client().beta.messages.create(
        model=COACH_MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": schema}},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    return _json_reply(r)


# Rule-based stand-in for the risk manager, used by backtests (the AI may already know past prices).
RULE_LIMITS = {"risk_pct": 2.0, "fee_pct": 2.0, "sector_pct": 40.0, "daily_loss_pct": 3.0}


def risk_rules(payload):
    """The risk manager's limits as plain rules, on the same payload the live risk gate builds. Returns (approved, reason)."""
    t, acct = payload["trade"], payload["account"]
    total = acct["value"] or 1.0
    if t["loss_if_stopped_pct_of_account"] > RULE_LIMITS["risk_pct"]:
        return False, f"A stop-out would lose {t['loss_if_stopped_pct_of_account']:.1f}% of the account (limit {RULE_LIMITS['risk_pct']:g}%)."
    if t["fee_pct_of_trade"] > RULE_LIMITS["fee_pct"]:
        return False, f"Fees are {t['fee_pct_of_trade']:.1f}% of the trade (limit {RULE_LIMITS['fee_pct']:g}%)."
    if t["sector"] != "Crypto":  # every coin is one sector, so the sector limit only applies to shares
        in_sector = sum(p["value"] for p in payload["open_positions"] if p["sector"] == t["sector"]) + t["cost"]
        if in_sector / total * 100 > RULE_LIMITS["sector_pct"]:
            return False, f"{t['sector']} would be {in_sector / total * 100:.0f}% of the account (limit {RULE_LIMITS['sector_pct']:g}%)."
    today = payload["today"]["realised_pnl"] + payload["today"]["unrealised_pnl"]
    if today < -RULE_LIMITS["daily_loss_pct"] / 100 * total:
        return False, f"Down ${-today:,.2f} today, more than {RULE_LIMITS['daily_loss_pct']:g}% of the account."
    return True, "Within the risk limits."
