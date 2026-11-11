"""Read-only public-market evaluation; never modifies the trading database."""
import json, time
from pathlib import Path
import requests
import pandas as pd
from app.ml.prediction_engine import StatisticalAIPredictionEngine
end=int(time.time()); start=end-30*86400
rows=[]
for left in range(start,end,900*300):
    response=requests.get('https://api.india.delta.exchange/v2/history/candles',params=dict(symbol='BTCUSD',resolution='5m',start=left,end=min(left+900*300,end)),timeout=20)
    response.raise_for_status(); payload=response.json()
    if not payload.get('success'): raise RuntimeError('Exchange rejected candle request')
    rows.extend(payload['result'])
df=pd.DataFrame(rows).drop_duplicates('time').sort_values('time')
results=[]
for fraction in (.6,.8,1.):
    subset=df.iloc[:int(len(df)*fraction)]
    results.append(dict(window_candles=len(subset),evaluation=StatisticalAIPredictionEngine().train_models(subset)))
output=dict(requested_days=30,candles=len(df),start=int(df.time.min()),end=int(df.time.max()),evaluations=results,notice='Overlapping evaluation windows; exploratory diagnostics, not independent significance tests.')
Path('backend/research/history_validation.json').write_text(json.dumps(output,indent=2))
print(json.dumps(output,indent=2))
