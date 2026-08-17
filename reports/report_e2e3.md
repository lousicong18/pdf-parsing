# Eval Report

## Classification accuracy

- overall: 0.412 (7/17)
  - text: 0.111
  - mixed: 0.500
  - table: 1.000

## Confusion matrix

| | text | table | mixed | scan |
| --- | --- | --- | --- |
| text | 1 | 8 | 0 | 0 |
| table | 0 | 4 | 0 | 0 |
| mixed | 0 | 2 | 2 | 0 |
| scan | 0 | 0 | 0 | 0 |

## VLM cost
- total_cost: 0.000000
- total_latency_ms: 0
- calls: 0

## Badcases (1)

- {'index': 2, 'expected': {'type': 'image'}, 'actual': {'type': 'text', 'bbox': [62.692909240722656, 104.49368286132812, 430.1929016113281, 114.99368286132812], 'page_type': 'mixed', 'order': 2, 'text': '字体嵌入，属文字层内容；解析器应原样保留这些符号而非误判为图片或乱码。', 'table': None, 'image': None, 'content': '字体嵌入，属文字层内容；解析器应原样保留这些符号而非误判为图片或乱码。', 'image_url': None}, 'match': False}