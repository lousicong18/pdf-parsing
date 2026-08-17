# Eval Report

## Classification accuracy

- overall: 0.000 (0/1)
  - text: 0.000

## Confusion matrix

| | text | table | mixed | scan |
| --- | --- | --- | --- |
| text | 0 | 0 | 1 | 0 |
| table | 0 | 0 | 0 | 0 |
| mixed | 0 | 0 | 0 | 0 |
| scan | 0 | 0 | 0 | 0 |

## VLM cost
- total_cost: 0.000000
- total_latency_ms: 0
- calls: 0

## Badcases (3)

- {'index': 1, 'expected': {'type': 'table', 'n_rows': 5, 'n_cols': 4}, 'actual': {'type': 'text', 'bbox': [78.0, 293.0199890136719, 207.8920135498047, 312.2980041503906], 'page_type': 'mixed', 'order': 1, 'text': 'I2IIIIII4I4II', 'table': None, 'image': None, 'content': 'I2IIIIII4I4II', 'image_url': None}, 'match': False}
- {'index': 2, 'expected': {'type': 'table', 'n_rows': 4, 'n_cols': 4}, 'actual': {'type': 'text', 'bbox': [78.0, 431.01995849609375, 218.5460205078125, 450.2979736328125], 'page_type': 'mixed', 'order': 2, 'text': 'I3IIIIIII8I5II', 'table': None, 'image': None, 'content': 'I3IIIIIII8I5II', 'image_url': None}, 'match': False}
- {'index': 3, 'expected': {'type': 'table', 'n_rows': 9, 'n_cols': 5}, 'actual': {'type': 'text', 'bbox': [215.93280029296875, 458.25, 379.3427734375, 471.989990234375], 'page_type': 'mixed', 'order': 3, 'text': 'I1\nI2\nI3\nI4\nI5', 'table': None, 'image': None, 'content': 'I1\nI2\nI3\nI4\nI5', 'image_url': None}, 'match': False}