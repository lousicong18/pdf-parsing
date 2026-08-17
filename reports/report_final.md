# Eval Report

## Classification accuracy

- overall: 1.000 (10/10)
  - text: 1.000
  - mixed: 1.000

## Confusion matrix

| | text | table | mixed | scan |
| --- | --- | --- | --- |
| text | 6 | 0 | 0 | 0 |
| table | 0 | 0 | 0 | 0 |
| mixed | 0 | 0 | 4 | 0 |
| scan | 0 | 0 | 0 | 0 |

## VLM cost
- total_cost: 0.004082
- total_latency_ms: 30544
- calls: 4

## Badcases (2)

- {'index': 4, 'expected': {'type': 'image'}, 'actual': {'type': 'text', 'bbox': [185.66510009765625, 203.68426513671875, 409.6091003417969, 231.68426513671875], 'page_type': 'text', 'order': 4, 'text': 'PDF 图文混排解析', 'table': None, 'image': None, 'content': 'PDF 图文混排解析', 'image_url': None}, 'match': False}
- {'index': 5, 'expected': {'type': 'image'}, 'actual': {'type': 'text', 'bbox': [191.49960327148438, 464.14703369140625, 403.7776184082031, 507.14703369140625], 'page_type': 'text', 'order': 5, 'text': '版本: v2.1.0\n日期: 2026年8月\n用途: 评估PDF解析器对复杂版面的识别能力', 'table': None, 'image': None, 'content': '版本: v2.1.0\n日期: 2026年8月\n用途: 评估PDF解析器对复杂版面的识别能力', 'image_url': None}, 'match': False}