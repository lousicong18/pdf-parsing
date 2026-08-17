# Eval Report

## Classification accuracy

- overall: 0.000 (0/1)
  - text: 0.000

## Confusion matrix

| | text | table | mixed | scan |
| --- | --- | --- | --- |
| text | 0 | 1 | 0 | 0 |
| table | 0 | 0 | 0 | 0 |
| mixed | 0 | 0 | 0 | 0 |
| scan | 0 | 0 | 0 | 0 |

## VLM cost
- total_cost: 0.000000
- total_latency_ms: 0
- calls: 0

## Badcases (3)

- {'index': 0, 'expected': {'type': 'text'}, 'actual': {'type': 'table', 'bbox': [241.98780000000002, 162.0, 353.2878, 252.0], 'page_type': 'table', 'order': 0, 'text': None, 'table': {'rows': [['nn', 'nn', 'nn', 'nn'], ['nn', '25', 'nn', '90'], ['nn', '30', 'nn', '85'], ['nn', '28', 'nn', '92'], ['nn', '35', 'nn', '88']], 'n_rows': 5, 'n_cols': 4, 'merged': [], 'cross_page': False, 'bbox': [241.98780000000002, 162.0, 353.2878, 252.0]}, 'image': None, 'content': '| nn | nn | nn | nn |\n| --- | --- | --- | --- |\n| nn | 25 | nn | 90 |\n| nn | 30 | nn | 85 |\n| nn | 28 | nn | 92 |\n| nn | 35 | nn | 88 |', 'image_url': None}, 'match': False}
- {'index': 2, 'expected': {'type': 'table', 'n_rows': 4, 'n_cols': 4}, 'actual': {'type': 'table', 'bbox': [203.7378, 456.0, 391.5378, 618.0], 'page_type': 'table', 'order': 2, 'text': None, 'table': {'rows': [['n1', 'n2', 'n3', 'n4', 'n5'], ['R1C1', 'R1C2', 'R1C3', 'R1C4', 'R1C5'], ['R2C1', 'R2C2', 'R2C3', 'R2C4', 'R2C5'], ['R3C1', 'R3C2', 'R3C3', 'R3C4', 'R3C5'], ['R4C1', 'R4C2', 'R4C3', 'R4C4', 'R4C5'], ['R5C1', 'R5C2', 'R5C3', 'R5C4', 'R5C5'], ['R6C1', 'R6C2', 'R6C3', 'R6C4', 'R6C5'], ['R7C1', 'R7C2', 'R7C3', 'R7C4', 'R7C5'], ['R8C1', 'R8C2', 'R8C3', 'R8C4', 'R8C5']], 'n_rows': 9, 'n_cols': 5, 'merged': [], 'cross_page': False, 'bbox': [203.7378, 456.0, 391.5378, 618.0]}, 'image': None, 'content': '| n1 | n2 | n3 | n4 | n5 |\n| --- | --- | --- | --- | --- |\n| R1C1 | R1C2 | R1C3 | R1C4 | R1C5 |\n| R2C1 | R2C2 | R2C3 | R2C4 | R2C5 |\n| R3C1 | R3C2 | R3C3 | R3C4 | R3C5 |\n| R4C1 | R4C2 | R4C3 | R4C4 | R4C5 |\n| R5C1 | R5C2 | R5C3 | R5C4 | R5C5 |\n| R6C1 | R6C2 | R6C3 | R6C4 | R6C5 |\n| R7C1 | R7C2 | R7C3 | R7C4 | R7C5 |\n| R8C1 | R8C2 | R8C3 | R8C4 | R8C5 |', 'image_url': None}, 'match': False}
- {'index': 3, 'expected': {'type': 'table', 'n_rows': 9, 'n_cols': 5}, 'actual': None, 'match': False}