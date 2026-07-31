# План реализации: замена системы контроля архитектурной истины

> **Для исполнителя:** реализовывать по задачам, через
> `superpowers:subagent-driven-development` либо `superpowers:executing-plans`.
> Шаги помечены чекбоксами `- [ ]`.

**Цель:** заменить `docs/system_design/design_truth/` (4830 строк, две живые
проверки из девятнадцати, обе мертвы до появления кода) на рукописный
`domain.yaml` с одним генерируемым словарём, контракт колец `import-linter` и
чекер порядка 200 строк — так, чтобы каждая проверка читала настоящий код с
первого модуля.

**Архитектура:** три артефакта с разными писателями (карта домена, контракт
импортов, бэклог) и три инструмента (`truth_check.py`, `lint-imports`, `mypy`).
Слой модуля — его каталог: `src/pretraga/{domain,usecases,adapters,entrypoints}`.
Якорь кода не пишется руками, а выводится сверкой имени понятия с именем класса
в слое домена.

**Стек:** Python 3.12, PyYAML (строгий загрузчик), `ast` из стандартной
библиотеки, pytest + hypothesis, import-linter 2.13, mypy, ruff, uv.

**Источник:** [spec.md](spec.md), `draft v3`, одобрена.

## Глобальные ограничения

- **Код — только английский**: идентификаторы, комментарии, докстринги
  (`CLAUDE.md` §11). Документы этого репозитория — русские.
- **Никаких сумм, тарифов и оценок стоимости** в отслеживаемых артефактах,
  коммитах и докстрингах (`CLAUDE.md` §11).
- **Команда гейта не несёт списка путей.** Инструменты находят цели сами от
  корня; git решает, что наше.
- **Пути — аргументы функций со значениями по умолчанию на продакшн**, не
  константы модуля в теле функции. Тест обязан передать временные пути явно.
- **Породы ровно четыре**: `entity`, `value`, `derived`, `port`. Словарь пород
  живёт в коде — потому что код по нему ветвится (`port` управляет счётчиком
  нереализованных портов). Всё прочее, чем оперирует модель, остаётся данными.
- **`pyproject.toml` не меняет состав зависимостей.** Меняются только
  `[tool.coverage.run] source` и добавляется `[tool.importlinter]`.
- **Корневой пакет — `pretraga`.** Кольца снаружи внутрь:
  `entrypoints → adapters → usecases → domain`.
- **Ветка одна:** `feature/design-truth-replacement`. Спека называет 7 коммитов;
  план разворачивает её первый пункт в пять задач, потому что инструмент
  строится по TDD и у каждого шага свой тестовый цикл. Граница ревью та же.

---

## Структура файлов

**Создаются:**

| Файл | Ответственность |
|---|---|
| `docs/system_design/domain.yaml` | единственный рукописный источник модели домена |
| `docs/system_design/domain_glossary.md` | генерируется из него; писатель — инструмент |
| `tools/truth_check.py` | разбор, валидация, генерация, сверка с кодом, хук |
| `tools/conftest.py` | герметичность: снимок управляемого дерева вокруг каждого теста |
| `tools/test_truth_check.py` | тесты чекера |
| `tools/test_mutations.py` | мутационный стенд |
| `src/pretraga/{domain,usecases,adapters,entrypoints}/__init__.py` | четыре кольца |

**Меняются:** `pyproject.toml`, `.github/workflows/ci.yml`, `CLAUDE.md` §10,
`docs/system_design/architectural_vision.md` (пять мест, см. задачу 9),
`docs/backlog/backlog.md`.

**Удаляются:** `docs/system_design/design_truth/` (8 файлов),
`docs/backlog/ports_and_layers_brief.md`.

**Оценка объёма разошлась со спекой:** §4 спеки называет «порядка 150 строк»;
с докстринговым режимом остальных модулей репозитория выходит порядка 200.
Расхождение названо здесь, а не тихо принято.

---

## Задача 1: загрузчик и валидатор карты

Спека: коммит 1, проверки §4.1–§4.2.

**Файлы:**
- Создать: `tools/truth_check.py`, `tools/conftest.py`, `tools/test_truth_check.py`

**Интерфейсы:**
- Отдаёт дальше: `load(source: Path) -> dict`, `validate(data: dict) -> list[str]`,
  `KINDS: dict[str, str]`, `REQUIRED_FIELDS: tuple[str, ...]`,
  константы `SOURCE`, `VIEW`, `SRC` (пути на продакшн).

- [ ] **Шаг 1: герметичная обвязка тестов**

Создать `tools/conftest.py`. Это перенос механизма из
`docs/system_design/design_truth/conftest.py` с одной содержательной правкой:
сторожим не папку инструмента, а то, что инструмент умеет переписать.

```python
"""Pytest wiring for the truth tool.

Hermeticity is structural, not disciplinary. truth_check's paths default to the
REAL map and the REAL glossary, so a test that calls main() by accident would
silently rewrite production. The autouse fixture below snapshots the whole
governed tree around every test — files, not a remembered list of files — and
fails loudly naming what moved.
"""
from __future__ import annotations

import hashlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WATCHED = (ROOT / "docs" / "system_design", ROOT / "src")

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _snapshot() -> dict[str, str]:
    out: dict[str, str] = {}
    for root in WATCHED:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            out[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


@pytest.fixture(autouse=True)
def production_untouched() -> Iterator[None]:
    before = _snapshot()
    yield
    after = _snapshot()
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    assert not (added or removed or changed), (
        "a test wrote into production truth artifacts: "
        f"changed={changed} added={added} removed={removed}"
    )
```

- [ ] **Шаг 2: написать падающие тесты**

Создать `tools/test_truth_check.py`:

```python
"""Tests for the domain-truth tool.

What is worth testing is the CHECKS, not the map: the map is curated data whose
content changes by design decision, so pinning its numbers would make the oracle
track the data instead of constraining the code.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

import truth_check as tc

MINIMAL = """\
preamble: |
  Терминологические конвенции.
triggers:
  ingest_spec: "спецификация ингеста"
chains:
  provenance:
    ru: "цепочка улики"
    hops: [Deliverable, ProvenanceAnchor]
entities:
  - id: Deliverable
    ru: "Деливерабл"
    kind: entity
    definition: |
      Итоговый документ.
    open:
      - {question: "состав приёмки", trigger: ingest_spec}
  - id: ProvenanceAnchor
    ru: "Якорь провенанса"
    kind: value
    definition: |
      Публикуемый стабильный адрес улики.
"""


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "domain.yaml"
    path.write_text(MINIMAL, encoding="utf-8")
    return path


def test_minimal_map_validates(source: Path) -> None:
    assert tc.validate(tc.load(source)) == []


def test_duplicate_key_raises_instead_of_losing_a_field(tmp_path: Path) -> None:
    """Stock PyYAML resolves a duplicate key in favour of the last one without a
    word. In a hand-written source of truth that is silent data loss."""
    doc = "preamble: a\npreamble: b\n"
    path = tmp_path / "dup.yaml"
    path.write_text(doc, encoding="utf-8")
    with pytest.raises(yaml.constructor.ConstructorError, match="duplicate key"):
        tc.load(path)
    assert yaml.safe_load(doc), "stock PyYAML still accepts it silently"


@pytest.mark.parametrize("field", sorted(tc.REQUIRED_FIELDS))
def test_missing_required_field_is_rejected(source: Path, field: str) -> None:
    data = tc.load(source)
    data["entities"][0][field] = "  "
    assert any(f"field {field}" in e for e in tc.validate(data))


def test_unknown_kind_is_rejected(source: Path) -> None:
    data = tc.load(source)
    data["entities"][0]["kind"] = "nonesuch"
    assert any("unknown kind 'nonesuch'" in e for e in tc.validate(data))


def test_duplicate_id_is_rejected(source: Path) -> None:
    data = tc.load(source)
    data["entities"].append(dict(data["entities"][0]))
    assert any("duplicate id: Deliverable" in e for e in tc.validate(data))


def test_unknown_trigger_is_rejected(source: Path) -> None:
    data = tc.load(source)
    data["entities"][0]["open"][0]["trigger"] = "nonesuch"
    assert any("unknown trigger 'nonesuch'" in e for e in tc.validate(data))


def test_open_item_without_a_question_is_rejected(source: Path) -> None:
    data = tc.load(source)
    data["entities"][0]["open"][0]["question"] = ""
    assert any("open item with no question" in e for e in tc.validate(data))


def test_missing_preamble_is_rejected(source: Path) -> None:
    data = tc.load(source)
    data["preamble"] = "   "
    assert any("no preamble" in e for e in tc.validate(data))


def test_chain_hop_outside_the_map_is_rejected(source: Path) -> None:
    data = tc.load(source)
    data["chains"]["provenance"]["hops"] = ["Deliverable", "Nowhere"]
    assert any("Nowhere is not a declared concept" in e for e in tc.validate(data))


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda d: d["chains"]["provenance"].update(ru="  "), "no ru label"),
        (lambda d: d["chains"]["provenance"].update(hops=["Deliverable"]), "at least two hops"),
    ],
    ids=["no label", "too short"],
)
def test_malformed_chain_is_rejected(source: Path, mutate: Any, expected: str) -> None:
    data = tc.load(source)
    mutate(data)
    assert any(expected in e for e in tc.validate(data))


def test_an_unused_trigger_is_legal(source: Path) -> None:
    """The old system required a vocabulary value and its first carrier in one
    commit; that was measured friction, not an invariant."""
    data = tc.load(source)
    data["triggers"]["enrichment_spec"] = "спецификация обогащения"
    assert tc.validate(data) == []
```

