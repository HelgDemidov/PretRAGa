"""Validate entity_map.yaml as a graph and generate BOTH derived views:
entity_map.md (graph + attribute tables + placeholder registry) and
entity_glossary.md (prose glossary: hand-written conventions preamble +
per-entity definitions from the map).

Source of truth: entity_map.yaml — the ONLY hand-written file of the system
and the ONLY entry channel for entity/term changes: entities, attributes,
relations, definitions AND the cross-cutting conventions prose (top-level
`conventions` block). This script is the only writer of both generated
views — never edit them by hand; entity_map_check.py detects stale or
hand-edited views.

Checks: duplicate ids, dangling relation endpoints, isolated entities,
placeholders without a decision trigger, unknown groups/statuses,
entities without a definition, missing conventions block.

Run: .venv/bin/python docs/system_design/design_truth/entity_map_build.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import networkx as nx
import yaml

HERE = Path(__file__).parent
SOURCE = HERE / "entity_map.yaml"
MAP_VIEW = HERE / "entity_map.md"
GLOSSARY_VIEW = HERE / "entity_glossary.md"

STATUSES = {
    "fixed": "✅ зафиксировано",
    "placeholder": "⬜ плейсхолдер",
    "implementation_time": "🔧 выбор реализации",
    "deferred": "⏩ отложено",
}


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    groups = data.get("groups", {})
    entities = data.get("entities", [])
    relations = data.get("relations", [])

    if not str(data.get("conventions", "")).strip():
        errors.append("missing top-level conventions block (the glossary preamble prose)")

    ids = [e["id"] for e in entities]
    for eid in ids:
        if ids.count(eid) > 1:
            errors.append(f"duplicate entity id: {eid}")
    known = set(ids)

    for e in entities:
        if e.get("group") not in groups:
            errors.append(f"unknown group {e.get('group')!r} on entity {e['id']}")
        if not str(e.get("definition", "")).strip():
            errors.append(
                f"entity {e['id']} has no definition — an entity that cannot be "
                "defined in prose is not ready to enter the truth"
            )
        for a in e.get("attributes", []):
            if a.get("status") not in STATUSES:
                errors.append(f"unknown status {a.get('status')!r} on {e['id']}.{a.get('name')}")
            if a.get("status") == "placeholder" and not a.get("trigger"):
                errors.append(f"placeholder without trigger: {e['id']}.{a.get('name')}")

    graph = nx.DiGraph()
    graph.add_nodes_from(known)
    for r in relations:
        for endpoint in (r["from"], r["to"]):
            if endpoint not in known:
                errors.append(f"relation endpoint not a defined entity: {endpoint} ({r['from']} -> {r['to']})")
        if r["from"] in known and r["to"] in known:
            graph.add_edge(r["from"], r["to"])

    for node in graph.nodes:
        if graph.degree(node) == 0:
            errors.append(f"isolated entity (no relations): {node}")

    return errors


def _by_group(data: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for e in data["entities"]:
        grouped.setdefault(e["group"], []).append(e)
    return grouped


def mermaid_block(data: dict) -> str:
    lines = ["```mermaid", "flowchart LR"]
    grouped = _by_group(data)
    for gid, title in data["groups"].items():
        members = grouped.get(gid, [])
        if not members:
            continue
        lines.append(f'    subgraph {gid}["{title}"]')
        for e in members:
            lines.append(f'        {e["id"]}["{e["ru"]}"]')
        lines.append("    end")
    for r in data["relations"]:
        lines.append(f'    {r["from"]} -- "{r["type"]}" --> {r["to"]}')
    lines.append("```")
    return "\n".join(lines)


def group_summary_block(data: dict) -> str:
    """One node per group; an edge A -> B labeled with the number of relations
    crossing from entities of A to entities of B. Deterministic order (relation
    order) — the freshness check compares generated views byte-for-byte."""
    group_of = {e["id"]: e["group"] for e in data["entities"]}
    counts: dict[tuple[str, str], int] = {}
    for r in data["relations"]:
        ga, gb = group_of[r["from"]], group_of[r["to"]]
        if ga != gb:
            counts[(ga, gb)] = counts.get((ga, gb), 0) + 1
    lines = ["```mermaid", "flowchart LR"]
    for gid, title in data["groups"].items():
        lines.append(f'    {gid}["{title}"]')
    for (ga, gb), n in counts.items():
        lines.append(f'    {ga} -- "{n}" --> {gb}')
    lines.append("```")
    return "\n".join(lines)


def group_projection_block(data: dict, gid: str) -> str:
    """Projection of one group: its entities inside a subgraph, every incident
    relation, cross-group neighbours as stadium-shaped external nodes."""
    group_of = {e["id"]: e["group"] for e in data["entities"]}
    ru = {e["id"]: e["ru"] for e in data["entities"]}
    members = [e for e in data["entities"] if e["group"] == gid]
    member_ids = {e["id"] for e in members}
    edges = [r for r in data["relations"] if gid in (group_of[r["from"]], group_of[r["to"]])]
    externals: list[str] = []
    for r in edges:
        for end in (r["from"], r["to"]):
            if end not in member_ids and end not in externals:
                externals.append(end)
    lines = ["```mermaid", "flowchart LR", f'    subgraph {gid}["{data["groups"][gid]}"]']
    for e in members:
        lines.append(f'        {e["id"]}["{e["ru"]}"]')
    lines.append("    end")
    for x in externals:
        lines.append(f'    {x}(["{ru[x]}"])')
    for r in edges:
        lines.append(f'    {r["from"]} -- "{r["type"]}" --> {r["to"]}')
    lines.append("```")
    return "\n".join(lines)


def group_projections(data: dict) -> str:
    out: list[str] = []
    grouped = _by_group(data)
    for gid, title in data["groups"].items():
        if not grouped.get(gid):
            continue
        out.append(f"### {title}\n")
        out.append(group_projection_block(data, gid))
        out.append("")
    return "\n".join(out)


def attribute_tables(data: dict) -> str:
    out: list[str] = []
    grouped = _by_group(data)
    for gid, title in data["groups"].items():
        members = grouped.get(gid, [])
        if not members:
            continue
        out.append(f"### {title}\n")
        out.append("| Сущность | Атрибут | Статус | Примечание / триггер |")
        out.append("|---|---|---|---|")
        for e in members:
            for a in e.get("attributes", []):
                note = a.get("note", "")
                if a.get("trigger"):
                    note = (note + " — " if note else "") + f"триггер: {a['trigger']}"
                out.append(f"| {e['ru']} ({e['id']}) | {a['name']} | {STATUSES[a['status']]} | {note} |")
        out.append("")
    return "\n".join(out)


def placeholder_registry(data: dict) -> str:
    rows = []
    for e in data["entities"]:
        for a in e.get("attributes", []):
            if a["status"] == "placeholder":
                rows.append(f"| {e['ru']} ({e['id']}) | {a['name']} | {a['trigger']} |")
    header = ["| Сущность | Атрибут-плейсхолдер | Триггер решения |", "|---|---|---|"]
    return "\n".join(header + rows)


def stats(data: dict) -> str:
    counts = dict.fromkeys(STATUSES, 0)
    total_attrs = 0
    for e in data["entities"]:
        for a in e.get("attributes", []):
            counts[a["status"]] += 1
            total_attrs += 1
    parts = [f"{STATUSES[s]}: {n}" for s, n in counts.items()]
    return (
        f"Сущностей: {len(data['entities'])}; связей: {len(data['relations'])}; "
        f"атрибутов: {total_attrs} ({'; '.join(parts)})."
    )


def render(data: dict) -> str:
    return "\n".join(
        [
            "# Карта сущностей и атрибутов PretRAGa",
            "",
            "Приложение к [сквозному словарю](entity_glossary.md). СГЕНЕРИРОВАНО из",
            "`entity_map.yaml` скриптом `entity_map_build.py` — руками не править:",
            "источник истины карты — YAML, у файла один писатель (генератор).",
            "Проверки целостности графа (висячие связи, изолированные сущности,",
            "плейсхолдеры без триггера) выполняются при каждой генерации.",
            "",
            stats(data),
            "",
            "## Сводная межгрупповая схема",
            "",
            "Группы как узлы; метка ребра — число связей, пересекающих границу групп.",
            "",
            group_summary_block(data),
            "",
            "## Проекции по группам",
            "",
            "Сущности группы — в рамке; скруглённые узлы — соседи из других групп;",
            "показаны все связи, касающиеся группы.",
            "",
            group_projections(data),
            "## Полный граф связей",
            "",
            mermaid_block(data),
            "",
            "## Атрибуты и их статусы",
            "",
            attribute_tables(data),
            "## Реестр плейсхолдеров",
            "",
            "Ничто из согласованного, но не расписанного, не должно потеряться:",
            "каждый плейсхолдер несёт триггер, при срабатывании которого состав",
            "обязан быть зафиксирован.",
            "",
            placeholder_registry(data),
            "",
        ]
    )


def render_glossary(data: dict) -> str:
    parts = [
        "# Сквозной словарь сущностей PretRAGa",
        "",
        "СГЕНЕРИРОВАНО из `entity_map.yaml` скриптом `entity_map_build.py` — руками",
        "не править. Единственный канал изменения сущностей, терминов, определений",
        "и конвенций — `entity_map.yaml` (конвенции — его блок `conventions`).",
        "Писатель этого файла — генератор; ручная правка ловится проверкой свежести.",
        "",
        str(data["conventions"]).strip(),
        "",
        "---",
    ]
    grouped = _by_group(data)
    for gid, title in data["groups"].items():
        members = grouped.get(gid, [])
        if not members:
            continue
        parts.append(f"\n## {title}")
        for e in members:
            parts.append(f"\n### {e['ru']} ({e['id']})")
            parts.append(str(e["definition"]).strip())
    parts.append("")
    return "\n".join(parts)


def main() -> int:
    data = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    errors = validate(data)
    if errors:
        print("VALIDATION ERRORS:")
        for err in errors:
            print(f"  - {err}")
        return 1
    MAP_VIEW.write_text(render(data), encoding="utf-8")
    GLOSSARY_VIEW.write_text(render_glossary(data), encoding="utf-8")
    print(f"OK: {stats(data)}")
    print(f"written: {MAP_VIEW}")
    print(f"written: {GLOSSARY_VIEW}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
