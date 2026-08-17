from collections import defaultdict


def column_detection(blocks: list) -> int:
    """Detect column count by clustering text-block bbox[0] (x0).

    Shared by classify_features (writes PageFeatures.columns) and
    extract_text / mixed (sorting only, no feature rewrite).
    """
    if not blocks:
        return 1

    x0s = []
    for b in blocks:
        if isinstance(b, dict):
            bbox = b.get("bbox", [0, 0, 0, 0])
        elif isinstance(b, (tuple, list)):
            bbox = b  # raw get_text("blocks") tuple: (x0,y0,x1,y1,text,...)
        else:
            bbox = getattr(b, "bbox", [0, 0, 0, 0])
        x0s.append(float(bbox[0]))

    if len(x0s) <= 1:
        return 1

    # cluster x0 by proximity (half-page-width tolerance)
    width_max = max(x0s) - min(x0s)
    tol = max(width_max * 0.1, 20.0)
    sorted_x = sorted(x0s)
    clusters: list[list[float]] = [[sorted_x[0]]]
    for x in sorted_x[1:]:
        if x - clusters[-1][-1] <= tol:
            clusters[-1].append(x)
        else:
            clusters.append([x])

    # treat tight multi-cluster noise as single column
    significant = [c for c in clusters if len(c) >= max(2, len(x0s) * 0.1)]
    return max(len(significant), 1)