- [ ] **Шаг 3: убедиться, что тесты падают**

Запустить: `.venv/bin/python -m pytest tools -q`
Ожидается: сбор падает с `ModuleNotFoundError: No module named 'truth_check'`.

- [ ] **Шаг 4: минимальная реализация**

Создать `tools/truth_check.py`:

```python
"""Domain-truth conformance checker.

`domain.yaml` is the curated truth and the machine never rewrites it: this tool
diffs observable reality against it and fails loudly on divergence. Resolution
is always a human decision — fix the code, or edit the map deliberately.

Dependency direction is NOT checked here. That is import-linter's job, on real
imports, with the contracts declared in pyproject.toml.

Paths are arguments whose defaults point at production, never constants read
inside a function: a test must pass temporary paths explicitly, so an accidental
main() cannot rewrite the real glossary.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / "docs" / "system_design" / "domain.yaml"
VIEW = ROOT / "docs" / "system_design" / "domain_glossary.md"
SRC = ROOT / "src" / "pretraga"

# A code-level enumeration is justified only where the code BRANCHES on the
# value. It does: `port` drives the unimplemented-port counter, and the four
# kinds each carry a different obligation in prose. Everything else the model
# operates with — triggers, chain names, concept ids — stays data in the map.
KINDS: dict[str, str] = {
    "entity": "сущность с жизненным циклом: идентификатор чеканится один раз и не пересчитывается",
    "value": "неизменяемое значение: ключ равен хэшу содержимого",
    "derived": "производное: восстановимо из источника, назад не пишет",
    "port": "порт: интерфейс, объявленный доменом и реализуемый снаружи",
}
REQUIRED_FIELDS = ("id", "ru", "kind", "definition")


class _Strict(yaml.SafeLoader):
    """Loader that refuses a duplicate mapping key."""


def _no_duplicate_keys(loader: object, node: object, deep: bool = False) -> dict:
    """PyYAML resolves a duplicate key silently in favour of the last one. In a
    hand-written source of truth that is silent data loss: a careless paste can
    delete a definition and the file stays valid YAML."""
    mapping: dict = {}
    for key_node, value_node in node.value:  # type: ignore[attr-defined]
        key = loader.construct_object(key_node, deep=deep)  # type: ignore[attr-defined]
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,  # type: ignore[attr-defined]
                f"duplicate key {key!r} — the later value would silently win",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)  # type: ignore[attr-defined]
    return mapping


_Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)


def load(source: Path = SOURCE) -> dict:
    """The ONE place the map is parsed, so generator, checker and tests all get
    the same semantics."""
    parsed: dict = yaml.load(source.read_text(encoding="utf-8"), Loader=_Strict)
    return parsed


def validate(data: dict) -> list[str]:
    """Structural errors only — everything here is fixable without a design
    decision, which is why it blocks."""
    errors: list[str] = []
    if not str(data.get("preamble", "")).strip():
        errors.append("no preamble: the terminological conventions are part of the truth")

    triggers = data.get("triggers") or {}
    seen: set[str] = set()
    for entity in data.get("entities") or []:
        eid = str(entity.get("id") or "<no id>")
        if eid in seen:
            errors.append(f"duplicate id: {eid}")
        seen.add(eid)
        for field in REQUIRED_FIELDS:
            if not str(entity.get(field, "")).strip():
                errors.append(f"{eid}: field {field} is empty or missing")
        if entity.get("kind") not in KINDS:
            errors.append(
                f"{eid}: unknown kind {entity.get('kind')!r}, expected one of {sorted(KINDS)}"
            )
        for item in entity.get("open") or []:
            if not str(item.get("question", "")).strip():
                errors.append(f"{eid}: an open item with no question")
            trigger = item.get("trigger")
            if trigger is not None and trigger not in triggers:
                errors.append(f"{eid}: unknown trigger {trigger!r}")

    for cid, spec in (data.get("chains") or {}).items():
        if not str(spec.get("ru", "")).strip():
            errors.append(f"chain {cid}: no ru label")
        hops = spec.get("hops") or []
        if len(hops) < 2:
            errors.append(f"chain {cid}: needs at least two hops")
        for hop in hops:
            if hop not in seen:
                errors.append(f"chain {cid}: {hop} is not a declared concept")
    return errors
```

- [ ] **Шаг 5: убедиться, что тесты проходят**

Запустить: `.venv/bin/python -m pytest tools -q`
Ожидается: 12 passed.

- [ ] **Шаг 6: линт и типы**

Запустить: `.venv/bin/python -m ruff check tools && .venv/bin/python -m mypy tools`
Ожидается: чисто. При жалобах mypy на конструкторы PyYAML — точечные `type: ignore`
с кодом ошибки, как уже сделано в коде выше; глобального ослабления не вводить.

- [ ] **Шаг 7: коммит**

```bash
git add tools/truth_check.py tools/conftest.py tools/test_truth_check.py
git commit -m "feat(truth): строгий загрузчик и валидатор карты домена"
```

---

## Задача 2: `domain.yaml` — перенос содержания

Спека: коммит 1, §2 и §6 (перераспределение).

**Файлы:**
- Создать: `docs/system_design/domain.yaml`
- Изменить: `tools/test_truth_check.py` (добавить регрессию на реальную карту)

**Интерфейсы:**
- Отдаёт дальше: реальную карту по пути `SOURCE`; ~20 понятий пород
  `entity`/`value`/`derived`, ноль понятий породы `port` (порты появятся вместе
  с первым сценарием).

- [ ] **Шаг 1: выписать состав переноса**

Из `docs/system_design/design_truth/entity_map.yaml` переносятся определения
понятий пород `data` и `derived` — двадцать штук:

`AcquisitionChannel`, `AcquisitionAct`, `RawPayload`, `AcquisitionHint`,
`Document`, `ContentVersion`, `CanonicalText`, `ConversionRecord`,
`ProvenanceAnchor`, `Fragment`, `Translation`, `Claim`, `TypedReference`,
`WorldEntity`, `GraphLayer`, `VerbalizedGraphContext`, `VectorIndex`,
`LexicalIndex`, `DerivationManifest`, `Deliverable`.

Породы назначаются так: неизменяемое, ключ которого есть хэш содержимого, —
`value` (`RawPayload`, `ContentVersion`, `CanonicalText`, `ProvenanceAnchor`);
восстановимое из источника — `derived` (`AcquisitionHint`, `Fragment`,
`Translation`, `GraphLayer`, `VerbalizedGraphContext`, `VectorIndex`,
`LexicalIndex`); остальное — `entity`.

**НЕ переносятся** (их содержание уезжает в задаче 9 и в спеки слоёв):
12 процессов, 3 хранилища, 2 файла данных, `Connector`, термин `Corpus`.

- [ ] **Шаг 2: написать карту**

Создать `docs/system_design/domain.yaml`. Шапка и первые два понятия — образец
формы; остальные восемнадцать пишутся по нему, определения переносятся из
`entity_map.yaml` дословно, без пересказа.

