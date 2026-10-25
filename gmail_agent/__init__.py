"""Personal Gmail agent. Separate from the trading code: it never imports or changes it
(it only reuses store.py to keep its own activity log in Supabase).

Reads headers and labels only (never bodies). Adds "Agent/" labels only when dry-run is off.
"""
