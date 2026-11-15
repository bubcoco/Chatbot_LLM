"""finalize: publish the draft as the final reply."""

from supportkit.core.graph.state import SupportState


def finalize(state: SupportState) -> dict:
    return {"final_reply": state["draft_reply"]}