```yaml
# Модель домена PretRAGa — ЕДИНСТВЕННЫЙ рукописный источник.
# Машина сюда не пишет: расхождение разрешает человек, а не перезапись.
# Словарь domain_glossary.md генерируется отсюда инструментом tools/truth_check.py.
#
# Разделение языков по назначению поля: английский — всё, что является или
# станет символом в коде (id, ключи триггеров и цепочек); русский — всё, что
# читает человек (ru, definition, question, preamble).
#
# Поля понятия: id / ru / kind / definition обязательны; open — по месту.
# Породы: entity | value | derived | port.

preamble: |
  ## Терминологические конвенции

  - Слово **«источник»** в модели данных не используется: в живой речи оно означает
    отдельную публикацию, и потому зарезервировано за человеческим языком. Поток
    документов из настроенного места добычи называется **каналом добычи**.
  - **«Кандидат»** — не понятие, а стадия жизненного цикла Документа (до приёмки).
  - **«Корпус»** — не хранимое, а предикат состояния: все активные документы реестра.
    Ни идентификатора, ни конфигурации, ни собственного жизненного цикла.
  - Код — только английский; в скобках у каждого понятия — его имя в коде.

triggers:
  acquisition_spec:               "спецификация добычи"
  ingest_spec:                    "спецификация ингеста"
  conversion_spec:                "спецификация конвертации"
  enrichment_spec:                "спецификация обогащения"
  synthesis_workshop_spec:        "спецификация мастерской синтеза"
  first_vocabulary_consumer_spec: "первая спецификация, использующая словарь"

# Несущие цепочки — утверждения, которые видение §6 объявляет конструкцией, а не
# описанием. Пока моделей нет, проверка инертна и говорит об этом; как только оба
# конца звена появятся в коде, соседняя пара сверяется по полям реальных типов.
chains:
  provenance_evidence:
    ru: "цепочка улики: от деливерабла до сырья, оба звена версионированы"
    hops: [Deliverable, Claim, ProvenanceAnchor, CanonicalText, ConversionRecord, RawPayload]
  provenance_stamp:
    ru: "штамп деливерабла: манифест деривации и коммит реестра"
    hops: [Deliverable, DerivationManifest]

entities:
  - id: Document
    ru: "Документ"
    kind: entity
    definition: |
      Единица корпуса; сущность с историей (уровень «работы»). Идентичность —
      чеканная, выдаётся на стадии кандидата. Сопоставимость — через
      схематизированные координаты происхождения: пары «схема + значение» (ELI,
      CELEX, номер в реестре, канонический URL). Жизненный цикл — закрытое
      множество: кандидат → активен → выведен; приёмка автоматическая, вывод —
      решение человека, внесённое командой. Классификационные атрибуты —
      значения контролируемых словарей, заполняются машинно. Класс
      авторитетности не хранится: вычисляется таблицей правил.
    open:
      - {question: "какие координатные схемы дают авто-склейку; URL — никогда", trigger: ingest_spec}
      - {question: "формула машинного счётчика полноты метаданных", trigger: enrichment_spec}

  - id: ProvenanceAnchor
    ru: "Якорь провенанса"
    kind: value
    definition: |
      Тройка (версия содержимого, хэш канонического текста, символьный интервал) —
      публикуемый стабильный адрес улики. Не зависит от нарезки на фрагменты и её
      версий. Якоря живут только в оригинале: перевод носителем якорей не бывает.
```

⚠ `provenance_stamp` в старой карте имел три звена
(`Deliverable → DerivationManifest → CorpusRegistry`); `CorpusRegistry` —
хранилище и в модель домена не переносится, поэтому цепочка укорачивается до
двух звеньев. Это осознанное сужение, а не потеря: коммит реестра остаётся
полем внутри `DerivationManifest`.

- [ ] **Шаг 3: добавить регрессию на реальную карту**

Дописать в `tools/test_truth_check.py`:

```python
def test_committed_map_validates() -> None:
    """The map is curated data: this pins that it PARSES and is structurally
    sound, never how many concepts it holds."""
    assert tc.validate(tc.load()) == []


def test_every_declared_kind_is_used() -> None:
    """A kind nobody carries is speculative generality with a validation cost.
    `port` is exempt: ports appear with the first use case, and declaring the
    kind early costs nothing because the code branches on it either way."""
    used = {e["kind"] for e in tc.load()["entities"]}
    assert used <= set(tc.KINDS)
    assert used >= {"entity", "value", "derived"}
```

- [ ] **Шаг 4: прогнать**

Запустить: `.venv/bin/python -m pytest tools -q`
Ожидается: 14 passed. При падении — читать имя понятия в сообщении, чинить карту.

- [ ] **Шаг 5: коммит**

```bash
git add docs/system_design/domain.yaml tools/test_truth_check.py
git commit -m "feat(truth): перенести двадцать доменных понятий в domain.yaml"
```

---

## Задача 3: генерация словаря и проверка свежести

Спека: коммит 1, проверка §4.4.

**Файлы:**
- Изменить: `tools/truth_check.py`, `tools/test_truth_check.py`
- Создать: `docs/system_design/domain_glossary.md` (генерацией, не руками)

**Интерфейсы:**
- Потребляет: `load`, `validate`, `KINDS` из задачи 1.
- Отдаёт дальше: `render(data: dict) -> str`,
  `build(source: Path, view: Path) -> int`.

- [ ] **Шаг 1: написать падающие тесты**

```python
def test_render_is_deterministic(source: Path) -> None:
    data = tc.load(source)
    assert tc.render(data) == tc.render(tc.load(source))


def test_render_names_every_concept_and_its_kind(source: Path) -> None:
    text = tc.render(tc.load(source))
    for entity in tc.load(source)["entities"]:
        assert f"## {entity['ru']} (`{entity['id']}`)" in text
        assert tc.KINDS[entity["kind"]] in text


def test_render_carries_the_preamble_and_the_chains(source: Path) -> None:
    text = tc.render(tc.load(source))
    assert "Терминологические конвенции" in text
    assert "цепочка улики" in text
    assert "`Deliverable` → `ProvenanceAnchor`" in text


def test_render_lists_open_questions_with_their_trigger(source: Path) -> None:
    text = tc.render(tc.load(source))
    assert "ОТКРЫТО: состав приёмки — триггер: `ingest_spec`" in text


def test_build_writes_the_view_and_check_then_passes(source: Path, tmp_path: Path) -> None:
    view = tmp_path / "glossary.md"
    assert tc.build(source, view) == 0
    assert view.exists()
    errors, _ = tc.check(source, view, tmp_path / "nosrc")
    assert errors == []


def test_missing_view_is_caught(source: Path, tmp_path: Path) -> None:
    errors, _ = tc.check(source, tmp_path / "absent.md", tmp_path / "nosrc")
    assert any("is missing" in e for e in errors)


def test_hand_edited_view_is_caught(source: Path, tmp_path: Path) -> None:
    view = tmp_path / "glossary.md"
    tc.build(source, view)
    view.write_text(view.read_text(encoding="utf-8") + "\nконтрабанда\n", encoding="utf-8")
    errors, _ = tc.check(source, view, tmp_path / "nosrc")
    assert any("stale or hand-edited" in e for e in errors)


def test_build_refuses_to_write_from_a_broken_map(tmp_path: Path) -> None:
    """A generator that renders an invalid map produces a plausible-looking lie."""
    broken = tmp_path / "broken.yaml"
    broken.write_text("preamble: x\nentities:\n  - id: A\n", encoding="utf-8")
    view = tmp_path / "glossary.md"
    assert tc.build(broken, view) == 1
    assert not view.exists()
```

- [ ] **Шаг 2: убедиться, что падают**

Запустить: `.venv/bin/python -m pytest tools -q -k "render or build or view"`
Ожидается: FAIL, `module 'truth_check' has no attribute 'render'`.

- [ ] **Шаг 3: реализовать**

Дописать в `tools/truth_check.py`:

```python
def render(data: dict) -> str:
    """The one generated view. Its writer is this function; a hand edit is
    caught by the freshness check, so the file has exactly one author."""
    out = [
        "# Словарь домена PretRAGa",
        "",
        "СГЕНЕРИРОВАНО из `domain.yaml` инструментом `tools/truth_check.py` —",
        "руками не править: у файла один писатель, ручная правка ловится",
        "проверкой свежести.",
        "",
        str(data["preamble"]).strip(),
        "",
        "---",
        "",
    ]
    for entity in data["entities"]:
        out += [
            f"## {entity['ru']} (`{entity['id']}`)",
            "",
            f"*{KINDS[entity['kind']]}*",
            "",
            str(entity["definition"]).strip(),
            "",
        ]
        for item in entity.get("open") or []:
            trigger = item.get("trigger")
            tail = f" — триггер: `{trigger}`" if trigger else ""
            out.append(f"- ОТКРЫТО: {item['question']}{tail}")
        if entity.get("open"):
            out.append("")

    chains = data.get("chains") or {}
    if chains:
        out += ["## Несущие цепочки", ""]
        for cid, spec in chains.items():
            out += [
                f"**`{cid}`** — {spec['ru']}",
                "",
                " → ".join(f"`{hop}`" for hop in spec["hops"]),
                "",
            ]
    return "\n".join(out)


def build(source: Path = SOURCE, view: Path = VIEW) -> int:
    data = load(source)
    errors = validate(data)
    if errors:
        print(f"DOMAIN TRUTH: {len(errors)} error(s) — nothing written")
        for error in errors:
            print(f"  - {error}")
        return 1
    view.write_text(render(data), encoding="utf-8")
    print(f"written: {view}")
    return 0


def check(source: Path = SOURCE, view: Path = VIEW, src: Path = SRC) -> tuple[list[str], list[str]]:
    """Returns (errors, info). Errors block; info is counted and named because
    closing one is a human design decision, not a repair."""
    data = load(source)
    errors = validate(data)
    if errors:
        # Everything below assumes a well-formed map; reporting cascade noise
        # from a malformed one diagnoses nothing.
        return errors, []
    info: list[str] = []
    if not view.exists():
        errors.append(f"{view.name} is missing — run truth_check.py --build")
    elif view.read_text(encoding="utf-8") != render(data):
        errors.append(f"{view.name} is stale or hand-edited — run truth_check.py --build")
    return errors, info
```

