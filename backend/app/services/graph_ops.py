"""Graph analysis helpers built on NetworkX."""

from __future__ import annotations

from typing import Any

import networkx as nx

from app.schemas.graph import EdgeDirection, GraphDocument


def to_networkx(doc: GraphDocument) -> Any:
    """Convert to a `networkx.MultiDiGraph`. Bidirectional edges become two arcs."""
    g = nx.MultiDiGraph(id=doc.id, title=doc.title)
    for n in doc.nodes:
        g.add_node(n.id, label=n.label, kind=n.kind.value, group_id=n.group_id)
    for e in doc.edges:
        attrs = {
            "id": e.id,
            "label": e.label,
            "evidence": e.evidence.value,
            "confidence": e.confidence,
        }
        g.add_edge(e.source, e.target, key=e.id, **attrs)
        if e.direction is EdgeDirection.BIDIRECTIONAL:
            g.add_edge(e.target, e.source, key=f"{e.id}:rev", **attrs)
    return g


def graph_summary(doc: GraphDocument) -> dict[str, Any]:
    g = to_networkx(doc)
    return {
        "node_count": g.number_of_nodes(),
        "edge_count": len(doc.edges),
        "group_count": len(doc.groups),
        "inferred_edge_count": len(doc.inferred_edges()),
        "locked_element_count": len(doc.locked_element_ids()),
        "isolated_nodes": sorted(nx.isolates(g)),
        "is_acyclic": nx.is_directed_acyclic_graph(g),
        "weakly_connected_components": nx.number_weakly_connected_components(g)
        if g.number_of_nodes()
        else 0,
    }
