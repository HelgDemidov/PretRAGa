"""Validate entity_map.yaml as a graph and generate BOTH derived views:
entity_map.md (graph + attribute tables + placeholder registry) and
entity_glossary.md (prose glossary: hand-written conventions preamble +
per-entity definitions from the map).

Source of truth: entity_map.yaml — the ONLY entry channel for entity/term
changes, including definitions. glossary_preamble.md holds cross-cutting
conventions prose (a disjoint domain: no entity entries live there).
This script is the only writer of both generated views — never edit them
by hand; entity_map_check.py detects stale or hand-edited views.

Checks: duplicate ids, dangling relation endpoints, isolated entities,
placeholders without a decision trigger, unknown groups/statuses,
entities without a definition.

Run: .venv/bin/python docs/system_design/design_truth/entity_map_build.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import networkx as nx
import yaml

HERE = Path(__file__).parent
SOURCE = HERE / "entity_map.yaml"
PREAMBLE = HERE / "glossary_preamble.md"
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
            "## Граф связей",
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
        "не править. Единственный канал изменения сущностей, терминов и определений —",
        "`entity_map.yaml`; сквозные конвенции — `glossary_preamble.md`. Писатель",
        "этого файла — генератор; ручная правка ловится проверкой свежести.",
        "",
        PREAMBLE.read_text(encoding="utf-8").strip(),
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