- [ ] **Шаг 4: прогнать тесты**

Запустить: `.venv/bin/python -m pytest tools -q`
Ожидается: 22 passed.

- [ ] **Шаг 5: собрать настоящий словарь**

Запустить: `.venv/bin/python tools/truth_check.py --build`
⚠ Разбор аргументов появится в задаче 6. До неё собрать так:
`.venv/bin/python -c "import sys; sys.path.insert(0,'tools'); import truth_check as t; t.build()"`
Ожидается: `written: …/domain_glossary.md`.

- [ ] **Шаг 6: коммит**

```bash
git add tools/truth_check.py tools/test_truth_check.py docs/system_design/domain_glossary.md
git commit -m "feat(truth): генерировать словарь домена и ловить его протухание"
```

---

## Задача 4: сверка карты с кодом

Спека: коммит 1, проверки §4.3, §4.5–§4.7. Это разворот стены.

**Файлы:**
- Изменить: `tools/truth_check.py`, `tools/test_truth_check.py`

**Интерфейсы:**
- Потребляет: `load`, `validate`, `check` из задач 1 и 3.
- Отдаёт дальше: `trace(data: dict, src: Path) -> tuple[list[str], list[str]]`,
  `_public_classes(directory: Path) -> dict[str, ast.ClassDef]`.

- [ ] **Шаг 1: написать падающие тесты**

```python
def _package(root: Path, ring: str, module: str, body: str) -> Path:
    """A throwaway src/pretraga tree inside tmp_path. Tests never touch the real
    one: the entry points default to production paths."""
    directory = root / "pretraga" / ring
    directory.mkdir(parents=True, exist_ok=True)
    (root / "pretraga" / "__init__.py").touch()
    (directory / "__init__.py").touch()
    path = directory / f"{module}.py"
    path.write_text(body, encoding="utf-8")
    return path


def test_concept_without_code_is_counted_not_blocked(source: Path, tmp_path: Path) -> None:
    """The central inversion. Designing ahead of code is the normal state; the
    old system blocked on it and could not be unblocked except by anchoring
    every concept at once."""
    src = tmp_path / "src"
    _package(src, "domain", "anchor", "class ProvenanceAnchor:\n    pass\n")
    errors, info = tc.trace(tc.load(source), src / "pretraga")
    assert errors == []
    assert any("1 of 2 concepts have no code yet" in line for line in info)
    assert any("Deliverable" in line for line in info)


def test_undeclared_domain_type_blocks(source: Path, tmp_path: Path) -> None:
    src = tmp_path / "src"
    _package(src, "domain", "stray", "class SmuggledConcept:\n    pass\n")
    errors, _ = tc.trace(tc.load(source), src / "pretraga")
    assert any("undeclared domain type in code: SmuggledConcept" in e for e in errors)


def test_private_class_in_the_domain_layer_is_ignored(source: Path, tmp_path: Path) -> None:
    src = tmp_path / "src"
    _package(src, "domain", "helper", "class _Helper:\n    pass\n")
    errors, _ = tc.trace(tc.load(source), src / "pretraga")
    assert errors == []


def test_absent_source_tree_is_silent(source: Path, tmp_path: Path) -> None:
    errors, info = tc.trace(tc.load(source), tmp_path / "nothing")
    assert errors == []
    assert any("2 of 2 concepts have no code yet" in line for line in info)


def test_unimplemented_port_is_counted_not_blocked(tmp_path: Path) -> None:
    source = tmp_path / "with_port.yaml"
    source.write_text(
        MINIMAL + """\
  - id: DocumentRepository
    ru: "Порт: хранилище документов"
    kind: port
    definition: |
      Домен объявляет, что ему нужно от хранения.
""",
        encoding="utf-8",
    )
    src = tmp_path / "src"
    _package(src, "domain", "ports", "class DocumentRepository:\n    pass\n")
    errors, info = tc.trace(tc.load(source), src / "pretraga")
    assert errors == []
    assert any("DocumentRepository" in line and "not implemented" in line for line in info)


def test_implemented_port_leaves_the_counter(tmp_path: Path) -> None:
    source = tmp_path / "with_port.yaml"
    source.write_text(
        MINIMAL + """\
  - id: DocumentRepository
    ru: "Порт: хранилище документов"
    kind: port
    definition: |
      Домен объявляет, что ему нужно от хранения.
""",
        encoding="utf-8",
    )
    src = tmp_path / "src"
    _package(src, "domain", "ports", "class DocumentRepository:\n    pass\n")
    _package(src, "adapters", "git", "class GitRegistry(DocumentRepository):\n    pass\n")
    _, info = tc.trace(tc.load(source), src / "pretraga")
    assert not any("not implemented" in line for line in info)
```

- [ ] **Шаг 2: убедиться, что падают**

Запустить: `.venv/bin/python -m pytest tools -q -k "trace or port or undeclared or without_code"`
Ожидается: FAIL, `module 'truth_check' has no attribute 'trace'`.

- [ ] **Шаг 3: реализовать**

Дописать в `tools/truth_check.py`:

```python
def _public_classes(directory: Path) -> dict[str, ast.ClassDef]:
    """Public classes declared directly in a package tree. A domain concept is
    a type, so classes are the whole surface; a leading underscore marks a
    helper and is skipped."""
    found: dict[str, ast.ClassDef] = {}
    if not directory.exists():
        return found
    for py in sorted(directory.rglob("*.py")):
        for node in ast.parse(py.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                found[node.name] = node
    return found


def _base_class_names(src: Path, exclude: Path) -> set[str]:
    """Names used as a base class anywhere under src/ EXCEPT the excluded
    directory — that is what "someone outside the domain implements this port"
    looks like in the syntax tree."""
    names: set[str] = set()
    if not src.exists():
        return names
    for py in sorted(src.rglob("*.py")):
        if exclude in py.parents:
            continue
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                if isinstance(base, ast.Name):
                    names.add(base.id)
                elif isinstance(base, ast.Attribute):
                    names.add(base.attr)
    return names


def trace(data: dict, src: Path = SRC) -> tuple[list[str], list[str]]:
    """The only check that looks at reality, and its direction is the opposite
    of the system this replaces.

    BLOCKS on a public type in the domain layer that the map does not declare —
    a concept that entered the system past a decision, fixable in one edit.
    COUNTS a concept with no code yet: designing ahead of code is the normal
    state, and blocking on it can only be cleared by anchoring everything at
    once."""
    domain_dir = src / "domain"
    declared = {e["id"] for e in data["entities"]}
    in_code = _public_classes(domain_dir)

    errors = [
        f"undeclared domain type in code: {name} — rename it, or add it to domain.yaml"
        for name in sorted(set(in_code) - declared)
    ]
    info: list[str] = []
    missing = sorted(declared - set(in_code))
    if missing:
        info.append(
            f"{len(missing)} of {len(declared)} concepts have no code yet: {', '.join(missing)}"
        )
    ports = {e["id"] for e in data["entities"] if e["kind"] == "port"}
    implemented = _base_class_names(src, exclude=domain_dir)
    unimplemented = sorted((ports & set(in_code)) - implemented)
    if unimplemented:
        info.append(
            "ports declared in code but not implemented outside the domain layer: "
            + ", ".join(unimplemented)
        )
    return errors, info
```

Затем подключить в `check()` — заменить тело после проверки свежести:

```python
    trace_errors, trace_info = trace(data, src)
    errors += trace_errors
    info += trace_info

    open_items = [item for e in data["entities"] for item in e.get("open") or []]
    if open_items:
        by_trigger: dict[str, int] = {}
        for item in open_items:
            key = str(item.get("trigger") or "—")
            by_trigger[key] = by_trigger.get(key, 0) + 1
        listed = ", ".join(f"{name}: {count}" for name, count in sorted(by_trigger.items()))
        info.append(f"{len(open_items)} open question(s) — {listed}")
    return errors, info
```

- [ ] **Шаг 4: прогнать**

Запустить: `.venv/bin/python -m pytest tools -q`
Ожидается: 29 passed.

- [ ] **Шаг 5: коммит**

```bash
git add tools/truth_check.py tools/test_truth_check.py
git commit -m "feat(truth): сверять карту с кодом — блокирует код без понятия, не понятие без кода"
```

---

## Задача 5: несущие цепочки по аннотациям типов

Спека: коммит 1, проверка §4.8.

**Файлы:**
- Изменить: `tools/truth_check.py`, `tools/test_truth_check.py`

**Интерфейсы:**
- Потребляет: `_public_classes` из задачи 4.
- Отдаёт дальше: `chain_state(data: dict, src: Path) -> tuple[list[str], list[str]]`.

