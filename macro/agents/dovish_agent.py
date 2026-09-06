from config.settings import settings
from macro.agents.base import OpenAIAgent


class DovishAgent(OpenAIAgent):
    name = "dovish"
    role = (
        "Evaluate growth slowdowns, yield curve inversions, and liquidity distress. "
        "Bias positive when easing / risk-off growth concerns dominate."
    )
    model = settings.primary_macro_model
