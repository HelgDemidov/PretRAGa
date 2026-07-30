"""Validate entity_map.yaml as a graph and generate BOTH derived views:
entity_map.md (vocabularies + graph + attribute tables + registries) and
entity_glossary.md (prose glossary: hand-written conventions preamble +
per-entity definitions from the map).

Source of truth: entity_map.yaml — the ONLY hand-written file of the system
and the ONLY entry channel for entity/term changes: entities, attributes,
relations, definitions, the closed vocabularies (kinds, relation types,
triggers) AND the cross-cutting conventions prose (top-level `conventions`
block). This script is the only writer of both generated views — never edit
them by hand; entity_map_check.py detects stale or hand-edited views.

Two tiers of check, deliberately separated:
  errors      — the map is malformed or an entity violates a `forbidden`
                obligation of its kind. A misclassification; fixable without
                any design decision, so it blocks.
  obligations — a `required` obligation of the kind is not met (no identity,
                no version, no placement). Closing it IS a design decision,
                so it is counted and named in a registry instead of blocking.

Run: .venv/bin/python docs/system_design/design_truth/entity_map_build.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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

# Obligation field -> the values it accepts. The obligations themselves live in
# the map (`kinds` block), not here: a new kind is an entry there, not an edit.
OBLIGATION_FIELDS = {
    "anchor": {"required", "forbidden"},
    "identity": {"required", "optional", "forbidden"},
    "version": {"required", "optional"},
    "placement": {"required", "optional", "forbidden"},
    "hosts": {"required", "optional"},
    "attributes": {"required", "forbidden"},
}
MARKS = {"identity", "version"}

# Human labels for the obligations registry, keyed by (field, entity role).
OBLIGATION_LABEL = {
    "identity": "нет атрибута-идентичности (marks: identity)",
    "version": "нет версии: ни своей (marks: version), ни через связь",
    "placement": "не сказано, где хранится (нет связи класса placement)",
    "hosts": "ничего в нём не размещено (не цель ни одной связи placement)",
}


def _attrs(entity: dict) -> list[dict]:
    return entity.get("attributes") or []


def _types_of_class(data: dict, cls: str) -> set[str]:
    return {t for t, spec in data["relation_types"].items() if spec.get("class") == cls}


def _placement_types(data: dict) -> set[str]:
    return _types_of_class(data, "placement")


def layer_rank(data: dict) -> dict[str, int]:
    """Declaration order in the `layers` block IS the dependency order: rank 0
    is the top, and a layer may only depend downward (on a higher rank) or on
    itself."""
    return {layer: i for i, layer in enumerate(data["layers"])}


def anchor_required(data: dict, entity: dict) -> bool:
    """Whether this entity's kind expects a code anchor. Kinds that forbid one
    (a human-written data file, a glossary term) have no code by definition —
    there is no separate per-entity escape hatch."""
    kind = data["kinds"].get(entity.get("kind"), {})
    return bool(kind.get("anchor") == "required")


def _validate_vocabularies(data: dict) -> list[str]:
    errors: list[str] = []
    for block in ("kinds", "relation_classes", "relation_types", "triggers", "layers"):
        if not data.get(block):
            errors.append(f"missing top-level {block} block (closed vocabulary)")
    if errors:
        return errors

    for kid, spec in data["kinds"].items():
        if not str(spec.get("ru", "")).strip():
            errors.append(f"kind {kid} has no ru label")
        for field, allowed in OBLIGATION_FIELDS.items():
            value = spec.get(field)
            if value not in allowed:
                errors.append(
                    f"kind {kid}: obligation {field}={value!r} not in {sorted(allowed)}"
                )

    for tid, spec in data["relation_types"].items():
        if not str(spec.get("ru", "")).strip():
            errors.append(f"relation type {tid} has no ru label")
        if spec.get("class") not in data["relation_classes"]:
            errors.append(f"relation type {tid}: unknown class {spec.get('class')!r}")
        inverse = spec.get("inverse_of")
        if inverse is not None and inverse not in data["relation_types"]:
            errors.append(f"relation type {tid}: unknown inverse_of {inverse!r}")
    return errors


def _validate_forbidden(data: dict, sources: set[str], targets: set[str]) -> list[str]:
    """A `forbidden` obligation broken is a classification error: either the
    kind is wrong or the fact is wrong. Fixable without a design decision."""
    errors: list[str] = []
    for e in data["entities"]:
        kind = data["kinds"].get(e.get("kind"))
        if kind is None:
            continue
        eid = e["id"]
        if kind["anchor"] == "forbidden" and e.get("implements"):
            errors.append(f"{eid}: kind {e['kind']} has no code, but carries implements anchors")
        if kind["identity"] == "forbidden":
            named = [a["name"] for a in _attrs(e) if a.get("marks") == "identity"]
            if named:
                errors.append(f"{eid}: kind {e['kind']} takes no identity, but {named[0]} marks one")
        if kind["placement"] == "forbidden" and eid in sources:
            errors.append(f"{eid}: kind {e['kind']} is not stored anywhere, but has a placement relation")
        if kind["attributes"] == "forbidden" and _attrs(e):
            errors.append(f"{eid}: kind {e['kind']} takes no attributes, but has {len(_attrs(e))}")
        if kind["attributes"] == "required" and not _attrs(e):
            errors.append(f"{eid}: kind {e['kind']} requires attributes, but has none")
    return errors


def _validate_layering(data: dict) -> list[str]:
    """A dependency edge may point down the layer stack or stay inside a layer;
    pointing up inverts the architecture and is an error, not a registry entry:
    either the edge is wrong or the layer assignment is."""
    rank = layer_rank(data)
    layer_of = {e["id"]: e.get("layer") for e in data["entities"]}
    errors: list[str] = []
    for r in data["relations"]:
        if r.get("type") not in _types_of_class(data, "dependency"):
            continue
        src, dst = layer_of.get(r["from"]), layer_of.get(r["to"])
        if src not in rank or dst not in rank:
            continue
        if rank[src] > rank[dst]:
            errors.append(
                f"layering: {r['from']} ({src}) depends upward on {r['to']} ({dst}) "
                f"via {r['type']} — a lower layer may not depend on a higher one"
            )
    return errors


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    groups = data.get("groups", {})
    entities = data.get("entities", [])
    relations = data.get("relations", [])

    if not str(data.get("conventions", "")).strip():
        errors.append("missing top-level conventions block (the glossary preamble prose)")

    errors += _validate_vocabularies(data)
    if errors:
        # Everything below reads the vocabularies; reporting cascade failures
        # from an absent or malformed vocabulary diagnoses nothing.
        return errors

    ids = [e["id"] for e in entities]
    for eid in ids:
        if ids.count(eid) > 1:
            errors.append(f"duplicate entity id: {eid}")
    known = set(ids)

    for e in entities:
        if e.get("group") not in groups:
            errors.append(f"unknown group {e.get('group')!r} on entity {e['id']}")
        if e.get("kind") not in data["kinds"]:
            errors.append(f"unknown kind {e.get('kind')!r} on entity {e['id']}")
        if e.get("layer") not in data["layers"]:
            errors.append(f"unknown layer {e.get('layer')!r} on entity {e['id']}")
        if not str(e.get("definition", "")).strip():
            errors.append(
                f"entity {e['id']} has no definition — an entity that cannot be "
                "defined in prose is not ready to enter the truth"
            )
        for a in _attrs(e):
            if a.get("status") not in STATUSES:
                errors.append(f"unknown status {a.get('status')!r} on {e['id']}.{a.get('name')}")
            if a.get("status") == "placeholder" and not a.get("trigger"):
                errors.append(f"placeholder without trigger: {e['id']}.{a.get('name')}")
            if a.get("trigger") is not None and a["trigger"] not in data["triggers"]:
                errors.append(f"unknown trigger {a['trigger']!r} on {e['id']}.{a['name']}")
            if a.get("marks") is not None and a["marks"] not in MARKS:
                errors.append(f"unknown marks {a['marks']!r} on {e['id']}.{a['name']}")

    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_nodes_from(known)
    placement = _placement_types(data)
    sources: set[str] = set()
    targets: set[str] = set()
    for r in relations:
        for endpoint in (r["from"], r["to"]):
            if endpoint not in known:
                errors.append(f"relation endpoint not a defined entity: {endpoint} ({r['from']} -> {r['to']})")
        if r.get("type") not in data["relation_types"]:
            errors.append(f"unknown relation type {r.get('type')!r} ({r['from']} -> {r['to']})")
        elif r["type"] in placement:
            sources.add(r["from"])
            targets.add(r["to"])
        if r["from"] in known and r["to"] in known:
            graph.add_edge(r["from"], r["to"])

    for node in graph.nodes:
        if graph.degree(node) == 0:
            errors.append(f"isolated entity (no relations): {node}")

    errors += _validate_forbidden(data, sources, targets)
    errors += _validate_layering(data)
    return errors


def obligations(data: dict) -> list[tuple[str, str, str]]:
    """Unmet `required` obligations, as (entity id, kind, what is missing).

    These are NOT errors: closing one means deciding what the identity of an
    entity is, or where a derived layer lives — human design decisions. They
    are counted and named so that they cannot quietly stay open, which is the
    same contract the placeholder registry gives to unspecified attributes."""
    placement = _placement_types(data)
    sources = {r["from"] for r in data["relations"] if r.get("type") in placement}
    targets = {r["to"] for r in data["relations"] if r.get("type") in placement}
    carries_version = {
        e["id"] for e in data["entities"] if any(a.get("marks") == "version" for a in _attrs(e))
    }
    reaches_version = {
        r["from"] for r in data["relations"] if r["to"] in carries_version
    }

    out: list[tuple[str, str, str]] = []
    for e in data["entities"]:
        kind = data["kinds"].get(e.get("kind"))
        if kind is None:
            continue
        eid = e["id"]
        if kind["identity"] == "required" and eid not in {
            x["id"] for x in data["entities"] if any(a.get("marks") == "identity" for a in _attrs(x))
        }:
            out.append((eid, e["kind"], OBLIGATION_LABEL["identity"]))
        if kind["version"] == "required" and eid not in carries_version | reaches_version:
            out.append((eid, e["kind"], OBLIGATION_LABEL["version"]))
        if kind["placement"] == "required" and eid not in sources:
            out.append((eid, e["kind"], OBLIGATION_LABEL["placement"]))
        if kind["hosts"] == "required" and eid not in targets:
            out.append((eid, e["kind"], OBLIGATION_LABEL["hosts"]))
    return out


def _by_group(data: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for e in data["entities"]:
        grouped.setdefault(e["group"], []).append(e)
    return grouped


def _label(data: dict, relation: dict) -> str:
    """A relation may carry its own ru label; the type's label is the default.
    Per-edge labels keep the nuance a coarse type cannot hold."""
    own = relation.get("ru")
    if own:
        return str(own)
    return str(data["relation_types"][relation["type"]]["ru"])


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
        lines.append(f'    {r["from"]} -- "{_label(data, r)}" --> {r["to"]}')
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
        lines.append(f'    {r["from"]} -- "{_label(data, r)}" --> {r["to"]}')
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


def vocabulary_tables(data: dict) -> str:
    members: dict[str, list[str]] = {}
    for e in data["entities"]:
        members.setdefault(e["kind"], []).append(e["id"])

    out = ["### Породы сущностей и их обязательства\n"]
    out.append(
        "| Порода | Смысл | Якорь | Идентичность | Версия | Размещение | Вмещает | Атрибуты | Сущностей |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|")
    for kid, spec in data["kinds"].items():
        cells = " | ".join(str(spec[f]) for f in OBLIGATION_FIELDS)
        out.append(
            f"| `{kid}` ({spec['ru']}) | {spec.get('note', '')} | {cells} | {len(members.get(kid, []))} |"
        )
    out.append("")
    for kid, spec in data["kinds"].items():
        out.append(f"- `{kid}` — {', '.join(members.get(kid, [])) or '—'}")
    out.append("")

    inverse = [t for t, s in data["relation_types"].items() if s.get("inverse_of")]
    used: dict[str, int] = {}
    for r in data["relations"]:
        used[r["type"]] = used.get(r["type"], 0) + 1
    out.append("### Типы связей\n")
    out.append("| Тип | Метка по умолчанию | Класс | Обратный к | Связей |")
    out.append("|---|---|---|---|---|")
    for tid, spec in data["relation_types"].items():
        out.append(
            f"| `{tid}` | {spec['ru']} | `{spec['class']}` | "
            f"{'`' + str(spec['inverse_of']) + '`' if spec.get('inverse_of') else '—'} | {used.get(tid, 0)} |"
        )
    out.append("")
    out.append("Классы связей: " + "; ".join(f"`{c}` — {d}" for c, d in data["relation_classes"].items()) + ".")
    inverted = sum(used.get(t, 0) for t in inverse)
    out.append("")
    out.append(
        f"Записаны в обратную сторону относительно канонической: {inverted} связей из "
        f"{len(data['relations'])} (типы {', '.join('`' + t + '`' for t in inverse)}). "
        "Потребитель, которому важно направление, нормализует их по `inverse_of` — "
        "переориентировать карту руками не требуется."
    )
    out.append("")

    out.append("### Триггеры решений\n")
    out.append("| Триггер | Событие | Плейсхолдеров ждёт |")
    out.append("|---|---|---|")
    waiting: dict[str, int] = {}
    for e in data["entities"]:
        for a in _attrs(e):
            if a.get("trigger"):
                waiting[a["trigger"]] = waiting.get(a["trigger"], 0) + 1
    for tid, label in data["triggers"].items():
        out.append(f"| `{tid}` | {label} | {waiting.get(tid, 0)} |")
    out.append("")
    return "\n".join(out)


def layer_section(data: dict) -> str:
    """The layer stack, its membership, and every dependency edge measured
    against it. Ordering is the contract, so it is printed as a rank."""
    rank = layer_rank(data)
    members: dict[str, list[str]] = {}
    for e in data["entities"]:
        members.setdefault(e["layer"], []).append(e["id"])
    dep_types = _types_of_class(data, "dependency")
    layer_of = {e["id"]: e["layer"] for e in data["entities"]}
    edges = [r for r in data["relations"] if r["type"] in dep_types]

    out = ["| # | Слой | Сущностей | Состав |", "|---|---|---|---|"]
    for layer, title in data["layers"].items():
        ids = members.get(layer, [])
        out.append(f"| {rank[layer]} | {title} (`{layer}`) | {len(ids)} | {', '.join(ids) or '—'} |")
    out.append("")

    crossing: dict[tuple[str, str], int] = {}
    for r in edges:
        key = (layer_of[r["from"]], layer_of[r["to"]])
        crossing[key] = crossing.get(key, 0) + 1
    out.append("```mermaid")
    out.append("flowchart TD")
    for layer, title in data["layers"].items():
        out.append(f'    {layer}["{rank[layer]} — {title}"]')
    for (a, b), n in crossing.items():
        out.append(f'    {a} -- "{n}" --> {b}')
    out.append("```")
    out.append("")
    out.append(f"Связей класса `dependency`: {len(edges)} из {len(data['relations'])}. Все они:")
    out.append("")
    out.append("| Связь | Из слоя | В слой | Вниз по стеку |")
    out.append("|---|---|---|---|")
    for r in edges:
        a, b = layer_of[r["from"]], layer_of[r["to"]]
        direction = "да" if rank[a] < rank[b] else ("свой слой" if a == b else "**НЕТ**")
        out.append(f"| {r['from']} → {r['to']} (`{r['type']}`) | {a} | {b} | {direction} |")
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
            for a in _attrs(e):
                note = a.get("note", "")
                if a.get("trigger"):
                    note = (note + " — " if note else "") + f"триггер: `{a['trigger']}`"
                if a.get("marks"):
                    note = (note + " — " if note else "") + f"**{a['marks']}**"
                out.append(f"| {e['ru']} ({e['id']}) | {a['name']} | {STATUSES[a['status']]} | {note} |")
        out.append("")
    return "\n".join(out)


def placeholder_registry(data: dict) -> str:
    rows = []
    for e in data["entities"]:
        for a in _attrs(e):
            if a["status"] == "placeholder":
                rows.append(f"| {e['ru']} ({e['id']}) | {a['name']} | `{a['trigger']}` |")
    header = ["| Сущность | Атрибут-плейсхолдер | Триггер решения |", "|---|---|---|"]
    return "\n".join(header + rows)


def obligation_registry(data: dict) -> str:
    ru = {e["id"]: e["ru"] for e in data["entities"]}
    rows = [
        f"| {ru[eid]} ({eid}) | `{kind}` | {what} |" for eid, kind, what in obligations(data)
    ]
    header = ["| Сущность | Порода | Незакрытое обязательство |", "|---|---|---|"]
    if not rows:
        return "\n".join(header) + "\n\nОткрытых обязательств нет."
    return "\n".join(header + rows)


def stats(data: dict) -> str:
    counts = dict.fromkeys(STATUSES, 0)
    total_attrs = 0
    for e in data["entities"]:
        for a in _attrs(e):
            counts[a["status"]] += 1
            total_attrs += 1
    parts = [f"{STATUSES[s]}: {n}" for s, n in counts.items()]
    return (
        f"Сущностей: {len(data['entities'])} в {len(data['kinds'])} породах; "
        f"связей: {len(data['relations'])} в {len(data['relation_types'])} типах; "
        f"атрибутов: {total_attrs} ({'; '.join(parts)}); "
        f"открытых обязательств: {len(obligations(data))}."
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
            "плейсхолдеры без триггера, словарные значения, обязательства пород)",
            "выполняются при каждой генерации.",
            "",
            stats(data),
            "",
            "## Словари карты",
            "",
            "Закрытые словари: значение вне словаря — ошибка, новое значение — запись",
            "в `entity_map.yaml`, а не правка скриптов.",
            "",
            vocabulary_tables(data),
            "## Слои и направление зависимости",
            "",
            "Порядок записи слоёв — и есть контракт: слой вправе зависеть от лежащего",
            "ниже и от своего собственного, зависимость вверх — ошибка сборки. Слои —",
            "не группы: группа отвечает «про что это», слой — «кто от кого вправе",
            "зависеть». Ограничен только класс `dependency`; `governance` не ограничен",
            "намеренно — там направление ребра не совпадает с направлением зависимости кода.",
            "",
            layer_section(data),
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
            "## Реестр открытых обязательств",
            "",
            "Обязательство породы, которое сущность не закрывает. Это не поломка карты,",
            "а незанятая позиция: закрыть её — значит решить, чем сущность опознаётся,",
            "чем инвалидируется или где лежит. Решение человеческое, поэтому реестр",
            "считает и называет, но не блокирует.",
            "",
            obligation_registry(data),
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
            kind = data["kinds"][e["kind"]]
            parts.append(f"\n### {e['ru']} ({e['id']})")
            parts.append(
                f"*Порода: {kind['ru']} (`{e['kind']}`) — {kind.get('note', '')}. "
                f"Слой: {data['layers'][e['layer']]} (`{e['layer']}`).*\n"
            )
            parts.append(str(e["definition"]).strip())
    parts.append("")
    return "\n".join(parts)


def main() -> int:
    data: dict[str, Any] = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
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