- [ ] **Шаг 1: написать падающие тесты**

```python
CHAIN_OK = '''\
from dataclasses import dataclass


@dataclass(frozen=True)
class ProvenanceAnchor:
    span: tuple[int, int]


@dataclass(frozen=True)
class Deliverable:
    evidence: list[ProvenanceAnchor]
'''

CHAIN_BROKEN = '''\
from dataclasses import dataclass


@dataclass(frozen=True)
class ProvenanceAnchor:
    span: tuple[int, int]


@dataclass(frozen=True)
class Deliverable:
    title: str
'''


def test_chain_without_code_is_inert_and_says_so(source: Path, tmp_path: Path) -> None:
    errors, info = tc.chain_state(tc.load(source), tmp_path / "nothing")
    assert errors == []
    assert any("provenance: 0 of 2 links in code" in line for line in info)


def test_chain_holds_when_the_field_refers_to_the_next_link(source: Path, tmp_path: Path) -> None:
    src = tmp_path / "src"
    _package(src, "domain", "model", CHAIN_OK)
    errors, info = tc.chain_state(tc.load(source), src / "pretraga")
    assert errors == []
    assert info == []


def test_broken_chain_blocks_once_both_ends_are_in_code(source: Path, tmp_path: Path) -> None:
    src = tmp_path / "src"
    _package(src, "domain", "model", CHAIN_BROKEN)
    errors, _ = tc.chain_state(tc.load(source), src / "pretraga")
    assert any("Deliverable has no field referring to ProvenanceAnchor" in e for e in errors)


def test_string_annotation_counts(source: Path, tmp_path: Path) -> None:
    """A forward reference is still a reference."""
    src = tmp_path / "src"
    _package(
        src,
        "domain",
        "model",
        "class ProvenanceAnchor:\n    pass\n\n\nclass Deliverable:\n"
        '    evidence: "list[ProvenanceAnchor]"\n',
    )
    errors, _ = tc.chain_state(tc.load(source), src / "pretraga")
    assert errors == []
```

- [ ] **Шаг 2: убедиться, что падают**

Запустить: `.venv/bin/python -m pytest tools -q -k chain`
Ожидается: FAIL, `module 'truth_check' has no attribute 'chain_state'`.

- [ ] **Шаг 3: реализовать**

```python
def _annotation_names(node: ast.ClassDef) -> set[str]:
    """Every identifier appearing in the annotations of a class's fields,
    including the ones inside a string forward reference."""
    names: set[str] = set()
    for statement in node.body:
        if not isinstance(statement, ast.AnnAssign) or statement.annotation is None:
            continue
        annotations: list[ast.expr] = [statement.annotation]
        for sub in ast.walk(statement.annotation):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                try:
                    annotations.append(ast.parse(sub.value, mode="eval").body)
                except SyntaxError:  # a string that is not a type expression
                    continue
        for tree in annotations:
            for sub in ast.walk(tree):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
                elif isinstance(sub, ast.Attribute):
                    names.add(sub.attr)
    return names


def chain_state(data: dict, src: Path = SRC) -> tuple[list[str], list[str]]:
    """A named chain is the claim the vision calls load-bearing. It is checked
    only where BOTH ends of a hop are already in code; before that it is inert
    and says so, instead of reading as green."""
    in_code = _public_classes(src / "domain")
    errors: list[str] = []
    info: list[str] = []
    for cid, spec in (data.get("chains") or {}).items():
        hops = spec["hops"]
        present = [hop for hop in hops if hop in in_code]
        for first, second in zip(hops, hops[1:], strict=False):
            if first not in in_code or second not in in_code:
                continue
            if second not in _annotation_names(in_code[first]):
                errors.append(
                    f"chain {cid}: {first} has no field referring to {second} — "
                    "either the model is wrong or the chain is"
                )
        if len(present) < len(hops):
            info.append(f"chain {cid}: {len(present)} of {len(hops)} links in code, check deferred")
    return errors, info
```

Подключить в `check()` рядом с `trace`:

```python
    chain_errors, chain_info = chain_state(data, src)
    errors += chain_errors
    info += chain_info
```

- [ ] **Шаг 4: прогнать**

Запустить: `.venv/bin/python -m pytest tools -q`
Ожидается: 33 passed.

- [ ] **Шаг 5: коммит**

```bash
git add tools/truth_check.py tools/test_truth_check.py
git commit -m "feat(truth): сверять несущие цепочки по аннотациям типов"
```

---

## Задача 6: точки входа — CLI и хук сессии

Спека: коммит 1, §5 (хук).

**Файлы:**
- Изменить: `tools/truth_check.py`, `tools/test_truth_check.py`

**Интерфейсы:**
- Отдаёт дальше: `main(argv: list[str]) -> int`, режимы `--build`, `--hook`,
  `--quick`; `_tool_edit(rel: str) -> bool`.

- [ ] **Шаг 1: написать падающие тесты**

```python
import io
import json
import subprocess
import sys


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "tools/truth_check.py", *args],
        capture_output=True, text=True, check=False, cwd=str(tc.ROOT),
    )


def test_cli_is_green_on_the_committed_state() -> None:
    done = _run()
    assert done.returncode == 0, done.stdout
    assert "DOMAIN TRUTH: OK" in done.stdout


def test_cli_quick_mode_stays_terse() -> None:
    done = _run("--quick")
    assert done.returncode == 0
    assert done.stdout.strip() == "DOMAIN TRUTH: OK"


def test_hook_ignores_a_path_it_does_not_govern(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = json.dumps({"tool_input": {"file_path": f"{tc.ROOT}/README.md"}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    assert tc.hook() == 0
    assert capsys.readouterr().out == ""


def test_hook_survives_malformed_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("{ not json"))
    assert tc.hook() == 0
    assert capsys.readouterr().out == ""


def test_hook_reports_a_governed_edit_without_blocking_when_green(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = json.dumps({"tool_input": {"file_path": str(tc.SOURCE)}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    assert tc.hook() == 0
    out = json.loads(capsys.readouterr().out)
    assert "TRUTH ARTIFACT edited" in out["hookSpecificOutput"]["additionalContext"]
    assert "decision" not in out, "a green map must not block"


def test_hook_blocks_on_an_unreadable_map(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    broken = tmp_path / "domain.yaml"
    broken.write_text("{[ not yaml", encoding="utf-8")
    payload = json.dumps({"tool_input": {"file_path": str(tc.SOURCE)}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    assert tc.hook(source=broken) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "block"
    assert "MAP UNREADABLE" in out["hookSpecificOutput"]["additionalContext"]


def test_demotion_covers_tools_only() -> None:
    """Editing the renderer redefines what a fresh view is, so the view goes
    stale at that instant and cannot be rebuilt until the edit is finished. A
    block that cannot be obeyed teaches the operator to ignore blocks."""
    assert tc._tool_edit("tools/truth_check.py")
    assert not tc._tool_edit("docs/system_design/domain.yaml")
    assert not tc._tool_edit("docs/system_design/domain_glossary.md")
    assert not tc._tool_edit("src/pretraga/domain/anything.py")
```

- [ ] **Шаг 2: убедиться, что падают**

Запустить: `.venv/bin/python -m pytest tools -q -k "cli or hook or demotion"`
Ожидается: FAIL — `truth_check.py` пока не имеет `__main__`-обвязки и `hook`.

- [ ] **Шаг 3: реализовать**

