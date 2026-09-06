from config.settings import settings
from macro.agents.base import OpenAIAgent


class HawkishAgent(OpenAIAgent):
    name = "hawkish"
    role = (
        "Analyze CPI, NFP, and Fed statements for inflationary / rate-hike implications. "
        "Bias positive when inflation risk and policy tightening dominate."
    )
    model = settings.primary_macro_model
