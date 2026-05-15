# Retrieval Evaluation Results

## Threshold Sweep (all-MiniLM-L6-v2)

_Run `python tools/eval_retrieval.py --sweep` to populate this section._

## Embedding Model Comparison

_Run the following commands and paste results here:_

```bash
python tools/eval_retrieval.py --model all-MiniLM-L6-v2 --sweep
python tools/eval_retrieval.py --model paraphrase-multilingual-MiniLM-L12-v2 --sweep
```

| Model | Avg Recall | Avg Noise | RAM (~) |
|-------|-----------|-----------|---------|
| all-MiniLM-L6-v2 | — | — | ~80 MB |
| paraphrase-multilingual-MiniLM-L12-v2 | — | — | ~440 MB |
| BAAI/bge-m3 | — | — | ~2.3 GB |

**Chosen model:** `all-MiniLM-L6-v2` — pending comparison data.