```python
GOVERNED_PREFIXES = ("src/", "docs/system_design/", "tools/")


def _tool_edit(rel: str) -> bool:
    """True when the edited file is a tool of this system rather than its data."""
    return rel.startswith("tools/") and rel.endswith(".py")


def _relative(path: Path) -> str | None:
    """Repo-relative form, or None for a path outside it. Tests pass temporary
    paths, so this must not raise where production paths never would."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return None


def _report(errors: list[str], info: list[str], quick: bool = False) -> int:
    for line in info if not quick else []:
        print(f"  i {line}")
    if errors:
        print(f"DOMAIN TRUTH: {len(errors)} error(s)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("DOMAIN TRUTH: OK")
    return 0


def hook(source: Path = SOURCE, view: Path = VIEW, src: Path = SRC) -> int:
    """Session-hook entry: read the harness PostToolUse JSON from stdin, filter
    to files the map governs, report. Always exits 0 — the blocking exits are
    the local gate and CI; the block here is expressed in the JSON decision,
    which the harness applies deterministically."""
    import io
    import json
    from contextlib import redirect_stdout

    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 — malformed hook input must never crash the hook
        return 0
    file_path = str((payload.get("tool_input") or {}).get("file_path") or "")
    root = str(ROOT)
    if not file_path.startswith(root + "/"):
        return 0
    rel = file_path[len(root) + 1 :]
    if not rel.startswith(GOVERNED_PREFIXES):
        return 0

    lines = [f"[domain-truth] change touches governed path: {rel}"]
    truth_files = {r for r in (_relative(source), _relative(view)) if r}
    if rel in truth_files:
        lines.append(
            "[domain-truth] TRUTH ARTIFACT edited — this must be a design decision, "
            "not a way to silence a check"
        )
    failed = False
    buffer = io.StringIO()
    try:
        errors, info = check(source, view, src)
        if _tool_edit(rel):
            errors = [e for e in errors if "stale or hand-edited" not in e]
            info = info + ["view freshness demoted: a tool is being edited; rebuild before committing"]
        with redirect_stdout(buffer):
            failed = _report(errors, info, quick=True) != 0
        lines.extend(buffer.getvalue().strip().splitlines())
    except Exception as exc:  # noqa: BLE001 — the hook must ALWAYS emit JSON
        lines.append(f"[domain-truth] MAP UNREADABLE (fix before relying on any check): {exc}")
        failed = True

    out: dict = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n".join(lines),
        }
    }
    if failed:
        out["decision"] = "block"
        out["reason"] = (
            "Domain truth conformance FAILED — bring it back to green (usually: fix "
            "the map, or run tools/truth_check.py --build) or explicitly surface the "
            "failure to the user before continuing."
        )
    print(json.dumps(out, ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--hook":
        return hook()
    if argv and argv[0] == "--build":
        return build()
    errors, info = check()
    return _report(errors, info, quick=bool(argv) and argv[0] == "--quick")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Шаг 4: прогнать полный набор и гейт инструмента**

Запустить:
```
.venv/bin/python -m pytest tools -q
.venv/bin/python -m ruff check tools && .venv/bin/python -m mypy tools/truth_check.py
.venv/bin/python tools/truth_check.py
```
Ожидается: 40 passed; линт и типы чисто; `DOMAIN TRUTH: OK`.

- [ ] **Шаг 5: перевести хук сессии**

Правка `.claude/settings.json` (вне git — делается отдельно, в коммит не входит):
заменить команду на
`cd "<корень>" && .venv/bin/python tools/truth_check.py --hook`.
Проверить руками: записать любой файл под `src/` и убедиться, что в сессию
приходит отчёт `[domain-truth]`.

- [ ] **Шаг 6: коммит**

```bash
git add tools/truth_check.py tools/test_truth_check.py
git commit -m "feat(truth): точки входа — CLI, быстрый режим и хук сессии"
```

---

## Задача 7: мутационный стенд

Спека: коммит 2, раздел «Тестовое покрытие».

**Файлы:**
- Создать: `tools/test_mutations.py`

**Интерфейсы:**
- Потребляет: `tools/truth_check.py` как текст (мутации — литералы исходника).

- [ ] **Шаг 1: написать стенд**

```python
"""Mutation harness for the truth tool: plant a defect, demand a red suite.

A green suite is not evidence the tests CAN fail. Every check exists to catch
one thing; the only way to know it still does is to break that thing on purpose
and watch the suite go red.

Marked `heavy` — it runs the whole suite once per mutation, so it is excluded
from the default gate filter and invoked deliberately:

    .venv/bin/python -m pytest -m heavy

Anchor staleness is checked separately and is NOT heavy: renaming a function
invalidates the literal it is anchored by, and that must surface in the normal
gate rather than after minutes of the heavy run.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

HERE = Path(__file__).resolve().parent
TOOL = "truth_check.py"
SELF = "test_every_suite_spawning_test_is_marked_heavy"
SUITE_TIMEOUT_S = 300


class Mutation(NamedTuple):
    """`find` must occur EXACTLY once in the tool: a literal matching twice
    would mutate whichever came first, and the harness would be testing
    something other than what it names."""

    name: str
    find: str
    replace: str


MUTATIONS = [
    Mutation("duplicate YAML keys let through", "        if key in mapping:", "        if False:"),
    Mutation("unknown kind accepted", '        if entity.get("kind") not in KINDS:', "        if False:"),
    Mutation("missing required field accepted",
             '            if not str(entity.get(field, "")).strip():', "            if False:"),
    Mutation("duplicate id accepted", "        if eid in seen:", "        if False:"),
    Mutation("unknown trigger accepted",
             "            if trigger is not None and trigger not in triggers:", "            if False:"),
    Mutation("chain hop outside the map accepted", "            if hop not in seen:", "            if False:"),
    Mutation("stale generated view passes",
             '    elif view.read_text(encoding="utf-8") != render(data):', "    elif False:"),
    Mutation("undeclared domain type let through",
             "        for name in sorted(set(in_code) - declared)", "        for name in []"),
    Mutation("concept without code turned back into an error",
             '        f"undeclared domain type in code: {name} — rename it, or add it to domain.yaml"\n'
             "        for name in sorted(set(in_code) - declared)",
             '        f"undeclared domain type in code: {name}"\n'
             "        for name in sorted(set(in_code) ^ declared)"),
    Mutation("broken chain accepted",
             "            if second not in _annotation_names(in_code[first]):", "            if False:"),
]


def run_suite(directory: Path) -> subprocess.CompletedProcess[str]:
    """The suite as the gate runs it, against a copy. `not heavy` keeps the
    copy's own mutation module out — otherwise this would recurse."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-m", "not heavy", "-p", "no:cacheprovider", str(directory)],
        capture_output=True, text=True, check=False, timeout=SUITE_TIMEOUT_S, cwd=str(directory),
    )


@pytest.fixture
def tool_copy(tmp_path: Path) -> Path:
    """The whole repository copied, so the tool's ROOT-derived paths resolve to
    a copy of the map and of src/ rather than to production."""
    destination = tmp_path / "repo"
    shutil.copytree(
        HERE.parent,
        destination,
        ignore=shutil.ignore_patterns(
            "__pycache__", ".pytest_cache", ".git", ".venv", ".mypy_cache",
            ".ruff_cache", ".hypothesis", "htmlcov",
        ),
    )
    return destination / "tools"


def test_mutation_names_are_unique() -> None:
    names = [m.name for m in MUTATIONS]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("mutation", MUTATIONS, ids=lambda m: m.name)
def test_mutation_anchor_matches_exactly_once(mutation: Mutation) -> None:
    """Anchors are literal source text, so a rename silently invalidates one.
    Catching that here costs milliseconds; catching it inside the heavy run
    costs minutes and looks like a failure of the tool rather than of the
    harness."""
    source = (HERE / TOOL).read_text(encoding="utf-8")
    assert source.count(mutation.find) == 1, (
        f"anchor for {mutation.name!r} matches {source.count(mutation.find)} times — re-anchor it"
    )
    assert mutation.find != mutation.replace


def test_every_suite_spawning_test_is_marked_heavy() -> None:
    """The anti-recursion invariant as a check rather than a habit."""
    import inspect

    module = sys.modules[__name__]
    for name, obj in vars(module).items():
        if not name.startswith("test_") or not callable(obj) or name == SELF:
            continue
        if "run_suite(" not in inspect.getsource(obj):
            continue
        marks = {m.name for m in getattr(obj, "pytestmark", [])}
        assert "heavy" in marks, f"{name} spawns a suite but is not marked heavy"


@pytest.mark.heavy
def test_untouched_copy_is_green(tool_copy: Path) -> None:
    """The control. Without it a red result could just mean the copy is broken."""
    done = run_suite(tool_copy)
    assert done.returncode == 0, done.stdout[-3000:]


@pytest.mark.heavy
@pytest.mark.parametrize("mutation", MUTATIONS, ids=lambda m: m.name)
def test_planted_defect_turns_the_suite_red(mutation: Mutation, tool_copy: Path) -> None:
    target = tool_copy / TOOL
    source = target.read_text(encoding="utf-8")
    assert source.count(mutation.find) == 1
    target.write_text(source.replace(mutation.find, mutation.replace, 1), encoding="utf-8")

    done = run_suite(tool_copy)
    assert done.returncode != 0, (
        f"mutation {mutation.name!r} SURVIVED — no test constrains this behaviour\n"
        + done.stdout[-3000:]
    )
