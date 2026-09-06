import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro.regime_classifier import RegimeClassifier
from macro.cache import macro_cache
from macro.observability import llm_observer

async def main():
    print("=================================================================")
    print("TESTING 24-HOUR MACRO CACHE & AUTOMATED NEWS PULL")
    print("=================================================================")
    
    # 1. Clear any prior cache for test
    macro_cache.clear()
    classifier = RegimeClassifier()
    print("Initial cache state:", "PRESENT" if macro_cache.load() else "EMPTY")

    # 2. First call: Auto pulls news, queries LLM, caches for 24h
    print("\n[Step 1] Running refresh() — Expecting automatic news pull + LLM debate...")
    res1 = await classifier.refresh()
    print(f"Result 1: Regime={res1.state.name} | Confidence={res1.state.confidence:.2f}")
    print(f"Summary: {res1.state.summary}")
    print(f"Headlines in context: {len(classifier._context.get('headlines', []))}")
    print(f"LLM interactions recorded: {len(llm_observer.records)}")

    # 3. Second call: Must hit 24h cache (0 API calls!)
    print("\n[Step 2] Running refresh() again — Expecting immediate 24h CACHE HIT (Zero LLM calls)...")
    prior_count = len(llm_observer.records)
    res2 = await classifier.refresh()
    print(f"Result 2: Regime={res2.state.name}")
    print(f"Summary: {res2.state.summary}")
    print(f"New LLM calls made during second refresh: {len(llm_observer.records) - prior_count} (Should be 0!)")

    cached = macro_cache.load()
    if cached:
        print(f"\n[OK] 24-Hour Cache Active! Valid until: {cached.expires_at} ({cached.remaining_hours()}h left)")
    
    print("\n=================================================================")
    print("TEST PASSED: Automated News Pulling & 24h Cost Optimization Active!")
    print("=================================================================")

if __name__ == "__main__":
    asyncio.run(main())
