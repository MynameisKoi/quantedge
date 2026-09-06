from config.settings import settings
from macro.agents.base import OpenAIAgent


class CommodityAgent(OpenAIAgent):
    name = "commodity_specialist"
    role = (
        "Evaluate supply-side shocks, OPEC decisions, geopolitics, and commodity inventories "
        "affecting XAUUSD and USOIL."
    )
    model = settings.fast_sentiment_model