```

- [ ] **Шаг 2: прогнать дешёвую часть**

Запустить: `.venv/bin/python -m pytest tools -q -m "not heavy"`
Ожидается: 52 passed. Если какой-то якорь мутации не совпал ровно один раз —
править литерал, а не код инструмента.

- [ ] **Шаг 3: прогнать стенд целиком**

Запустить: `.venv/bin/python -m pytest -m heavy -q -p no:cacheprovider`
Ожидается: 11 passed. **Любая выжившая мутация — задача не закрыта:** значит,
проверку не сторожит ни один тест, и надо дописать тест, а не удалить мутацию.

- [ ] **Шаг 4: коммит**

```bash
git add tools/test_mutations.py
git commit -m "test(truth): мутационный стенд на десять проверок"
```

---

## Задача 8: удалить старую систему, перевести гейт, CI и покрытие

Спека: коммит 3. **Порядок вынужденный:** пока `design_truth/` жив, создание
`src/` роняет его проверку, поэтому удаление предшествует первому пакету.

**Файлы:**
- Удалить: `docs/system_design/design_truth/` (8 файлов)
- Изменить: `pyproject.toml`, `.github/workflows/ci.yml`, `CLAUDE.md` §10

- [ ] **Шаг 1: убедиться, что замена зелёная сама по себе**

Запустить: `.venv/bin/python tools/truth_check.py && .venv/bin/python -m pytest tools -q -m "not heavy"`
Ожидается: `DOMAIN TRUTH: OK`, 52 passed. Пока не зелено — не удалять ничего.

- [ ] **Шаг 2: удалить**

```bash
git rm -r docs/system_design/design_truth
```

- [ ] **Шаг 3: перевести покрытие**

В `pyproject.toml` заменить:

```toml
[tool.coverage.run]
source = ["src", "tools"]
omit = ["*/conftest.py", "*/test_*.py"]
```

Комментарий над блоком переписать: `src/` перечислен до своего появления —
coverage предупреждает и продолжает, поэтому в день появления пакетов править
здесь нечего.

- [ ] **Шаг 4: перемерить порог покрытия**

Запустить ровно ту команду, что стоит в CI:
`.venv/bin/python -m pytest -m "not heavy" --cov --cov-report=term-missing`
Записать полученное число. Поставить `fail_under` **на два пункта ниже**
измеренного (CI меряет чуть ниже локального прогона). Перенести прежние 90 —
ошибка: это число снято с другого кода.

- [ ] **Шаг 5: перевести CI**

В `.github/workflows/ci.yml` заменить последний шаг:

```yaml
      - name: Domain truth
        if: '!cancelled()'
        run: uv run python tools/truth_check.py
```

Шаг `Import contracts` НЕ добавлять — он появится в задаче 10, когда будут
пакеты: `lint-imports` без корневого пакета падает, и красный CI без причины
хуже отсутствующей проверки.

- [ ] **Шаг 6: перевести локальный гейт в `CLAUDE.md` §10**

Заменить команду на:

```
ruff check \
  && git ls-files --cached --others --exclude-standard '*.py' | xargs -r python -m mypy \
  && python -m pytest -m "not heavy" --cov --cov-report=term-missing \
  && python tools/truth_check.py
```

Правило «при расхождении сверяться с `.github/workflows/ci.yml`, а не с памятью»
оставить дословно.

- [ ] **Шаг 7: прогнать гейт целиком**

Запустить команду из шага 6.
Ожидается: всё зелёное, покрытие не ниже нового порога.

- [ ] **Шаг 8: коммит**

```bash
git add -A
git commit -m "refactor(truth)!: удалить design_truth, перевести гейт, CI и покрытие"
```

---

## Задача 9: актуализировать видение и перенести решения процессов

Спека: коммит 4. **Ответ на вопрос «нужно ли править видение»: да, в пяти
местах, и они выписаны точно.**

**Файлы:**
- Изменить: `docs/system_design/architectural_vision.md`

- [ ] **Шаг 1: правка 1 — шапка (строка 5)**

Было: `[словарь сущностей](design_truth/entity_glossary.md); терминология — только оттуда.`
Стало: `[словарь домена](domain_glossary.md); терминология — только оттуда.`

- [ ] **Шаг 2: правка 2 — конец §5 (строки 88–90)**

Было:
```
Сквозное для всех слоёв (слой `foundation` карты): единый сетевой клиент, словари
и таблицы правил, манифесты деривации, замок писателя. Репозиторий кода и
рабочее пространство — раздельны.
```
Стало:
```
Сквозное для всех слоёв: единый сетевой клиент, словари и таблицы правил,
манифесты деривации, замок писателя. В коде это кольцо `adapters` — реализации
портов, объявленных доменом; семь слоёв выше — стадии конвейера, а не уровни
зависимости, и направление зависимости задаётся кольцами, не ими. Репозиторий
кода и рабочее пространство — раздельны.
```

- [ ] **Шаг 3: правка 3 — первый абзац §6 (строки 94–97)**

Было:
```
Сущности, атрибуты, связи, определения, породы и слои — в
[карте](design_truth/entity_map.md) и [словаре](design_truth/entity_glossary.md);
граф, проекции, пути и стек слоёв генерируются оттуда. Рукописной копии графа здесь нет
намеренно: она разошлась бы с картой незаметно.
```
Стало:
```
Понятия домена, их породы и определения — в [`domain.yaml`](domain.yaml) и
сгенерированном из него [словаре](domain_glossary.md); несущие цепочки объявлены
там же блоком `chains` и сверяются с полями реальных моделей. Направление
зависимости живёт не здесь и не в словаре, а в контракте импортов
(`pyproject.toml`), проверяемом на настоящих импортах. Рукописного графа связей
нет намеренно: сверить его с кодом нечем, поэтому он расходился бы молча.
```

- [ ] **Шаг 4: правка 4 — строка таблицы §9 (строка 168)**

Заменить строку целиком:

```
| Тонкий свой чекер словаря плюс import-linter на направление зависимостей | ArchUnit; Structurizr; Backstage; собственная модель архитектуры графом связей | ArchUnit — библиотека для Java, у нас Python; Structurizr требует JVM, которой на машине нет; Backstage поставляется порталом-службой — несоразмерно одному репозиторию. Собственный граф отклонён замером: из 85 рёбер что-либо ограничивали 7, и все семь — звенья цепочек провенанса. Пересмотр: JVM-компонент, продуктизация, вторая команда соответственно |
```

- [ ] **Шаг 5: правка 5 — §11, замена одной строки на две**

Убрать:
```
| Зависимости pyproject без потребителей (наследие старого проекта) | Сверка при первой спецификации; старый проект — не образец по умолчанию |
```
Поставить:
```
| Локальный инференс: §4 объявляет, что его нет, а `tokenizers` и `onnxruntime` закреплены под bge-m3 на CPU | Спецификация слоя обогащения: двинуть §4 либо пины |
| Графовый стек: `nx.pagerank` требует scipy (его нет в зависимостях), а `leiden_communities` в networkx — только диспетчер к внешнему бэкенду | Спецификация слоя обогащения, измерением на этой машине |
```

- [ ] **Шаг 6: перенести решения процессов**

Двенадцать процессов старой карты перестали быть понятиями. Их поведенческие
решения уже сказаны в видении §5 и §9 либо в `CLAUDE.md`; задача — **проверить
и не создать второго носителя**, а не переписать заново.

Проверить по списку, что каждое утверждение имеет ровно один дом:

| Процесс | Где живёт после переноса |
|---|---|
| `AdmissionMinimum` | `CLAUDE.md` §4 «Structural invariants live in ONE function»; состав — §11 видения, открытый пункт |
| `Triage` | видение §5 п. 4 и §9 (строка «Скачивание раньше триажа») |
| `Deduplication` | видение §5 п. 4, §6 и §9 (строка «Две точки дедупликации»); асимметрия — `CLAUDE.md` §8 |
| `MergeOperation` | видение §6 («вечный алиас») |
| `Enrichment` | видение §5 п. 5 и §6 (двухуровневая инкрементальность) |
| `ExceptionQueue` | видение §5 п. 5; состав — §11, открытый пункт |
| `Reconciliation` | `CLAUDE.md` §6 целиком |
| `QueryLayer` | видение §7 |
| `TrendQuery` | видение §7 и §1 (семантика числа) |
| `DeliverableValidator` | видение §5 п. 7 и §10 |
| `NetworkClient` | `CLAUDE.md` §9 «Retry armour lives in ONE shared client» |
| `WriterLock` | `CLAUDE.md` §6 «Prefer a single writer to a lock» и видение §8 |

Дописывать в видение **только то, чего в нём нет ни в одном из двух мест**.
Если утверждение уже есть — не дублировать: это ровно тот дефект, который спека
разбирает.

- [ ] **Шаг 7: проверить, что мёртвых ссылок не осталось**

Запустить:
```
rg -n "design_truth|entity_map|entity_glossary" docs/ CLAUDE.md .github/
```
Ожидается: пусто. Любое совпадение — недоделанная правка.

- [ ] **Шаг 8: коммит**

```bash
git add docs/system_design/architectural_vision.md
git commit -m "docs(design): актуализировать видение под замену системы истины"
```

---

## Задача 10: кольца и контракт импортов

Спека: коммиты 5 и 6.

**Файлы:**
- Создать: `src/pretraga/__init__.py` и по `__init__.py` в четырёх кольцах
- Изменить: `pyproject.toml`, `.github/workflows/ci.yml`, `CLAUDE.md` §10,
  `tools/test_mutations.py`

- [ ] **Шаг 1: завести пакеты**

```bash
mkdir -p src/pretraga/{domain,usecases,adapters,entrypoints}
for d in "" /domain /usecases /adapters /entrypoints; do : > "src/pretraga$d/__init__.py"; done
```

- [ ] **Шаг 2: убедиться, что стены больше нет**

Запустить: `.venv/bin/python tools/truth_check.py`
Ожидается: **exit 0**, `DOMAIN TRUTH: OK`, плюс информационная строка
`i 20 of 20 concepts have no code yet: …`.
Это и есть проверка развёрнутой стены: в старой системе тот же момент давал
ненулевой код выхода.

- [ ] **Шаг 3: добавить контракт**

В `pyproject.toml`:

```toml
# Направление зависимости проверяется на НАСТОЯЩИХ импортах, а не на рукописном
# графе: слой модуля есть его каталог, и рукописного отображения не существует.
[tool.importlinter]
root_packages = ["pretraga"]
include_external_packages = true

