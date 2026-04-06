from dotenv import load_dotenv
load_dotenv('.env')
from get_relevant_docs import get_relevant_docs

queries = [
    ("TestRail — members invite flow",      "test cases for members invite flow"),
    ("Jira — initiative campaign",           "initiative campaign content association"),
    ("Cypress — create content via API",     "how to create content via API in cypress"),
]

for label, query in queries:
    print(f"\n{'='*60}")
    print(f"QUERY: {label}")
    print(f"{'='*60}")
    results = get_relevant_docs(query, top_k=2)
    for i, r in enumerate(results, 1):
        print(f"\n  Result {i}:")
        print(f"  ID     : {r.get('id', '?')}")
        print(f"  Source : {r.get('source') or r.get('type', '?')}")
        print(f"  Content: {r['content'][:350]}")
        print()
