# Eval Report

## Classification accuracy

- overall: 0.412 (7/17)
  - text: 0.125
  - table: 0.714
  - mixed: 0.500

## Confusion matrix

| | text | table | mixed | scan |
| --- | --- | --- | --- |
| text | 1 | 7 | 0 | 0 |
| table | 1 | 5 | 1 | 0 |
| mixed | 0 | 1 | 1 | 0 |
| scan | 0 | 0 | 0 | 0 |

## VLM cost
- total_cost: 0.000000
- total_latency_ms: 0
- calls: 0

## Badcases (4)

- {'index': 1, 'expected': {'type': 'table'}, 'actual': {'type': 'text', 'bbox': [72.69290924072266, 578.466552734375, 519.6728515625, 588.466552734375], 'page_type': 'text', 'order': 1, 'text': '本文档专门设计用于测试各类PDF解析工具对复杂版面的识别与还原能力。包含多栏布局、嵌套表格、', 'table': None, 'image': None, 'content': '本文档专门设计用于测试各类PDF解析工具对复杂版面的识别与还原能力。包含多栏布局、嵌套表格、', 'image_url': None}, 'match': False}
- {'index': 2, 'expected': {'type': 'table'}, 'actual': {'type': 'text', 'bbox': [72.69290924072266, 594.466552734375, 332.6929016113281, 604.466552734375], 'page_type': 'text', 'order': 2, 'text': '嵌入图表、代码块、脚注注释、图文混排等多种排版元素。', 'table': None, 'image': None, 'content': '嵌入图表、代码块、脚注注释、图文混排等多种排版元素。', 'image_url': None}, 'match': False}
- {'index': 3, 'expected': {'type': 'table'}, 'actual': {'type': 'text', 'bbox': [98.40438842773438, 347.0547180175781, 496.8303527832031, 361.0547180175781], 'page_type': 'text', 'order': 3, 'text': 'Comprehensive Test Document for PDF Layout & Content Parsing', 'table': None, 'image': None, 'content': 'Comprehensive Test Document for PDF Layout & Content Parsing', 'image_url': None}, 'match': False}
- {'index': 2, 'expected': {'type': 'image'}, 'actual': {'type': 'text', 'bbox': [62.692909240722656, 104.49368286132812, 430.1929016113281, 114.99368286132812], 'page_type': 'mixed', 'order': 2, 'text': '字体嵌入，属文字层内容；解析器应原样保留这些符号而非误判为图片或乱码。', 'table': None, 'image': None, 'content': '字体嵌入，属文字层内容；解析器应原样保留这些符号而非误判为图片或乱码。', 'image_url': None}, 'match': False}