[[tool.importlinter.contracts]]
name = "Кольца: зависимости смотрят внутрь"
type = "layers"
layers = ["pretraga.entrypoints", "pretraga.adapters", "pretraga.usecases", "pretraga.domain"]

[[tool.importlinter.contracts]]
name = "Одна дверь наружу: сеть только в адаптере"
type = "forbidden"
source_modules = ["pretraga.domain", "pretraga.usecases"]
forbidden_modules = ["urllib", "httpx"]
```

`lint-imports` импортирует корневой пакет, а `[tool.uv] package = false` —
проект не устанавливается. Значит, пакет виден только через `PYTHONPATH`.
Решение принято здесь, а не оставлено исполнителю: **везде запускать контракт
как `PYTHONPATH=src lint-imports`** — в гейте `CLAUDE.md` §10 и в CI через
`env:` шага. Плюс `pythonpath = ["src"]` в `[tool.pytest.ini_options]`, чтобы
тесты видели пакет тем же способом.

Альтернатива — сделать проект устанавливаемым (`package = true`, src-layout):
тогда `uv sync` кладёт пакет в окружение и переменная не нужна. Она лучше в
день, когда у CLI появится консольная команда; сейчас это лишнее решение,
принятое раньше своего потребителя.

- [ ] **Шаг 4: проверить контракт вживую**

```bash
PYTHONPATH=src .venv/bin/lint-imports
```
Ожидается: `Contracts: 2 kept, 0 broken`, exit 0. Именно консольный скрипт —
`python -m importlinter.cli` молча возвращает 0, не проверив ничего.

Затем подсадить нарушение и убедиться, что оно ловится:
```bash
echo "from pretraga.adapters import x" >> src/pretraga/usecases/__init__.py
PYTHONPATH=src .venv/bin/lint-imports; echo "ожидается exit 1"
git checkout -- src/pretraga/usecases/__init__.py
```

- [ ] **Шаг 5: добавить мутацию на контракт**

Дописать в `tools/test_mutations.py`:

```python
CONTRACT_VIOLATION = "from pretraga.adapters.registry import GitRegistry\n"


def _lint(repo: Path) -> subprocess.CompletedProcess[str]:
    """import-linter has no __main__: `python -m importlinter.cli` imports the
    module, runs nothing and exits 0 — a silent pass that reads exactly like
    success. Verified. Only the console script actually lints."""
    import os

    executable = shutil.which("lint-imports", path=str(Path(sys.executable).parent))
    assert executable, "lint-imports is not in the venv — the contract cannot be checked"
    return subprocess.run(
        [executable], capture_output=True, text=True, check=False, cwd=str(repo),
        env=dict(os.environ, PYTHONPATH="src"), timeout=SUITE_TIMEOUT_S,
    )


@pytest.mark.heavy
def test_ring_contract_actually_catches_a_violation(tmp_path: Path) -> None:
    """The contract is a mechanism like any other: without planting a violation
    we would only know that it parses, not that it fires."""
    repo = tmp_path / "repo"
    shutil.copytree(
        HERE.parent, repo,
        ignore=shutil.ignore_patterns(
            "__pycache__", ".pytest_cache", ".git", ".venv", ".mypy_cache",
            ".ruff_cache", ".hypothesis", "htmlcov",
        ),
    )
    (repo / "src" / "pretraga" / "adapters" / "registry.py").write_text(
        "class GitRegistry:\n    pass\n", encoding="utf-8"
    )
    assert _lint(repo).returncode == 0, _lint(repo).stdout

    (repo / "src" / "pretraga" / "usecases" / "triage.py").write_text(
        CONTRACT_VIOLATION, encoding="utf-8"
    )
    broken = _lint(repo)
    assert broken.returncode != 0, "the ring contract did not fire on a real violation"
    assert "not allowed to import" in broken.stdout
```

⚠ Не заменять консольный скрипт на `python -m importlinter.cli`: у пакета нет
`__main__.py`, поэтому такой вызов импортирует модуль, ничего не линтует и
возвращает 0. Проверено исполнением — это молчаливый пропуск, неотличимый от
успеха.

- [ ] **Шаг 6: включить контракт в гейт и CI**

`CLAUDE.md` §10 — добавить шаг перед `truth_check.py`:
```
  && PYTHONPATH=src lint-imports \
```

`.github/workflows/ci.yml` — добавить перед шагом `Domain truth`:
```yaml
      - name: Import contracts
        if: '!cancelled()'
        env:
          PYTHONPATH: src
        run: uv run lint-imports
```

- [ ] **Шаг 7: прогнать всё**

```
ruff check \
  && git ls-files --cached --others --exclude-standard '*.py' | xargs -r .venv/bin/python -m mypy \
  && .venv/bin/python -m pytest -m "not heavy" --cov --cov-report=term-missing \
  && PYTHONPATH=src .venv/bin/lint-imports \
  && .venv/bin/python tools/truth_check.py
```
Ожидается: пять зелёных шагов.

- [ ] **Шаг 8: коммит**

```bash
git add -A
git commit -m "feat(arch): завести кольца pretraga и контракт направления зависимостей"
```

---

## Задача 11: закрыть бэклог

Спека: коммит 7.

**Файлы:**
- Изменить: `docs/backlog/backlog.md`
- Удалить: `docs/backlog/ports_and_layers_brief.md`

- [ ] **Шаг 1: удалить девять закрытых пунктов**

Из таблицы уходят пункты 1–9: предохранитель разведочного кода, направление
зависимостей и порты, обязательства пород, конвенции и удвоение идентичности,
проза против графа, якоря, генерация контракта, типы атрибутов, имена пометок.
Все девять закрыты не «сделано», а тем, что механизм, их породивший, удалён.

Остаётся пункт 10 (dbt) — он про продукт, и его триггер прежний.

- [ ] **Шаг 2: удалить бриф**

```bash
git rm docs/backlog/ports_and_layers_brief.md
```
Убрать ссылку на него из строки пункта 2, если та ещё осталась.

- [ ] **Шаг 3: проверить, что бэклог не ссылается на удалённое**

Запустить: `rg -n "design_truth|entity_map|ports_and_layers" docs/backlog/`
Ожидается: пусто.

- [ ] **Шаг 4: финальный прогон гейта и стенда**

```
.venv/bin/python -m pytest -m heavy -q -p no:cacheprovider
```
плюс полная команда гейта из задачи 10, шаг 7.
Ожидается: всё зелёное; ни одна мутация не выжила.

- [ ] **Шаг 5: коммит**

```bash
git add -A
git commit -m "docs(backlog): удалить девять пунктов и бриф портов, закрытые заменой"
```

---

## Самопроверка плана

**Покрытие спеки.** §1 → задачи 10, 9. §2 → задачи 1, 2. §3 → задача 10.
§4 → задачи 1, 3, 4, 5, 6. §5 → задачи 6, 8, 10. §6 → задачи 2, 9.
§7 (зависимости не трогаем) → нет задачи, и это верно: спека требует
бездействия. Обоснование О1–О14 → не реализуется, это запись решений.
«Тестовое покрытие» → задачи 1–7. «План коммитов» → задачи 1–11.

**Расхождения с текстом спеки, названные явно:**
1. Спека называет 7 коммитов, план — 11 задач с коммитом каждая. Первый пункт
   спеки развёрнут в пять задач, потому что инструмент строится по TDD.
2. Спека оценивает чекер в ~150 строк; с докстрингами выходит ~200.
3. Цепочка `provenance_stamp` укорачивается с трёх звеньев до двух:
   `CorpusRegistry` — хранилище и в модель домена не переносится.

**Одно место, где план не называет числа:** порог `fail_under` (задача 8,
шаг 4). Он измеряется той же командой, что стоит в CI, а не назначается —
перенос прежних 90 был бы числом, снятым с другого кода (`CLAUDE.md` §10).

**Три ловушки, проверенные исполнением и записанные, чтобы в них не наступили:**
`python -m importlinter.cli` молча возвращает 0; `Path.relative_to` бросает
`ValueError` на временном пути вне репозитория, из-за чего хук упал бы на
собственном тесте; `lint-imports` без `PYTHONPATH=src` не находит пакет, потому
что проект не устанавливается.
