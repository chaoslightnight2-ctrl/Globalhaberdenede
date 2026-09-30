"""Small same-model schema request; never logs the API credential."""
import json
import os
import time
from pathlib import Path
import requests

key = os.environ['GROQ_API_KEY']
schema = {'type': 'object', 'properties': {'ready': {'type': 'boolean'}, 'visual_query': {'type': 'string'},
          'cta': {'type': 'string', 'enum': ['Global Haber kanalına abone ol']},
          'tags': {'type': 'array', 'items': {'type': 'string'}}},
          'required': ['ready', 'visual_query', 'cta', 'tags'], 'additionalProperties': False}
from news_generation import package_schema
schema = package_schema(['technology_science', 'economy_life', 'health_education', 'climate_energy', 'transport_cities', 'culture_arts', 'sports', 'disasters_safety', 'politics_diplomacy', 'society', 'world_affairs'], 'Global Haber')
for attempt in range(3):
    response = requests.post('https://api.groq.com/openai/v1/chat/completions',
    headers={'Authorization': f'Bearer {key}'}, timeout=90, json={
        'model': 'openai/gpt-oss-120b', 'messages': [{'role': 'user', 'content': 'Return suitable false reason diagnostic title empty hook empty cta Global Haber kanalına abone ol description empty visual_query moon surface space topic_bucket technology_science narration_parts empty array tags empty array hashtags empty array.'}],
        'max_completion_tokens': 256, 'reasoning_effort': 'low', 'temperature': 0,
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'provider_test', 'strict': True, 'schema': schema}}})
    if response.status_code != 429 or attempt == 2:
        break
    delay = float(response.headers.get('retry-after', 60)) + 1
    if delay > 150:
        break
    time.sleep(delay)
data = response.json()
report = {'http_status': response.status_code,
          'limits': {k: v for k, v in response.headers.items() if k.lower().startswith('x-ratelimit-') or k.lower() == 'retry-after'}}
if response.ok:
    report['usage'] = data.get('usage')
    report['result'] = json.loads(data['choices'][0]['message']['content'])
else:
    report['error'] = str(data.get('error', {}).get('message', 'No error message')).replace(key, '[redacted]')
Path('maintenance/groq-probe.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
raise SystemExit(0 if response.ok else 1)
